# apps/leaderboards/management/commands/populate_leaderboards.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from apps.leaderboards.models import LeaderboardType, Leaderboard, LeaderboardEntry
from apps.results.models import ExamResult
from apps.leaderboards.tasks import update_all_leaderboards
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Populate leaderboards with existing exam results"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force repopulation even if leaderboards exist",
        )
        parser.add_argument(
            "--period",
            type=str,
            default="weekly",
            help="Period to populate (weekly, monthly, etc.)",
        )
        parser.add_argument(
            "--exam-type",
            type=str,
            default="scheduled",
            help="Exam type to populate (scheduled, practice, self_paced)",
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting leaderboard population...")

        # Check if we have any exam results
        total_results = ExamResult.objects.count()
        if total_results == 0:
            self.stdout.write(
                self.style.ERROR(
                    "No exam results found. Users need to complete exams first."
                )
            )
            return

        self.stdout.write(f"Found {total_results} exam results to process")

        # Get current time and calculate periods
        now = timezone.now()
        period = options["period"]
        exam_type_filter = options["exam_type"]

        # Calculate period dates
        if period == "weekly":
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            period_end = period_start + timedelta(days=7)
        elif period == "monthly":
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if period_start.month == 12:
                period_end = period_start.replace(year=period_start.year + 1, month=1)
            else:
                period_end = period_start.replace(month=period_start.month + 1)
        else:
            # Default to last 7 days for other periods
            period_start = now - timedelta(days=7)
            period_end = now

        self.stdout.write(f"Processing period: {period_start} to {period_end}")

        # Find or create leaderboard types
        lb_type = LeaderboardType.objects.filter(
            scope="exam",
            period=period,
            exam_type_filter=exam_type_filter,
            is_active=True,
        ).first()

        if not lb_type:
            self.stdout.write(
                self.style.ERROR(
                    f"No leaderboard type found for {exam_type_filter} exams with {period} period"
                )
            )
            return

        # Get exam results in the period
        results_filter = {
            "created_at__gte": period_start,
            "created_at__lt": period_end,
        }

        # Filter by exam type if specified
        if exam_type_filter != "all":
            results_filter["exam__exam_type"] = exam_type_filter

        results = ExamResult.objects.filter(**results_filter).select_related(
            "user", "exam"
        )

        if not results.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"No exam results found in period {period_start} to {period_end}"
                )
            )
            # Try with a broader time range (last 30 days)
            broader_start = now - timedelta(days=30)
            broader_results = ExamResult.objects.filter(
                created_at__gte=broader_start,
                exam__exam_type=(
                    exam_type_filter if exam_type_filter != "all" else "scheduled"
                ),
            ).select_related("user", "exam")

            if broader_results.exists():
                self.stdout.write(
                    f"Found {broader_results.count()} results in last 30 days, using those..."
                )
                results = broader_results
                period_start = broader_start
                period_end = now
            else:
                self.stdout.write(
                    self.style.ERROR("No results found even in last 30 days")
                )
                return

        self.stdout.write(f"Processing {results.count()} exam results")

        # Group results by exam
        exams_with_results = {}
        for result in results:
            exam_id = result.exam.id
            if exam_id not in exams_with_results:
                exams_with_results[exam_id] = {"exam": result.exam, "results": []}
            exams_with_results[exam_id]["results"].append(result)

        created_leaderboards = 0
        created_entries = 0

        for exam_id, data in exams_with_results.items():
            exam = data["exam"]
            exam_results = data["results"]

            self.stdout.write(
                f"\nProcessing exam: {exam.title} ({len(exam_results)} results)"
            )

            # Create or get leaderboard for this exam
            leaderboard, created = Leaderboard.objects.get_or_create(
                leaderboard_type=lb_type,
                exam=exam,
                period_start=period_start,
                period_end=period_end,
                defaults={
                    "subject": None,
                    "chapter": None,
                },
            )

            if created:
                created_leaderboards += 1
                self.stdout.write(f"  Created leaderboard for {exam.title}")
            elif options["force"]:
                # Clear existing entries if forcing
                leaderboard.entries.all().delete()
                self.stdout.write(f"  Cleared existing entries for {exam.title}")

            # Group results by user (get best score per user)
            user_best_scores = {}
            for result in exam_results:
                user_id = result.user.id
                if (
                    user_id not in user_best_scores
                    or result.percentage_score > user_best_scores[user_id]["score"]
                ):
                    user_best_scores[user_id] = {
                        "user": result.user,
                        "score": result.percentage_score,
                        "result": result,
                    }

            # Sort users by score
            sorted_users = sorted(
                user_best_scores.values(), key=lambda x: x["score"], reverse=True
            )

            # Create leaderboard entries
            entries_to_create = []
            leaderboard_data = []

            for rank, user_data in enumerate(sorted_users, 1):
                user = user_data["user"]
                result = user_data["result"]

                # Count user's total exams of this type
                user_total_exams = ExamResult.objects.filter(
                    user=user,
                    exam__exam_type=exam.exam_type,
                    created_at__gte=period_start,
                    created_at__lt=period_end,
                ).count()

                # Calculate achievements and badges
                achievements = []
                badges = []

                if result.percentage_score >= 95:
                    achievements.append(
                        {
                            "title": "Perfectionist",
                            "description": "Scored 95% or higher",
                            "icon": "star",
                            "type": "score",
                        }
                    )

                if rank == 1:
                    badges.append(
                        {
                            "name": "Gold Medal",
                            "description": "First place",
                            "color": "gold",
                        }
                    )
                elif rank <= 3:
                    badges.append(
                        {
                            "name": "Top 3",
                            "description": "Top 3 performer",
                            "color": "silver",
                        }
                    )
                elif rank <= 10:
                    badges.append(
                        {
                            "name": "Top 10",
                            "description": "Top 10 performer",
                            "color": "bronze",
                        }
                    )

                # Create entry
                entry = LeaderboardEntry(
                    leaderboard=leaderboard,
                    user=user,
                    rank=rank,
                    score=result.percentage_score,
                    total_exams=user_total_exams,
                    total_questions=result.total_questions,
                    correct_answers=result.correct_answers,
                    average_score=result.percentage_score,
                    best_score=result.percentage_score,
                    total_time_minutes=result.time_taken_minutes,
                    consistency_score=100.0,  # Single exam, perfect consistency
                    performance_trend="new",
                    achievements=achievements,
                    badges=badges,
                )
                entries_to_create.append(entry)

                # Add to cached data
                leaderboard_data.append(
                    {
                        "user_id": str(user.id),
                        "user_name": user.get_full_name(),
                        "rank": rank,
                        "score": result.percentage_score,
                        "total_exams": user_total_exams,
                    }
                )

            # Bulk create entries
            if entries_to_create:
                LeaderboardEntry.objects.bulk_create(
                    entries_to_create, ignore_conflicts=True
                )
                created_entries += len(entries_to_create)
                self.stdout.write(f"  Created {len(entries_to_create)} entries")

                # Update leaderboard metadata
                leaderboard.total_participants = len(entries_to_create)
                leaderboard.leaderboard_data = leaderboard_data
                leaderboard.save()

        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\nPopulation complete!\n"
                f"Created {created_leaderboards} leaderboards\n"
                f"Created {created_entries} leaderboard entries"
            )
        )

        # Trigger update of all leaderboards to ensure consistency
        self.stdout.write("Triggering full leaderboard update...")
        try:
            from apps.leaderboards.tasks import update_all_leaderboards

            # Call synchronously for immediate results
            update_all_leaderboards()
            self.stdout.write(self.style.SUCCESS("Leaderboard update completed"))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error updating leaderboards: {str(e)}")
            )
