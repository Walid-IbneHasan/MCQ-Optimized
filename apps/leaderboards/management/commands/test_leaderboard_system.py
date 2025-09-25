# apps/leaderboards/management/commands/test_leaderboard_system.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.leaderboards.models import LeaderboardType, Leaderboard, LeaderboardEntry
from apps.results.models import ExamResult
from apps.exams.models import Exam

User = get_user_model()


class Command(BaseCommand):
    help = "Test and debug leaderboard system"

    def handle(self, *args, **options):
        self.stdout.write("=== LEADERBOARD SYSTEM DIAGNOSTIC ===\n")

        # 1. Check LeaderboardTypes
        lb_types = LeaderboardType.objects.all()
        self.stdout.write(f"1. LeaderboardTypes found: {lb_types.count()}")
        for lb_type in lb_types[:5]:
            self.stdout.write(
                f"   - {lb_type.name} ({lb_type.scope}, {lb_type.period}, {lb_type.exam_type_filter})"
            )

        # 2. Check ExamResults
        results = ExamResult.objects.all()
        self.stdout.write(f"\n2. ExamResults found: {results.count()}")
        if results.exists():
            latest = results.order_by("-created_at").first()
            self.stdout.write(
                f"   - Latest: {latest.user.get_full_name()} - {latest.exam.title} - {latest.percentage_score}%"
            )

            # Check exam types
            exam_types = results.values_list("exam__exam_type", flat=True).distinct()
            self.stdout.write(f"   - Exam types in results: {list(exam_types)}")

        # 3. Check Leaderboards
        leaderboards = Leaderboard.objects.all()
        self.stdout.write(f"\n3. Leaderboard instances found: {leaderboards.count()}")
        for lb in leaderboards[:3]:
            self.stdout.write(
                f"   - {lb.leaderboard_type.name}: {lb.total_participants} participants"
            )

        # 4. Check LeaderboardEntries
        entries = LeaderboardEntry.objects.all()
        self.stdout.write(f"\n4. LeaderboardEntries found: {entries.count()}")
        if entries.exists():
            top_entry = entries.order_by("rank").first()
            self.stdout.write(
                f"   - Top entry: {top_entry.user.get_full_name()} - Rank {top_entry.rank} - {top_entry.score}%"
            )

        # 5. Check for data mismatches
        self.stdout.write(f"\n5. DIAGNOSTIC CHECKS:")

        if results.exists() and not leaderboards.exists():
            self.stdout.write(
                self.style.WARNING(
                    "   ⚠️  ISSUE: ExamResults exist but no Leaderboard instances found"
                )
            )
            self.stdout.write("   💡 FIX: Run 'python manage.py populate_leaderboards'")

        if leaderboards.exists() and not entries.exists():
            self.stdout.write(
                self.style.WARNING(
                    "   ⚠️  ISSUE: Leaderboard instances exist but no LeaderboardEntries found"
                )
            )
            self.stdout.write(
                "   💡 FIX: Run 'python manage.py populate_leaderboards --force'"
            )

        if not results.exists():
            self.stdout.write(
                self.style.ERROR(
                    "   ❌ ISSUE: No ExamResults found - users need to complete exams first"
                )
            )

        # 6. Show what commands to run
        self.stdout.write(f"\n6. RECOMMENDED ACTIONS:")

        if not results.exists():
            self.stdout.write("   1. Have users complete some exams first")
            self.stdout.write(
                "   2. Check that exam completion triggers calculate_session_score task"
            )

        elif not leaderboards.exists() or not entries.exists():
            self.stdout.write("   1. Run: python manage.py populate_leaderboards")
            self.stdout.write("   2. If still empty, run with --force flag")

        else:
            self.stdout.write("   ✅ System looks healthy!")

        # 7. Test leaderboard API endpoint simulation
        self.stdout.write(f"\n7. API SIMULATION TEST:")

        if lb_types.exists():
            default_type = lb_types.filter(is_default=True).first() or lb_types.first()
            self.stdout.write(f"   Default leaderboard type: {default_type.name}")

            # Simulate API call
            from django.utils import timezone

            now = timezone.now()
            current_leaderboards = Leaderboard.objects.filter(
                leaderboard_type=default_type,
                period_start__lte=now,
                period_end__gte=now,
            )

            self.stdout.write(
                f"   Current leaderboards for this type: {current_leaderboards.count()}"
            )

            if current_leaderboards.exists():
                lb = current_leaderboards.first()
                self.stdout.write(
                    f"   Sample leaderboard: {lb.total_participants} participants"
                )
                self.stdout.write(f"   Top entries count: {len(lb.leaderboard_data)}")
            else:
                self.stdout.write(
                    "   No current leaderboards found - this explains empty frontend"
                )

        self.stdout.write(f"\n=== DIAGNOSTIC COMPLETE ===")


# Also create a simple populate command for immediate use
class Command(BaseCommand):
    help = "Quick populate leaderboards from existing exam results"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Force repopulation")

    def handle(self, *args, **options):
        # Quick diagnostic
        results_count = ExamResult.objects.count()
        leaderboards_count = Leaderboard.objects.count()
        entries_count = LeaderboardEntry.objects.count()

        self.stdout.write(
            f"Current state: {results_count} results, {leaderboards_count} leaderboards, {entries_count} entries"
        )

        if results_count == 0:
            self.stdout.write(
                self.style.ERROR(
                    "No exam results found. Users must complete exams first."
                )
            )
            return

        # Import and call the population task
        try:
            from apps.leaderboards.tasks import update_all_leaderboards

            self.stdout.write("Triggering leaderboard population...")

            # Call synchronously
            update_all_leaderboards()

            # Check results
            new_leaderboards = Leaderboard.objects.count()
            new_entries = LeaderboardEntry.objects.count()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Update complete! "
                    f"Leaderboards: {leaderboards_count} → {new_leaderboards}, "
                    f"Entries: {entries_count} → {new_entries}"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))

            # Try alternative approach - direct population
            self.stdout.write("Trying direct population approach...")
            self._direct_populate(options.get("force", False))

    def _direct_populate(self, force=False):
        """Direct population method as fallback."""
        from django.utils import timezone
        from datetime import timedelta
        import statistics

        now = timezone.now()

        # Get recent results (last 30 days)
        recent_results = ExamResult.objects.filter(
            created_at__gte=now - timedelta(days=30)
        ).select_related("user", "exam")

        if not recent_results.exists():
            self.stdout.write("No recent results to populate from")
            return

        # Get default leaderboard type
        lb_type = LeaderboardType.objects.filter(
            scope="exam", period="weekly", exam_type_filter="scheduled", is_active=True
        ).first()

        if not lb_type:
            self.stdout.write("No suitable leaderboard type found")
            return

        # Calculate current period
        days_since_monday = now.weekday()
        period_start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        period_end = period_start + timedelta(days=7)

        # Group results by exam
        from collections import defaultdict

        exams_data = defaultdict(list)

        for result in recent_results:
            if result.exam.exam_type == "scheduled":  # Only scheduled for default
                exams_data[result.exam].append(result)

        created_count = 0

        for exam, results in exams_data.items():
            if len(results) < 2:  # Skip exams with too few results
                continue

            # Create/get leaderboard
            leaderboard, created = Leaderboard.objects.get_or_create(
                leaderboard_type=lb_type,
                exam=exam,
                period_start=period_start,
                period_end=period_end,
                defaults={"subject": None, "chapter": None},
            )

            if not created and not force:
                continue  # Skip existing unless forced

            # Clear existing entries if forcing or newly created
            if force or created:
                leaderboard.entries.all().delete()

            # Get best score per user
            user_scores = {}
            for result in results:
                user_id = result.user.id
                if (
                    user_id not in user_scores
                    or result.percentage_score > user_scores[user_id]["score"]
                ):
                    user_scores[user_id] = {
                        "user": result.user,
                        "score": result.percentage_score,
                        "result": result,
                    }

            # Create entries
            sorted_users = sorted(
                user_scores.values(), key=lambda x: x["score"], reverse=True
            )
            entries = []
            leaderboard_data = []

            for rank, user_data in enumerate(sorted_users, 1):
                user = user_data["user"]
                result = user_data["result"]

                badges = []
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

                entry = LeaderboardEntry(
                    leaderboard=leaderboard,
                    user=user,
                    rank=rank,
                    score=result.percentage_score,
                    total_exams=1,
                    total_questions=result.total_questions,
                    correct_answers=result.correct_answers,
                    average_score=result.percentage_score,
                    best_score=result.percentage_score,
                    total_time_minutes=result.time_taken_minutes,
                    consistency_score=100.0,
                    performance_trend="new",
                    badges=badges,
                )
                entries.append(entry)

                leaderboard_data.append(
                    {
                        "user_id": str(user.id),
                        "user_name": user.get_full_name(),
                        "rank": rank,
                        "score": result.percentage_score,
                        "total_exams": 1,
                    }
                )

            # Bulk create
            LeaderboardEntry.objects.bulk_create(entries, ignore_conflicts=True)

            # Update leaderboard
            leaderboard.total_participants = len(entries)
            leaderboard.leaderboard_data = leaderboard_data
            leaderboard.save()

            created_count += len(entries)
            self.stdout.write(f"  Populated {exam.title}: {len(entries)} entries")

        self.stdout.write(
            self.style.SUCCESS(
                f"Direct population complete: {created_count} entries created"
            )
        )
