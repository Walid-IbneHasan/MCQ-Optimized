# apps/leaderboards/tasks.py - COMPLETE REPLACEMENT
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.db.models import Avg, Sum, Max, Count, Q
from datetime import timedelta
from .models import LeaderboardType, Leaderboard, LeaderboardEntry
from apps.results.models import ExamResult
from apps.exams.models import Exam
import logging

logger = logging.getLogger(__name__)


def get_period_dates(period_type):
    """Calculate start and end dates for a leaderboard period."""
    now = timezone.now()

    if period_type == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

    elif period_type == "weekly":
        # Start from Monday of current week
        days_since_monday = now.weekday()
        start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(days=7)

    elif period_type == "biweekly":
        days_since_monday = now.weekday()
        start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(days=14)

    elif period_type == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end = start.replace(year=now.year + 1, month=1)
        else:
            end = start.replace(month=now.month + 1)

    elif period_type == "quarterly":
        quarter = (now.month - 1) // 3
        start_month = quarter * 3 + 1
        start = now.replace(
            month=start_month, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_month = start_month + 3
        if end_month > 12:
            end = start.replace(year=start.year + 1, month=end_month - 12)
        else:
            end = start.replace(month=end_month)

    elif period_type == "yearly":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=now.year + 1)

    else:  # all_time
        start = timezone.datetime(2020, 1, 1, tzinfo=timezone.get_current_timezone())
        end = now + timedelta(days=365)

    return start, end


@shared_task
def update_user_leaderboard_entries(user_id):
    """
    Update leaderboards for a specific user after they complete an exam.
    This is called automatically from calculate_session_score.
    """
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = User.objects.get(id=user_id)
        logger.info(f"[LEADERBOARD] Updating entries for user: {user.phone_number}")

        # Get all active leaderboard types
        leaderboard_types = LeaderboardType.objects.filter(is_active=True)
        updated_count = 0

        for lb_type in leaderboard_types:
            try:
                # Get or create leaderboard for current period
                period_start, period_end = get_period_dates(lb_type.period)

                # Handle exam-specific leaderboards differently
                if lb_type.scope == "exam":
                    # Get user's recent results for this exam type
                    exam_type = lb_type.exam_type_filter
                    if exam_type == "all":
                        results = ExamResult.objects.filter(
                            user=user,
                            created_at__gte=period_start,
                            created_at__lt=period_end,
                        )
                    else:
                        results = ExamResult.objects.filter(
                            user=user,
                            exam__exam_type=exam_type,
                            created_at__gte=period_start,
                            created_at__lt=period_end,
                        )

                    # Update leaderboard for each unique exam
                    exams = results.values_list("exam", flat=True).distinct()
                    for exam_id in exams:
                        exam = Exam.objects.get(id=exam_id)
                        _update_single_exam_leaderboard(
                            lb_type, exam, period_start, period_end, user
                        )
                        updated_count += 1

                else:
                    # Global, subject, or chapter leaderboards
                    _update_single_leaderboard(lb_type, period_start, period_end, user)
                    updated_count += 1

            except Exception as e:
                logger.error(
                    f"[LEADERBOARD] Error updating {lb_type.name} for user {user_id}: {str(e)}"
                )
                continue

        logger.info(
            f"[LEADERBOARD] Updated {updated_count} leaderboard types for user {user_id}"
        )
        return {"success": True, "updated": updated_count}

    except Exception as e:
        logger.error(
            f"[LEADERBOARD] Error in update_user_leaderboard_entries for {user_id}: {str(e)}"
        )
        raise


@shared_task
def update_exam_specific_leaderboards(exam_id):
    """
    Update all leaderboards for a specific exam.
    Called automatically when any user completes an exam.
    """
    try:
        exam = Exam.objects.get(id=exam_id)
        logger.info(f"[LEADERBOARD] Updating leaderboards for exam: {exam.title}")

        # Get leaderboard types for this exam type
        exam_type = exam.exam_type
        leaderboard_types = LeaderboardType.objects.filter(
            scope="exam",
            is_active=True,
        ).filter(Q(exam_type_filter=exam_type) | Q(exam_type_filter="all"))

        updated_count = 0

        for lb_type in leaderboard_types:
            try:
                period_start, period_end = get_period_dates(lb_type.period)
                _update_single_exam_leaderboard(lb_type, exam, period_start, period_end)
                updated_count += 1
            except Exception as e:
                logger.error(
                    f"[LEADERBOARD] Error updating {lb_type.name} for exam {exam_id}: {str(e)}"
                )
                continue

        logger.info(
            f"[LEADERBOARD] Updated {updated_count} leaderboards for exam {exam_id}"
        )
        return {"success": True, "updated": updated_count}

    except Exception as e:
        logger.error(
            f"[LEADERBOARD] Error in update_exam_specific_leaderboards for {exam_id}: {str(e)}"
        )
        raise


def _update_single_exam_leaderboard(
    lb_type, exam, period_start, period_end, specific_user=None
):
    """
    Update a single exam-specific leaderboard.
    If specific_user is provided, only update that user's entry.
    """
    # Get or create leaderboard
    leaderboard, created = Leaderboard.objects.get_or_create(
        leaderboard_type=lb_type,
        exam=exam,
        period_start=period_start,
        period_end=period_end,
        defaults={
            "subject": None,
            "chapter": None,
            "total_participants": 0,
        },
    )

    if created:
        logger.info(
            f"[LEADERBOARD] Created new leaderboard: {lb_type.name} for {exam.title}"
        )

    # Get results for this exam in this period
    results_query = ExamResult.objects.filter(
        exam=exam,
        created_at__gte=period_start,
        created_at__lt=period_end,
    ).select_related("user")

    # If updating specific user, filter to their results
    if specific_user:
        results_query = results_query.filter(user=specific_user)

    # Calculate user scores (best score per user)
    user_scores = {}
    for result in results_query:
        user_id = result.user.id
        if user_id not in user_scores:
            user_scores[user_id] = {
                "user": result.user,
                "best_score": result.percentage_score,
                "total_attempts": 1,
                "total_correct": result.correct_answers,
                "total_questions": result.total_questions,
                "total_time": result.time_taken_minutes,
            }
        else:
            user_scores[user_id]["best_score"] = max(
                user_scores[user_id]["best_score"], result.percentage_score
            )
            user_scores[user_id]["total_attempts"] += 1
            user_scores[user_id]["total_correct"] += result.correct_answers
            user_scores[user_id]["total_questions"] += result.total_questions
            user_scores[user_id]["total_time"] += result.time_taken_minutes

    if not user_scores:
        logger.info(f"[LEADERBOARD] No results found for {exam.title} in period")
        return

    # If updating specific user, we need all users to calculate correct rank
    if specific_user:
        # Get all other users' scores
        all_results = (
            ExamResult.objects.filter(
                exam=exam,
                created_at__gte=period_start,
                created_at__lt=period_end,
            )
            .exclude(user=specific_user)
            .select_related("user")
        )

        for result in all_results:
            user_id = result.user.id
            if user_id not in user_scores:
                user_scores[user_id] = {
                    "user": result.user,
                    "best_score": result.percentage_score,
                    "total_attempts": 1,
                    "total_correct": result.correct_answers,
                    "total_questions": result.total_questions,
                    "total_time": result.time_taken_minutes,
                }
            else:
                user_scores[user_id]["best_score"] = max(
                    user_scores[user_id]["best_score"], result.percentage_score
                )

    # Sort by best score
    sorted_users = sorted(
        user_scores.values(), key=lambda x: x["best_score"], reverse=True
    )

    # Update entries
    with transaction.atomic():
        if specific_user:
            # Only update specific user's entry
            user_data = next(
                (u for u in sorted_users if u["user"].id == specific_user.id), None
            )
            if user_data:
                rank = next(
                    (
                        i + 1
                        for i, u in enumerate(sorted_users)
                        if u["user"].id == specific_user.id
                    ),
                    len(sorted_users) + 1,
                )

                # Get previous rank
                try:
                    existing = LeaderboardEntry.objects.get(
                        leaderboard=leaderboard, user=specific_user
                    )
                    prev_rank = existing.rank
                except LeaderboardEntry.DoesNotExist:
                    prev_rank = None

                # Create or update entry
                LeaderboardEntry.objects.update_or_create(
                    leaderboard=leaderboard,
                    user=specific_user,
                    defaults={
                        "rank": rank,
                        "previous_rank": prev_rank,
                        "rank_change": (prev_rank - rank) if prev_rank else 0,
                        "score": user_data["best_score"],
                        "total_exams": user_data["total_attempts"],
                        "total_questions": user_data["total_questions"],
                        "correct_answers": user_data["total_correct"],
                        "best_score": user_data["best_score"],
                        "average_score": user_data[
                            "best_score"
                        ],  # For single exam, same as best
                        "total_time_minutes": user_data["total_time"],
                        "performance_trend": (
                            "improving" if (prev_rank and prev_rank > rank) else "new"
                        ),
                    },
                )

                logger.info(
                    f"[LEADERBOARD] Updated {specific_user.phone_number} rank to #{rank} in {exam.title}"
                )

        else:
            # Rebuild all entries
            LeaderboardEntry.objects.filter(leaderboard=leaderboard).delete()

            entries_to_create = []
            leaderboard_data = []

            for rank, user_data in enumerate(sorted_users, 1):
                user = user_data["user"]

                # Determine badges
                badges = []
                if rank == 1:
                    badges.append(
                        {
                            "name": "Gold Medal",
                            "description": "1st Place",
                            "color": "gold",
                        }
                    )
                elif rank == 2:
                    badges.append(
                        {
                            "name": "Silver Medal",
                            "description": "2nd Place",
                            "color": "silver",
                        }
                    )
                elif rank == 3:
                    badges.append(
                        {
                            "name": "Bronze Medal",
                            "description": "3rd Place",
                            "color": "bronze",
                        }
                    )
                elif rank <= 10:
                    badges.append(
                        {
                            "name": "Top 10",
                            "description": "Top 10 Performer",
                            "color": "blue",
                        }
                    )

                entries_to_create.append(
                    LeaderboardEntry(
                        leaderboard=leaderboard,
                        user=user,
                        rank=rank,
                        score=user_data["best_score"],
                        total_exams=user_data["total_attempts"],
                        total_questions=user_data["total_questions"],
                        correct_answers=user_data["total_correct"],
                        best_score=user_data["best_score"],
                        average_score=user_data["best_score"],
                        total_time_minutes=user_data["total_time"],
                        performance_trend="new",
                        badges=badges,
                    )
                )

                # Add to cached data (top 100 only)
                if rank <= 100:
                    leaderboard_data.append(
                        {
                            "rank": rank,
                            "user_id": str(user.id),
                            "user_name": user.get_full_name(),
                            "score": round(user_data["best_score"], 2),
                            "total_exams": user_data["total_attempts"],
                        }
                    )

            # Bulk create
            LeaderboardEntry.objects.bulk_create(entries_to_create)

            # Update leaderboard metadata
            leaderboard.total_participants = len(sorted_users)
            leaderboard.leaderboard_data = leaderboard_data
            leaderboard.last_updated = timezone.now()
            leaderboard.save()

            logger.info(
                f"[LEADERBOARD] Created {len(entries_to_create)} entries for {exam.title}"
            )


def _update_single_leaderboard(lb_type, period_start, period_end, specific_user=None):
    """Update a global/subject/chapter leaderboard."""
    # Similar logic but for non-exam-specific leaderboards
    # For now, we'll focus on exam-specific since that's what you're using
    pass


@shared_task
def update_all_leaderboards():
    """
    Periodic task to recalculate all leaderboards.
    Run this hourly or daily via Celery Beat.
    """
    try:
        logger.info("[LEADERBOARD] Starting full leaderboard update")

        leaderboard_types = LeaderboardType.objects.filter(is_active=True, scope="exam")
        total_updated = 0

        for lb_type in leaderboard_types:
            try:
                period_start, period_end = get_period_dates(lb_type.period)

                # Get all exams with results in this period
                exam_type = lb_type.exam_type_filter

                results_filter = {
                    "created_at__gte": period_start,
                    "created_at__lt": period_end,
                }

                if exam_type != "all":
                    results_filter["exam__exam_type"] = exam_type

                exams_with_results = (
                    ExamResult.objects.filter(**results_filter)
                    .values_list("exam", flat=True)
                    .distinct()
                )

                for exam_id in exams_with_results:
                    exam = Exam.objects.get(id=exam_id)
                    _update_single_exam_leaderboard(
                        lb_type, exam, period_start, period_end
                    )
                    total_updated += 1

            except Exception as e:
                logger.error(f"[LEADERBOARD] Error updating {lb_type.name}: {str(e)}")
                continue

        logger.info(
            f"[LEADERBOARD] Full update complete: {total_updated} leaderboards updated"
        )
        return {"success": True, "updated": total_updated}

    except Exception as e:
        logger.error(f"[LEADERBOARD] Error in update_all_leaderboards: {str(e)}")
        raise
