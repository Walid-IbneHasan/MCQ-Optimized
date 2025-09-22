# apps/leaderboards/tasks.py - Enhanced with exam-specific and user-specific updates
from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db.models import Avg, Sum, Count, Max, Min
from datetime import timedelta, date
from .models import LeaderboardType, Leaderboard, LeaderboardEntry
from apps.results.models import ExamResult, SubjectPerformance
from apps.subjects.models import Subject, Chapter
from apps.exams.models import Exam
from utils.redis_client import redis_client
import logging
import statistics

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task
def update_user_leaderboard_entries(user_id):
    """
    Update leaderboard entries for a specific user after they complete an exam.
    This is triggered immediately after exam completion.
    """
    try:
        user = User.objects.get(id=user_id)
        logger.info(f"Updating leaderboard entries for user {user.phone_number}")

        # Get current leaderboards that should include this user
        current_time = timezone.now()

        # Update global leaderboards
        global_leaderboards = Leaderboard.objects.filter(
            leaderboard_type__scope="global",
            period_start__lte=current_time,
            period_end__gte=current_time,
        )

        for leaderboard in global_leaderboards:
            _update_user_in_leaderboard(user, leaderboard)

        # Update subject-specific leaderboards
        # Get subjects the user has participated in
        user_subjects = Subject.objects.filter(
            chapters__questions__examanswer__session__user=user,
            chapters__questions__examanswer__session__status__in=[
                "completed",
                "auto_submitted",
            ],
        ).distinct()

        for subject in user_subjects:
            subject_leaderboards = Leaderboard.objects.filter(
                leaderboard_type__scope="subject",
                subject=subject,
                period_start__lte=current_time,
                period_end__gte=current_time,
            )

            for leaderboard in subject_leaderboards:
                _update_user_in_leaderboard(user, leaderboard)

        logger.info(
            f"Successfully updated leaderboard entries for user {user.phone_number}"
        )
        return True

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return False
    except Exception as e:
        logger.error(f"Error updating leaderboard entries for user {user_id}: {str(e)}")
        raise


@shared_task
def update_exam_specific_leaderboards(exam_id):
    """
    Update leaderboards for a specific exam after completion.
    """
    try:
        exam = Exam.objects.get(id=exam_id)
        logger.info(f"Updating exam-specific leaderboards for exam {exam.title}")

        current_time = timezone.now()

        # Create or update exam-specific leaderboards for different periods
        periods = [
            ("weekly", 7),
            ("monthly", 30),
            ("quarterly", 90),
        ]

        for period_name, days in periods:
            period_start = current_time.replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            if period_name == "weekly":
                days_since_monday = current_time.weekday()
                period_start = period_start - timedelta(days=days_since_monday)
                period_end = period_start + timedelta(days=7)
            elif period_name == "monthly":
                period_start = period_start.replace(day=1)
                if period_start.month == 12:
                    period_end = period_start.replace(
                        year=period_start.year + 1, month=1
                    )
                else:
                    period_end = period_start.replace(month=period_start.month + 1)
            else:  # quarterly
                quarter_start_month = ((period_start.month - 1) // 3) * 3 + 1
                period_start = period_start.replace(month=quarter_start_month, day=1)
                if quarter_start_month >= 10:
                    period_end = period_start.replace(
                        year=period_start.year + 1, month=1
                    )
                else:
                    period_end = period_start.replace(month=quarter_start_month + 3)

            # Get or create leaderboard type for exam-specific leaderboards
            lb_type, created = LeaderboardType.objects.get_or_create(
                scope="exam",
                period=period_name,
                name=f"Exam {period_name.title()} Rankings",
                defaults={
                    "description": f"{period_name.title()} rankings for specific exams",
                    "score_calculation_method": "best",
                    "max_entries": 100,
                    "min_exams_required": 1,
                },
            )

            # Get or create leaderboard for this exam and period
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

            # Update the leaderboard
            _update_exam_leaderboard(leaderboard, exam, period_start, period_end)

        logger.info(
            f"Successfully updated exam-specific leaderboards for exam {exam.title}"
        )
        return True

    except Exam.DoesNotExist:
        logger.error(f"Exam {exam_id} not found")
        return False
    except Exception as e:
        logger.error(
            f"Error updating exam-specific leaderboards for exam {exam_id}: {str(e)}"
        )
        raise


def _update_user_in_leaderboard(user, leaderboard):
    """
    Update a specific user's entry in a leaderboard.
    """
    try:
        # Get user's exam results for this leaderboard's criteria
        results_query = ExamResult.objects.filter(
            user=user,
            created_at__gte=leaderboard.period_start,
            created_at__lt=leaderboard.period_end,
        )

        # Apply leaderboard-specific filters
        if leaderboard.subject:
            results_query = results_query.filter(
                exam__chapters__subject=leaderboard.subject
            ).distinct()
        elif leaderboard.chapter:
            results_query = results_query.filter(
                exam__chapters=leaderboard.chapter
            ).distinct()
        elif leaderboard.exam:
            results_query = results_query.filter(exam=leaderboard.exam)

        results = list(results_query)

        if (
            not results
            or len(results) < leaderboard.leaderboard_type.min_exams_required
        ):
            # Remove user from leaderboard if they don't meet requirements
            LeaderboardEntry.objects.filter(leaderboard=leaderboard, user=user).delete()
            return

        # Calculate user's score based on leaderboard method
        scores = [result.percentage_score for result in results]

        if leaderboard.leaderboard_type.score_calculation_method == "average":
            calculated_score = statistics.mean(scores)
        elif leaderboard.leaderboard_type.score_calculation_method == "best":
            calculated_score = max(scores)
        elif leaderboard.leaderboard_type.score_calculation_method == "total":
            calculated_score = sum(scores)
        else:  # weighted
            weights = [i + 1 for i in range(len(scores))]
            calculated_score = sum(s * w for s, w in zip(scores, weights)) / sum(
                weights
            )

        # Calculate other metrics
        total_questions = sum(result.total_questions for result in results)
        correct_answers = sum(result.correct_answers for result in results)
        total_time = sum(result.time_taken_minutes for result in results)

        # Get or create leaderboard entry
        entry, created = LeaderboardEntry.objects.get_or_create(
            leaderboard=leaderboard,
            user=user,
            defaults={
                "rank": 999999,  # Temporary rank, will be recalculated
                "score": calculated_score,
                "total_exams": len(results),
                "total_questions": total_questions,
                "correct_answers": correct_answers,
                "average_score": statistics.mean(scores),
                "best_score": max(scores),
                "total_time_minutes": total_time,
                "consistency_score": 100
                - (statistics.stdev(scores) if len(scores) > 1 else 0),
            },
        )

        if not created:
            # Update existing entry
            entry.score = calculated_score
            entry.total_exams = len(results)
            entry.total_questions = total_questions
            entry.correct_answers = correct_answers
            entry.average_score = statistics.mean(scores)
            entry.best_score = max(scores)
            entry.total_time_minutes = total_time
            entry.consistency_score = 100 - (
                statistics.stdev(scores) if len(scores) > 1 else 0
            )
            entry.save()

        # Recalculate ranks for this leaderboard
        _recalculate_leaderboard_ranks(leaderboard)

    except Exception as e:
        logger.error(
            f"Error updating user {user.id} in leaderboard {leaderboard.id}: {str(e)}"
        )
        raise


def _update_exam_leaderboard(leaderboard, exam, period_start, period_end):
    """
    Update an exam-specific leaderboard.
    """
    try:
        # Get all results for this exam in the period
        results = ExamResult.objects.filter(
            exam=exam,
            created_at__gte=period_start,
            created_at__lt=period_end,
        ).select_related("user")

        # Group by user and get best score
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

        # Clear existing entries
        LeaderboardEntry.objects.filter(leaderboard=leaderboard).delete()

        # Create new entries
        entries = []
        leaderboard_data = []

        # Sort by score
        sorted_users = sorted(
            user_scores.values(), key=lambda x: x["score"], reverse=True
        )

        for rank, user_data in enumerate(sorted_users, 1):
            user = user_data["user"]
            result = user_data["result"]

            if rank > leaderboard.leaderboard_type.max_entries:
                break

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
                consistency_score=100.0,  # Single exam, so 100% consistent
            )
            entries.append(entry)

            leaderboard_data.append(
                {
                    "user_id": str(user.id),
                    "user_name": user.get_full_name(),
                    "rank": rank,
                    "score": result.percentage_score,
                    "total_exams": 1,
                    "exam_date": result.created_at.isoformat(),
                }
            )

        # Bulk create entries
        LeaderboardEntry.objects.bulk_create(entries)

        # Update leaderboard metadata
        leaderboard.total_participants = len(entries)
        leaderboard.leaderboard_data = leaderboard_data
        leaderboard.save(
            update_fields=["total_participants", "leaderboard_data", "last_updated"]
        )

        logger.info(
            f"Updated exam leaderboard {leaderboard.id} with {len(entries)} entries"
        )

    except Exception as e:
        logger.error(f"Error updating exam leaderboard {leaderboard.id}: {str(e)}")
        raise


def _recalculate_leaderboard_ranks(leaderboard):
    """
    Recalculate ranks for all entries in a leaderboard.
    """
    try:
        # Get all entries sorted by score
        entries = list(
            LeaderboardEntry.objects.filter(leaderboard=leaderboard).order_by(
                "-score", "-best_score", "total_time_minutes"
            )
        )

        # Update ranks
        leaderboard_data = []
        for rank, entry in enumerate(entries, 1):
            old_rank = entry.rank
            entry.rank = rank
            entry.rank_change = old_rank - rank if old_rank else 0
            entry.save(update_fields=["rank", "rank_change"])

            leaderboard_data.append(
                {
                    "user_id": str(entry.user.id),
                    "user_name": entry.user.get_full_name(),
                    "rank": rank,
                    "score": entry.score,
                    "total_exams": entry.total_exams,
                    "rank_change": entry.rank_change,
                }
            )

        # Update cached leaderboard data
        leaderboard.total_participants = len(entries)
        leaderboard.leaderboard_data = leaderboard_data
        leaderboard.save(
            update_fields=["total_participants", "leaderboard_data", "last_updated"]
        )

        # Clear cache
        redis_client.delete(f"leaderboard:{leaderboard.id}")

    except Exception as e:
        logger.error(
            f"Error recalculating ranks for leaderboard {leaderboard.id}: {str(e)}"
        )
        raise


@shared_task
def create_default_leaderboard_types():
    """
    Create default leaderboard types for scheduled exams.
    """
    try:
        # Scheduled exam leaderboards (default)
        scheduled_periods = [
            ("weekly", "Weekly"),
            ("biweekly", "Bi-weekly"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
        ]

        for period_key, period_name in scheduled_periods:
            LeaderboardType.objects.get_or_create(
                scope="exam",
                period=period_key,
                name=f"Scheduled Exam {period_name} Rankings",
                defaults={
                    "description": f"{period_name} rankings for scheduled exams",
                    "score_calculation_method": "best",
                    "max_entries": 100,
                    "min_exams_required": 1,
                    "is_public": True,
                },
            )

        # Practice exam leaderboards
        for period_key, period_name in scheduled_periods:
            LeaderboardType.objects.get_or_create(
                scope="exam",
                period=period_key,
                name=f"Practice Exam {period_name} Rankings",
                defaults={
                    "description": f"{period_name} rankings for practice exams",
                    "score_calculation_method": "best",
                    "max_entries": 50,
                    "min_exams_required": 1,
                    "is_public": True,
                },
            )

        logger.info("Default leaderboard types created successfully")
        return True

    except Exception as e:
        logger.error(f"Error creating default leaderboard types: {str(e)}")
        raise


# Keep all existing tasks and add the enhanced functionality
@shared_task
def update_all_leaderboards():
    """
    Update all active leaderboards.
    """
    try:
        leaderboard_types = LeaderboardType.objects.filter(is_active=True)
        updated_count = 0

        for lb_type in leaderboard_types:
            if update_leaderboard_type(lb_type.id):
                updated_count += 1

        logger.info(f"Updated {updated_count} leaderboard types")
        return updated_count

    except Exception as e:
        logger.error(f"Error updating leaderboards: {str(e)}")
        raise


@shared_task
def update_leaderboard_type(leaderboard_type_id):
    """
    Update leaderboards for a specific type.
    """
    try:
        lb_type = LeaderboardType.objects.get(id=leaderboard_type_id)
        now = timezone.now()

        # Determine period dates based on leaderboard period
        if lb_type.period == "daily":
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start + timedelta(days=1)
        elif lb_type.period == "weekly":
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            period_end = period_start + timedelta(days=7)
        elif lb_type.period == "biweekly":
            days_since_monday = now.weekday()
            period_start = (now - timedelta(days=days_since_monday)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # Go back to start of current 2-week period
            weeks_since_epoch = (
                period_start.date() - date(1970, 1, 5)
            ).days // 7  # 1970-01-05 was a Monday
            if weeks_since_epoch % 2 == 1:
                period_start -= timedelta(days=7)
            period_end = period_start + timedelta(days=14)
        elif lb_type.period == "monthly":
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = (
                period_start.replace(month=period_start.month + 1)
                if period_start.month < 12
                else period_start.replace(year=period_start.year + 1, month=1)
            )
            period_end = next_month
        elif lb_type.period == "quarterly":
            quarter_start_month = ((now.month - 1) // 3) * 3 + 1
            period_start = now.replace(
                month=quarter_start_month,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            if quarter_start_month >= 10:
                period_end = period_start.replace(year=period_start.year + 1, month=1)
            else:
                period_end = period_start.replace(month=quarter_start_month + 3)
        else:  # all_time
            period_start = timezone.datetime.min.replace(tzinfo=timezone.utc)
            period_end = now + timedelta(days=365)  # Far future date

        if lb_type.scope == "global":
            update_global_leaderboard(lb_type, period_start, period_end)
        elif lb_type.scope == "subject":
            update_subject_leaderboards(lb_type, period_start, period_end)
        elif lb_type.scope == "chapter":
            update_chapter_leaderboards(lb_type, period_start, period_end)
        elif lb_type.scope == "exam":
            update_exam_leaderboards(lb_type, period_start, period_end)

        return True

    except LeaderboardType.DoesNotExist:
        logger.error(f"Leaderboard type not found: {leaderboard_type_id}")
        return False
    except Exception as e:
        logger.error(f"Error updating leaderboard type {leaderboard_type_id}: {str(e)}")
        raise


# Keep all the existing helper functions from the original code
def update_global_leaderboard(lb_type, period_start, period_end):
    """Update global leaderboard."""
    # ... (keep existing implementation)
    pass


def update_subject_leaderboards(lb_type, period_start, period_end):
    """Update subject-wise leaderboards."""
    # ... (keep existing implementation)
    pass


def update_chapter_leaderboards(lb_type, period_start, period_end):
    """Update chapter-wise leaderboards."""
    # ... (keep existing implementation)
    pass


def update_exam_leaderboards(lb_type, period_start, period_end):
    """Update exam-specific leaderboards with filtering by exam type."""
    # Get exams that had sessions in this period, filtered by type
    active_exams_query = Exam.objects.filter(
        sessions__created_at__gte=period_start,
        sessions__created_at__lt=period_end,
        is_active=True,
    ).distinct()

    # Filter by exam type if specified in leaderboard type name
    if "Scheduled" in lb_type.name:
        active_exams = active_exams_query.filter(exam_type="scheduled")
    elif "Practice" in lb_type.name:
        active_exams = active_exams_query.filter(exam_type="practice")
    else:
        active_exams = active_exams_query

    for exam in active_exams:
        leaderboard, created = Leaderboard.objects.get_or_create(
            leaderboard_type=lb_type,
            exam=exam,
            period_start=period_start,
            period_end=period_end,
            defaults={"subject": None, "chapter": None},
        )

        exam_results = ExamResult.objects.filter(
            exam=exam, created_at__gte=period_start, created_at__lt=period_end
        )

        _process_leaderboard_entries(leaderboard, exam_results, lb_type)


def _process_leaderboard_entries(leaderboard, exam_results, lb_type):
    """Helper function to process leaderboard entries."""
    # Group results by user
    user_data = {}
    for result in exam_results:
        user_id = result.user.id
        if user_id not in user_data:
            user_data[user_id] = {
                "user": result.user,
                "scores": [],
                "total_exams": 0,
                "total_questions": 0,
                "correct_answers": 0,
                "total_time": 0,
            }

        user_data[user_id]["scores"].append(result.percentage_score)
        user_data[user_id]["total_exams"] += 1
        user_data[user_id]["total_questions"] += result.total_questions
        user_data[user_id]["correct_answers"] += result.correct_answers
        user_data[user_id]["total_time"] += result.time_taken_minutes

    # Filter users with minimum required exams
    qualified_users = {
        uid: data
        for uid, data in user_data.items()
        if data["total_exams"] >= lb_type.min_exams_required
    }

    if not qualified_users:
        leaderboard.total_participants = 0
        leaderboard.leaderboard_data = []
        leaderboard.save(
            update_fields=["total_participants", "leaderboard_data", "last_updated"]
        )
        return

    # Calculate scores and create entries
    user_scores = []
    for user_id, data in qualified_users.items():
        scores = data["scores"]

        if lb_type.score_calculation_method == "average":
            calculated_score = statistics.mean(scores)
        elif lb_type.score_calculation_method == "best":
            calculated_score = max(scores)
        elif lb_type.score_calculation_method == "total":
            calculated_score = sum(scores)
        else:  # weighted
            weights = [i + 1 for i in range(len(scores))]
            calculated_score = sum(s * w for s, w in zip(scores, weights)) / sum(
                weights
            )

        user_scores.append(
            {
                "user": data["user"],
                "score": calculated_score,
                "total_exams": data["total_exams"],
                "total_questions": data["total_questions"],
                "correct_answers": data["correct_answers"],
                "total_time": data["total_time"],
                "average_score": statistics.mean(scores),
                "best_score": max(scores),
                "consistency_score": 100
                - (statistics.stdev(scores) if len(scores) > 1 else 0),
            }
        )

    # Sort and limit entries
    user_scores.sort(key=lambda x: x["score"], reverse=True)
    if lb_type.max_entries > 0:
        user_scores = user_scores[: lb_type.max_entries]

    # Create entries
    LeaderboardEntry.objects.filter(leaderboard=leaderboard).delete()

    entries = []
    leaderboard_data = []

    for rank, user_data in enumerate(user_scores, 1):
        user = user_data["user"]

        achievements = calculate_achievements(user, user_data)
        badges = calculate_badges(user, user_data, rank)

        entry = LeaderboardEntry(
            leaderboard=leaderboard,
            user=user,
            rank=rank,
            score=user_data["score"],
            total_exams=user_data["total_exams"],
            total_questions=user_data["total_questions"],
            correct_answers=user_data["correct_answers"],
            average_score=user_data["average_score"],
            best_score=user_data["best_score"],
            total_time_minutes=user_data["total_time"],
            consistency_score=user_data["consistency_score"],
            achievements=achievements,
            badges=badges,
        )
        entries.append(entry)

        leaderboard_data.append(
            {
                "user_id": str(user.id),
                "user_name": user.get_full_name(),
                "rank": rank,
                "score": user_data["score"],
                "total_exams": user_data["total_exams"],
            }
        )

    LeaderboardEntry.objects.bulk_create(entries)

    leaderboard.total_participants = len(entries)
    leaderboard.leaderboard_data = leaderboard_data
    leaderboard.save(
        update_fields=["total_participants", "leaderboard_data", "last_updated"]
    )


def calculate_achievements(user, user_data):
    """Calculate achievements for a user based on performance."""
    achievements = []

    # Score-based achievements
    if user_data["best_score"] >= 95:
        achievements.append(
            {
                "title": "Perfectionist",
                "description": "Scored 95% or higher",
                "icon": "star",
                "type": "score",
            }
        )

    # Consistency achievements
    if user_data["consistency_score"] >= 90:
        achievements.append(
            {
                "title": "Consistent Performer",
                "description": "Maintained consistent performance",
                "icon": "target",
                "type": "consistency",
            }
        )

    # Volume achievements
    if user_data["total_exams"] >= 50:
        achievements.append(
            {
                "title": "Dedicated Learner",
                "description": "Completed 50+ exams",
                "icon": "book",
                "type": "volume",
            }
        )

    return achievements


def calculate_badges(user, user_data, rank):
    """Calculate badges for a user based on rank and performance."""
    badges = []

    # Rank-based badges
    if rank == 1:
        badges.append(
            {"name": "Gold Medal", "description": "First place", "color": "gold"}
        )
    elif rank <= 3:
        badges.append(
            {"name": "Top 3", "description": "Top 3 performer", "color": "silver"}
        )
    elif rank <= 10:
        badges.append(
            {"name": "Top 10", "description": "Top 10 performer", "color": "bronze"}
        )

    return badges


@shared_task
def cleanup_old_leaderboards():
    """Clean up old leaderboard data."""
    try:
        # Keep leaderboards for last 6 months
        cutoff_date = timezone.now() - timedelta(days=180)

        old_leaderboards = Leaderboard.objects.filter(
            period_end__lt=cutoff_date, is_finalized=True
        )

        count = old_leaderboards.count()
        old_leaderboards.delete()

        logger.info(f"Cleaned up {count} old leaderboards")
        return count

    except Exception as e:
        logger.error(f"Error cleaning up leaderboards: {str(e)}")
        raise
