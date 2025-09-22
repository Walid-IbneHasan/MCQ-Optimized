# apps/exams/tasks.py - Updated to trigger analytics
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Q, Avg
from datetime import timedelta
from .models import Exam, ExamSession, ExamAnswer, ExamQuestion
from apps.questions.models import Question, QuestionOption
from apps.results.models import ExamResult
from apps.notifications.tasks import send_notification
from utils.redis_client import redis_client
import json
import logging
import random

logger = logging.getLogger(__name__)


@shared_task
def calculate_session_score(session_id):
    """
    Calculate score for an exam session and create ExamResult.
    This is the main function that should run after exam submission.
    """
    try:
        session = ExamSession.objects.select_related("exam", "user").get(id=session_id)

        # Get all answers for this session
        answers = ExamAnswer.objects.filter(session=session).select_related(
            "question", "selected_option"
        )

        total_marks = 0
        correct_answers = 0
        wrong_answers = 0
        unanswered = 0
        marks_obtained = 0
        negative_marks = 0

        # Calculate scores for each answer
        for answer in answers:
            question = answer.question
            total_marks += question.marks

            if answer.selected_option:
                if answer.selected_option.is_correct:
                    correct_answers += 1
                    marks_awarded = question.marks
                    marks_obtained += marks_awarded
                    answer.is_correct = True
                    answer.marks_awarded = marks_awarded
                else:
                    wrong_answers += 1
                    answer.is_correct = False

                    # Apply negative marking if enabled
                    if (
                        session.exam.negative_marking_enabled
                        and question.allow_negative_marking
                    ):
                        negative = question.negative_marks
                        marks_obtained -= negative
                        negative_marks += negative
                        answer.marks_awarded = -negative
                    else:
                        answer.marks_awarded = 0
            else:
                unanswered += 1
                answer.is_correct = False
                answer.marks_awarded = 0

            # Save the updated answer
            answer.save(update_fields=["is_correct", "marks_awarded"])

        # Calculate percentage
        percentage_score = (
            (marks_obtained / total_marks * 100) if total_marks > 0 else 0
        )
        is_passed = percentage_score >= session.exam.passing_percentage

        # Update session with final scores
        session.total_score = marks_obtained
        session.percentage_score = percentage_score
        session.is_passed = is_passed
        session.save(update_fields=["total_score", "percentage_score", "is_passed"])

        # Calculate grade
        def calculate_grade(percentage):
            if percentage >= 90:
                return "A+"
            elif percentage >= 85:
                return "A"
            elif percentage >= 80:
                return "A-"
            elif percentage >= 75:
                return "B+"
            elif percentage >= 70:
                return "B"
            elif percentage >= 65:
                return "B-"
            elif percentage >= 60:
                return "C+"
            elif percentage >= 55:
                return "C"
            elif percentage >= 50:
                return "C-"
            else:
                return "F"

        # Create or update ExamResult record
        from apps.results.models import ExamResult

        result, created = ExamResult.objects.update_or_create(
            session=session,
            defaults={
                "user": session.user,
                "exam": session.exam,
                "total_questions": answers.count(),
                "questions_attempted": correct_answers + wrong_answers,
                "correct_answers": correct_answers,
                "wrong_answers": wrong_answers,
                "unanswered_questions": unanswered,
                "total_marks": total_marks,
                "marks_obtained": marks_obtained,
                "negative_marks": negative_marks,
                "percentage_score": percentage_score,
                "is_passed": is_passed,
                "grade": calculate_grade(percentage_score),
                "time_taken_minutes": session.time_spent_seconds // 60,
                "time_taken_seconds": session.time_spent_seconds,
                "average_time_per_question": (
                    session.time_spent_seconds / answers.count()
                    if answers.count() > 0
                    else 0
                ),
                "accuracy_rate": (
                    (correct_answers / (correct_answers + wrong_answers) * 100)
                    if (correct_answers + wrong_answers) > 0
                    else 0
                ),
            },
        )

        # Calculate subject and chapter wise performance
        subject_scores = {}
        chapter_scores = {}
        difficulty_scores = {"easy": 0, "medium": 0, "hard": 0}

        for answer in answers:
            question = answer.question
            subject_name = question.chapter.subject.name
            chapter_name = question.chapter.name
            difficulty = question.difficulty

            # Subject-wise calculation
            if subject_name not in subject_scores:
                subject_scores[subject_name] = {
                    "total_marks": 0,
                    "obtained_marks": 0,
                    "questions": 0,
                    "correct": 0,
                }

            subject_scores[subject_name]["total_marks"] += question.marks
            subject_scores[subject_name]["obtained_marks"] += answer.marks_awarded
            subject_scores[subject_name]["questions"] += 1
            if answer.is_correct:
                subject_scores[subject_name]["correct"] += 1

            # Chapter-wise calculation
            chapter_key = f"{subject_name} - {chapter_name}"
            if chapter_key not in chapter_scores:
                chapter_scores[chapter_key] = {
                    "total_marks": 0,
                    "obtained_marks": 0,
                    "questions": 0,
                    "correct": 0,
                }

            chapter_scores[chapter_key]["total_marks"] += question.marks
            chapter_scores[chapter_key]["obtained_marks"] += answer.marks_awarded
            chapter_scores[chapter_key]["questions"] += 1
            if answer.is_correct:
                chapter_scores[chapter_key]["correct"] += 1

            # Difficulty-wise calculation
            if answer.is_correct:
                difficulty_scores[difficulty] += 1

        # Calculate percentages for subjects and chapters
        for subject_name in subject_scores:
            if subject_scores[subject_name]["total_marks"] > 0:
                subject_scores[subject_name]["percentage"] = (
                    subject_scores[subject_name]["obtained_marks"]
                    / subject_scores[subject_name]["total_marks"]
                    * 100
                )
            else:
                subject_scores[subject_name]["percentage"] = 0

        for chapter_key in chapter_scores:
            if chapter_scores[chapter_key]["total_marks"] > 0:
                chapter_scores[chapter_key]["percentage"] = (
                    chapter_scores[chapter_key]["obtained_marks"]
                    / chapter_scores[chapter_key]["total_marks"]
                    * 100
                )
            else:
                chapter_scores[chapter_key]["percentage"] = 0

        # Update result with detailed performance data
        result.subject_wise_scores = subject_scores
        result.chapter_wise_scores = chapter_scores
        result.difficulty_wise_scores = difficulty_scores

        # Generate weak and strong areas
        weak_areas = []
        strong_areas = []

        for subject, stats in subject_scores.items():
            if stats["percentage"] < 50:
                weak_areas.append(subject)
            elif stats["percentage"] >= 80:
                strong_areas.append(subject)

        result.weak_areas = weak_areas
        result.strong_areas = strong_areas

        # Generate suggestions
        suggested_retakes = []
        for chapter, stats in chapter_scores.items():
            if stats["percentage"] < 40:
                suggested_retakes.append(chapter)

        result.suggested_retakes = suggested_retakes[:3]  # Limit to top 3

        # Calculate rank among all participants
        better_results = ExamResult.objects.filter(
            exam=session.exam, percentage_score__gt=percentage_score
        ).count()
        result.rank = better_results + 1

        # Save the complete result
        result.save()
        
        # CRITICAL: Trigger leaderboard updates here
        logger.info(f"Triggering leaderboard updates for user {session.user.id}, exam {session.exam.id}")
        
        # Import here to avoid circular imports
        from apps.leaderboards.tasks import (
            update_user_leaderboard_entries,
            update_exam_specific_leaderboards,
        )

        # Update leaderboards asynchronously
        update_user_leaderboard_entries.delay(session.user.id)
        update_exam_specific_leaderboards.delay(session.exam.id)


        # IMPORTANT: Trigger analytics calculation
        logger.info(f"Triggering analytics calculation for session {session_id}")

        # Import here to avoid circular imports
        from apps.results.tasks import (
            calculate_exam_analytics,
            calculate_user_analytics,
            update_subject_performances,
        )

        # Trigger analytics calculations (use delay for async processing)
        calculate_exam_analytics.delay(session.exam.id)
        calculate_user_analytics.delay(session.user.id)
        update_subject_performances.delay(session.user.id)

        # Update question statistics for each answered question
        for answer in answers:
            update_question_statistics.delay(answer.question.id, answer.is_correct)

        # Update exam statistics
        update_exam_statistics.delay(session.exam.id)

        # Send notification to user
        send_notification.delay(
            user_id=session.user.id,
            notification_type="exam_completed",
            context={
                "exam_title": session.exam.title,
                "score": percentage_score,
                "passed": is_passed,
                "result_id": str(result.id),
            },
        )

        # Clear any cached data
        cache_key = f"session:{session_id}:answers"
        redis_client.delete(cache_key)

        logger.info(
            f"Score calculated and result created for session {session_id}: "
            f"{percentage_score:.2f}% (Result ID: {result.id}). Analytics tasks queued."
            f"{percentage_score:.2f}% (Result ID: {result.id}). Leaderboard updates queued."
        )

        return {
            "success": True,
            "score": percentage_score,
            "passed": is_passed,
            "result_id": str(result.id),
        }

    except ExamSession.DoesNotExist:
        logger.error(f"Session {session_id} not found")
        return {"success": False, "error": "Session not found"}
    except Exception as e:
        logger.error(f"Error calculating score for session {session_id}: {str(e)}")
        raise


@shared_task
def update_exam_statistics(exam_id):
    """
    Update exam statistics after a session completion.
    """
    try:
        from apps.results.models import ExamResult

        exam = Exam.objects.get(id=exam_id)

        # Get all completed results for this exam
        results = ExamResult.objects.filter(exam=exam)

        if results.exists():
            total_attempts = results.count()
            avg_score = results.aggregate(avg=Avg("percentage_score"))["avg"] or 0

            exam.total_attempts = total_attempts
            exam.average_score = avg_score
            exam.save(update_fields=["total_attempts", "average_score"])

            logger.info(
                f"Updated statistics for exam {exam_id}: {total_attempts} attempts, {avg_score:.2f}% avg"
            )

    except Exam.DoesNotExist:
        logger.error(f"Exam {exam_id} not found")
    except Exception as e:
        logger.error(f"Error updating exam statistics: {str(e)}")


@shared_task
def update_question_statistics(question_id, is_correct):
    """
    Update question statistics after it's answered.
    """
    try:
        question = Question.objects.get(id=question_id)

        question.total_attempts = F("total_attempts") + 1
        if is_correct:
            question.correct_attempts = F("correct_attempts") + 1

        question.save(update_fields=["total_attempts", "correct_attempts"])

        # Also trigger question analytics calculation
        from apps.results.tasks import calculate_question_analytics

        calculate_question_analytics.delay(question_id)

    except Question.DoesNotExist:
        logger.error(f"Question {question_id} not found")
    except Exception as e:
        logger.error(f"Error updating question statistics: {str(e)}")


# Keep all other existing tasks unchanged...
@shared_task
def auto_submit_expired_sessions():
    """
    Auto-submit exam sessions that have exceeded their time limit.
    Run this task every minute.
    """
    try:
        # Find expired sessions
        expired_sessions = ExamSession.objects.filter(
            status="in_progress", started_at__isnull=False
        )

        count = 0
        for session in expired_sessions:
            # Check if time is up (including grace period)
            if session.started_at:
                elapsed_seconds = (timezone.now() - session.started_at).total_seconds()
                total_allowed_seconds = (
                    session.duration_minutes * 60
                ) + session.exam.grace_period_seconds

                if elapsed_seconds > total_allowed_seconds:
                    # Auto-submit the session
                    session.submit_session(auto_submitted=True)

                    # Trigger score calculation
                    calculate_session_score.delay(session.id)

                    count += 1

                    # Send notification
                    send_notification.delay(
                        user_id=session.user.id,
                        notification_type="exam_auto_submitted",
                        context={"exam_title": session.exam.title},
                    )

                    logger.info(
                        f"Auto-submitted session {session.id} for user {session.user.id}"
                    )

        logger.info(f"Auto-submitted {count} expired sessions")
        return f"Auto-submitted {count} sessions"

    except Exception as e:
        logger.error(f"Error in auto-submit task: {str(e)}")
        raise


@shared_task
def cleanup_abandoned_sessions():
    """
    Clean up abandoned exam sessions (not started within 1 hour of creation).
    Run daily.
    """
    try:
        cutoff_time = timezone.now() - timedelta(hours=1)

        abandoned_sessions = ExamSession.objects.filter(
            status="not_started", created_at__lt=cutoff_time
        )

        count = abandoned_sessions.count()

        for session in abandoned_sessions:
            session.status = "abandoned"
            session.save(update_fields=["status"])

            # Return subscription attempt if applicable
            if session.exam.requires_subscription:
                from apps.subscriptions.models import Subscription

                subscription = Subscription.objects.filter(
                    user=session.user, is_active=True
                ).first()

                if subscription:
                    subscription.remaining_exams = F("remaining_exams") + 1
                    subscription.save(update_fields=["remaining_exams"])

        logger.info(f"Cleaned up {count} abandoned sessions")
        return f"Cleaned up {count} abandoned sessions"

    except Exception as e:
        logger.error(f"Error cleaning up abandoned sessions: {str(e)}")
        raise


@shared_task
def process_exam_submission(session_id):
    """
    Process exam submission - calculate scores and create results immediately.
    This should be called when an exam is submitted.
    """
    try:
        logger.info(f"Processing exam submission for session {session_id}")

        # Calculate the score and create result
        result = calculate_session_score(session_id)

        if result["success"]:
            logger.info(
                f"Successfully processed exam submission for session {session_id}"
            )
            return result
        else:
            logger.error(
                f"Failed to process exam submission for session {session_id}: {result}"
            )
            return result

    except Exception as e:
        logger.error(
            f"Error processing exam submission for session {session_id}: {str(e)}"
        )
        raise


@shared_task
def process_bulk_answers(session_id, answers_json):
    """
    Process bulk answer submission from Redis to database.
    Used for optimizing high-traffic exam submissions.
    """
    try:
        session = ExamSession.objects.get(id=session_id)
        answers_data = json.loads(answers_json)

        with transaction.atomic():
            for answer_data in answers_data:
                question_id = answer_data.get("question_id")
                option_id = answer_data.get("selected_option_id")
                time_spent = answer_data.get("time_spent_seconds", 0)
                is_marked = answer_data.get("is_marked_for_review", False)

                if question_id:
                    answer, created = ExamAnswer.objects.update_or_create(
                        session=session,
                        question_id=question_id,
                        defaults={
                            "selected_option_id": option_id,
                            "time_spent_seconds": time_spent,
                            "is_marked_for_review": is_marked,
                        },
                    )

            # Update session progress
            session.answers_submitted = ExamAnswer.objects.filter(
                session=session, selected_option__isnull=False
            ).count()
            session.save(update_fields=["answers_submitted"])

        logger.info(f"Processed {len(answers_data)} answers for session {session_id}")
        return {"success": True, "processed": len(answers_data)}

    except Exception as e:
        logger.error(f"Error processing bulk answers: {str(e)}")
        raise


@shared_task
def send_exam_reminders():
    """
    Send reminders for upcoming scheduled exams.
    Run every hour.
    """
    try:
        # Find exams starting in the next 24 hours
        start_time = timezone.now() + timedelta(hours=23)
        end_time = timezone.now() + timedelta(hours=24)

        upcoming_exams = Exam.objects.filter(
            exam_type="scheduled",
            scheduled_start__gte=start_time,
            scheduled_start__lt=end_time,
            is_active=True,
        )

        for exam in upcoming_exams:
            # Get all eligible users (with active subscriptions if required)
            from apps.subscriptions.models import Subscription
            from django.contrib.auth import get_user_model

            User = get_user_model()

            if exam.requires_subscription:
                users = User.objects.filter(
                    subscriptions__is_active=True, is_active=True
                ).distinct()
            else:
                users = User.objects.filter(is_active=True)

            for user in users:
                send_notification.delay(
                    user_id=user.id,
                    notification_type="exam_reminder",
                    context={
                        "exam_title": exam.title,
                        "start_time": exam.scheduled_start.isoformat(),
                        "duration": exam.duration_minutes,
                    },
                )

        logger.info(f"Sent reminders for {upcoming_exams.count()} exams")
        return f"Sent reminders for {upcoming_exams.count()} exams"

    except Exception as e:
        logger.error(f"Error sending exam reminders: {str(e)}")
        raise


@shared_task
def generate_exam_analytics(exam_id):
    """
    Generate detailed analytics for an exam.
    """
    try:
        from apps.results.models import ExamResult
        from django.db.models import Avg, Count, StdDev, Q

        exam = Exam.objects.get(id=exam_id)
        results = ExamResult.objects.filter(exam=exam)

        if not results.exists():
            return {"success": False, "message": "No results available"}

        analytics = {
            "total_attempts": results.count(),
            "unique_users": results.values("user").distinct().count(),
            "average_score": results.aggregate(avg=Avg("percentage_score"))["avg"],
            "std_deviation": results.aggregate(std=StdDev("percentage_score"))["std"],
            "pass_rate": (
                results.filter(is_passed=True).count() / results.count() * 100
            ),
            "average_time": results.aggregate(avg=Avg("time_taken_seconds"))["avg"],
            "score_distribution": {
                "0-20": results.filter(percentage_score__lt=20).count(),
                "20-40": results.filter(
                    percentage_score__gte=20, percentage_score__lt=40
                ).count(),
                "40-60": results.filter(
                    percentage_score__gte=40, percentage_score__lt=60
                ).count(),
                "60-80": results.filter(
                    percentage_score__gte=60, percentage_score__lt=80
                ).count(),
                "80-100": results.filter(percentage_score__gte=80).count(),
            },
        }

        # Cache the analytics
        cache_key = f"exam:{exam_id}:analytics"
        redis_client.setex(cache_key, 3600, json.dumps(analytics))

        logger.info(f"Generated analytics for exam {exam_id}")
        return analytics

    except Exam.DoesNotExist:
        logger.error(f"Exam {exam_id} not found")
        return {"success": False, "error": "Exam not found"}
    except Exception as e:
        logger.error(f"Error generating exam analytics: {str(e)}")
        raise
