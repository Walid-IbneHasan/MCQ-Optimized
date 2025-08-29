from mcq_platform.celery import shared_task
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
        elif lb_type.period == "monthly":
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = (
                period_start.replace(month=period_start.month + 1)
                if period_start.month < 12
                else period_start.replace(year=period_start.year + 1, month=1)
            )
            period_end = next_month
        elif lb_type.period == "yearly":
            period_start = now.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            period_end = period_start.replace(year=period_start.year + 1)
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


def update_global_leaderboard(lb_type, period_start, period_end):
    """Update global leaderboard."""

    # Get or create leaderboard
    leaderboard, created = Leaderboard.objects.get_or_create(
        leaderboard_type=lb_type,
        period_start=period_start,
        period_end=period_end,
        defaults={"subject": None, "chapter": None, "exam": None},
    )

    # Get all users who took exams in this period
    exam_results = ExamResult.objects.filter(
        created_at__gte=period_start, created_at__lt=period_end
    )

    if lb_type.period == "all_time":
        exam_results = ExamResult.objects.all()

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

    # Calculate scores based on method
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
            # Simple weighted average (more recent scores have higher weight)
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

    # Sort by score (descending)
    user_scores.sort(key=lambda x: x["score"], reverse=True)

    # Limit entries if specified
    if lb_type.max_entries > 0:
        user_scores = user_scores[: lb_type.max_entries]

    # Create/update leaderboard entries
    LeaderboardEntry.objects.filter(leaderboard=leaderboard).delete()

    entries = []
    leaderboard_data = []

    for rank, user_data in enumerate(user_scores, 1):
        user = user_data["user"]

        # Calculate performance trend and achievements
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

        # Add to cached leaderboard data
        leaderboard_data.append(
            {
                "user_id": str(user.id),
                "user_name": user.full_name,
                "rank": rank,
                "score": user_data["score"],
                "total_exams": user_data["total_exams"],
            }
        )

    # Bulk create entries
    LeaderboardEntry.objects.bulk_create(entries)

    # Update leaderboard
    leaderboard.total_participants = len(entries)
    leaderboard.leaderboard_data = leaderboard_data
    leaderboard.save(
        update_fields=["total_participants", "leaderboard_data", "last_updated"]
    )

    # Clear cache
    redis_client.delete(f"leaderboard:{leaderboard.id}")

    logger.info(
        f"Updated global leaderboard {leaderboard.id} with {len(entries)} entries"
    )


def update_subject_leaderboards(lb_type, period_start, period_end):
    """Update subject-wise leaderboards."""
    subjects = Subject.objects.filter(is_active=True)

    for subject in subjects:
        # Get or create leaderboard for this subject
        leaderboard, created = Leaderboard.objects.get_or_create(
            leaderboard_type=lb_type,
            subject=subject,
            period_start=period_start,
            period_end=period_end,
            defaults={"chapter": None, "exam": None},
        )

        # Get results for this subject in the period
        exam_results = ExamResult.objects.filter(
            exam__chapters__subject=subject,
            created_at__gte=period_start,
            created_at__lt=period_end,
        ).distinct()

        if lb_type.period == "all_time":
            exam_results = ExamResult.objects.filter(
                exam__chapters__subject=subject
            ).distinct()

        # Process similar to global leaderboard
        _process_leaderboard_entries(leaderboard, exam_results, lb_type)


def update_chapter_leaderboards(lb_type, period_start, period_end):
    """Update chapter-wise leaderboards."""
    chapters = Chapter.objects.filter(is_active=True)

    for chapter in chapters:
        leaderboard, created = Leaderboard.objects.get_or_create(
            leaderboard_type=lb_type,
            chapter=chapter,
            period_start=period_start,
            period_end=period_end,
            defaults={"subject": None, "exam": None},
        )

        exam_results = ExamResult.objects.filter(
            exam__chapters=chapter,
            created_at__gte=period_start,
            created_at__lt=period_end,
        ).distinct()

        if lb_type.period == "all_time":
            exam_results = ExamResult.objects.filter(exam__chapters=chapter).distinct()

        _process_leaderboard_entries(leaderboard, exam_results, lb_type)


def update_exam_leaderboards(lb_type, period_start, period_end):
    """Update exam-specific leaderboards."""
    # Get exams that had sessions in this period
    active_exams = Exam.objects.filter(
        sessions__created_at__gte=period_start,
        sessions__created_at__lt=period_end,
        is_active=True,
    ).distinct()

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

    # Calculate scores and create entries (similar to global leaderboard)
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
                "user_name": user.full_name,
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
