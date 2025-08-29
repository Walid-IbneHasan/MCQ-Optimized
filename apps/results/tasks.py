from mcq_platform.celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.db.models import Avg, Count, StdDev, Q, F, Sum
from datetime import timedelta, datetime
from .models import (
    ExamResult,
    UserPerformanceAnalytics,
    SubjectPerformance,
    ExamAnalytics,
    QuestionAnalytics,
)
from apps.exams.models import Exam, ExamSession, ExamAnswer
from apps.questions.models import Question
from apps.subjects.models import Subject, Chapter
from utils.redis_client import redis_client
import json
import numpy as np
import logging

logger = logging.getLogger(__name__)


@shared_task
def calculate_user_analytics(user_id):
    """
    Calculate comprehensive analytics for a user.
    """
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = User.objects.get(id=user_id)
        analytics, created = UserPerformanceAnalytics.objects.get_or_create(user=user)

        # Get all user's exam results
        results = ExamResult.objects.filter(user=user)

        if not results.exists():
            logger.info(f"No results found for user {user_id}")
            return {"success": True, "message": "No results to analyze"}

        # Calculate overall statistics
        analytics.total_exams_taken = results.count()
        analytics.total_exams_passed = results.filter(is_passed=True).count()

        # Time statistics
        total_time = results.aggregate(total=Sum("time_taken_minutes"))["total"] or 0
        analytics.total_time_spent_hours = total_time / 60

        # Score statistics
        score_stats = results.aggregate(
            avg=Avg("percentage_score"),
            best=Max("percentage_score"),
            worst=Min("percentage_score"),
            variance=Variance("percentage_score"),
        )

        analytics.average_score = score_stats["avg"] or 0.0
        analytics.best_score = score_stats["best"] or 0.0
        analytics.worst_score = score_stats["worst"] or 0.0
        analytics.score_variance = score_stats["variance"] or 0.0

        # Calculate consistency rating
        if analytics.score_variance < 100:
            analytics.consistency_rating = "Very Consistent"
        elif analytics.score_variance < 200:
            analytics.consistency_rating = "Consistent"
        elif analytics.score_variance < 400:
            analytics.consistency_rating = "Moderately Consistent"
        else:
            analytics.consistency_rating = "Inconsistent"

        # Subject-wise performance
        subject_scores = {}
        subjects = Subject.objects.filter(
            chapters__questions__examanswer__session__result__user=user
        ).distinct()

        for subject in subjects:
            subject_results = results.filter(exam__chapters__subject=subject).distinct()
            if subject_results.exists():
                avg_score = subject_results.aggregate(avg=Avg("percentage_score"))[
                    "avg"
                ]
                subject_scores[str(subject.id)] = round(avg_score, 2)

        analytics.subject_wise_averages = subject_scores

        # Identify strengths and weaknesses
        sorted_subjects = sorted(
            subject_scores.items(), key=lambda x: x[1], reverse=True
        )
        if sorted_subjects:
            analytics.subject_strengths = [s[0] for s in sorted_subjects[:3]]
            analytics.subject_weaknesses = [
                s[0] for s in sorted_subjects[-3:] if s[1] < 60
            ]

        # Calculate improvement trend
        recent_results = results.order_by("-created_at")[:10]
        if recent_results.count() >= 5:
            recent_scores = [r.percentage_score for r in recent_results]
            trend = calculate_trend(recent_scores)

            if trend > 0.5:
                analytics.improvement_trend = "Improving"
            elif trend < -0.5:
                analytics.improvement_trend = "Declining"
            else:
                analytics.improvement_trend = "Stable"

            analytics.progress_rate = trend

        # Calculate preferred difficulty
        difficulty_performance = results.values(
            "exam__difficulty_distribution"
        ).annotate(avg_score=Avg("percentage_score"))

        # Peak performance hours
        hour_performance = (
            results.extra(select={"hour": "EXTRACT(hour FROM created_at)"})
            .values("hour")
            .annotate(avg_score=Avg("percentage_score"))
            .order_by("-avg_score")[:3]
        )

        analytics.peak_performance_hours = [int(h["hour"]) for h in hour_performance]

        # Generate recommendations
        analytics.study_recommendations = generate_study_recommendations(
            user, analytics
        )
        analytics.next_level_suggestions = generate_next_level_suggestions(
            user, analytics
        )

        # Save analytics
        analytics.save()

        # Update subject performances
        update_subject_performances.delay(user_id)

        logger.info(f"Analytics calculated for user {user_id}")
        return {"success": True, "analytics_id": str(analytics.id)}

    except Exception as e:
        logger.error(f"Error calculating user analytics: {str(e)}")
        raise


@shared_task
def update_subject_performances(user_id):
    """
    Update subject-wise performance for a user.
    """
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()

        user = User.objects.get(id=user_id)
        subjects = Subject.objects.filter(is_active=True)

        for subject in subjects:
            # Get results for this subject
            subject_results = ExamResult.objects.filter(
                user=user, exam__chapters__subject=subject
            ).distinct()

            if subject_results.exists():
                performance, created = SubjectPerformance.objects.get_or_create(
                    user=user, subject=subject
                )

                # Update metrics
                performance.exams_taken = subject_results.count()
                performance.exams_passed = subject_results.filter(
                    is_passed=True
                ).count()

                # Score statistics
                score_stats = subject_results.aggregate(
                    avg=Avg("percentage_score"),
                    best=Max("percentage_score"),
                    latest=Max("created_at"),
                )

                performance.average_score = score_stats["avg"] or 0.0
                performance.best_score = score_stats["best"] or 0.0

                # Get latest score
                latest_result = subject_results.order_by("-created_at").first()
                if latest_result:
                    performance.latest_score = latest_result.percentage_score

                # Get first attempt score
                first_result = subject_results.order_by("created_at").first()
                if first_result:
                    performance.first_attempt_score = first_result.percentage_score
                    performance.improvement = (
                        performance.latest_score - performance.first_attempt_score
                    )

                # Calculate trend
                recent_results = subject_results.order_by("-created_at")[:5]
                if recent_results.count() >= 3:
                    scores = [r.percentage_score for r in recent_results]
                    trend = calculate_trend(scores)

                    if trend > 0.3:
                        performance.trend = "Improving"
                    elif trend < -0.3:
                        performance.trend = "Declining"
                    else:
                        performance.trend = "Stable"

                # Chapter-wise analysis
                chapter_scores = {}
                weak_chapters = []
                strong_chapters = []

                chapters = Chapter.objects.filter(subject=subject, is_active=True)
                for chapter in chapters:
                    chapter_results = subject_results.filter(
                        exam__chapters=chapter
                    ).distinct()

                    if chapter_results.exists():
                        avg_score = chapter_results.aggregate(
                            avg=Avg("percentage_score")
                        )["avg"]
                        chapter_scores[str(chapter.id)] = round(avg_score, 2)

                        if avg_score < 50:
                            weak_chapters.append(str(chapter.id))
                        elif avg_score >= 80:
                            strong_chapters.append(str(chapter.id))

                performance.chapter_scores = chapter_scores
                performance.weak_chapters = weak_chapters
                performance.strong_chapters = strong_chapters

                # Time analysis
                time_stats = subject_results.aggregate(
                    avg_time=Avg("time_taken_minutes"),
                    total_time=Sum("time_taken_minutes"),
                )

                performance.average_time_per_exam = time_stats["avg_time"] or 0.0
                performance.total_time_spent = (
                    time_stats["total_time"] or 0
                ) / 60  # Convert to hours

                # Recommendations
                performance.recommended_chapters = weak_chapters[
                    :3
                ]  # Top 3 weak chapters

                # Study priority
                if performance.average_score < 50:
                    performance.study_priority = "High"
                elif performance.average_score < 70:
                    performance.study_priority = "Medium"
                else:
                    performance.study_priority = "Low"

                performance.save()

        logger.info(f"Subject performances updated for user {user_id}")
        return {"success": True}

    except Exception as e:
        logger.error(f"Error updating subject performances: {str(e)}")
        raise


@shared_task
def calculate_exam_analytics(exam_id):
    """
    Calculate analytics for a specific exam.
    """
    try:
        exam = Exam.objects.get(id=exam_id)
        analytics, created = ExamAnalytics.objects.get_or_create(exam=exam)

        # Get all results for this exam
        results = ExamResult.objects.filter(exam=exam)

        if not results.exists():
            logger.info(f"No results found for exam {exam_id}")
            return {"success": True, "message": "No results to analyze"}

        # Participation statistics
        analytics.total_attempts = results.count()
        analytics.unique_users = results.values("user").distinct().count()

        # Calculate completion rate
        total_sessions = ExamSession.objects.filter(exam=exam).count()
        completed_sessions = ExamSession.objects.filter(
            exam=exam, status__in=["completed", "auto_submitted"]
        ).count()

        if total_sessions > 0:
            analytics.completion_rate = (completed_sessions / total_sessions) * 100

        # Score statistics
        score_stats = results.aggregate(
            avg=Avg("percentage_score"),
            highest=Max("percentage_score"),
            lowest=Min("percentage_score"),
            std_dev=StdDev("percentage_score"),
        )

        analytics.average_score = score_stats["avg"] or 0.0
        analytics.highest_score = score_stats["highest"] or 0.0
        analytics.lowest_score = score_stats["lowest"] or 0.0
        analytics.standard_deviation = score_stats["std_dev"] or 0.0

        # Calculate median
        scores = list(results.values_list("percentage_score", flat=True))
        if scores:
            analytics.median_score = np.median(scores)

        # Pass/fail statistics
        analytics.total_passed = results.filter(is_passed=True).count()
        analytics.total_failed = results.filter(is_passed=False).count()

        if analytics.total_attempts > 0:
            analytics.pass_rate = (
                analytics.total_passed / analytics.total_attempts
            ) * 100

        # Time statistics
        time_stats = results.aggregate(
            avg_time=Avg("time_taken_minutes"),
            min_time=Min("time_taken_minutes"),
            max_time=Max("time_taken_minutes"),
        )

        analytics.average_completion_time = time_stats["avg_time"] or 0.0
        analytics.fastest_completion = time_stats["min_time"] or 0.0
        analytics.slowest_completion = time_stats["max_time"] or 0.0

        # Question analysis
        question_stats = analyze_exam_questions(exam_id)
        analytics.most_missed_questions = question_stats["most_missed"][:5]
        analytics.easiest_questions = question_stats["easiest"][:5]
        analytics.hardest_questions = question_stats["hardest"][:5]
        analytics.question_difficulty_analysis = question_stats[
            "difficulty_distribution"
        ]

        # User behavior
        sessions = ExamSession.objects.filter(exam=exam)
        analytics.tab_switch_incidents = (
            sessions.aggregate(total=Sum("tab_switches"))["total"] or 0
        )

        suspicious_sessions = sessions.filter(tab_switches__gt=5).count()
        analytics.suspicious_activities = suspicious_sessions

        # Calculate trends
        analytics.score_trend = calculate_exam_trend(exam_id, "score")
        analytics.participation_trend = calculate_exam_trend(exam_id, "participation")

        # Generate recommendations
        analytics.exam_recommendations = generate_exam_recommendations(analytics)

        analytics.save()

        logger.info(f"Analytics calculated for exam {exam_id}")
        return {"success": True, "analytics_id": str(analytics.id)}

    except Exam.DoesNotExist:
        logger.error(f"Exam {exam_id} not found")
        return {"success": False, "error": "Exam not found"}
    except Exception as e:
        logger.error(f"Error calculating exam analytics: {str(e)}")
        raise


@shared_task
def calculate_question_analytics(question_id):
    """
    Calculate analytics for a specific question.
    """
    try:
        question = Question.objects.get(id=question_id)
        analytics, created = QuestionAnalytics.objects.get_or_create(question=question)

        # Get all answers for this question
        answers = ExamAnswer.objects.filter(question=question)

        if not answers.exists():
            logger.info(f"No answers found for question {question_id}")
            return {"success": True, "message": "No answers to analyze"}

        # Usage statistics
        analytics.times_presented = answers.count()
        analytics.times_answered = answers.filter(selected_option__isnull=False).count()
        analytics.times_correct = answers.filter(is_correct=True).count()
        analytics.times_skipped = answers.filter(selected_option__isnull=True).count()

        # Performance metrics
        if analytics.times_answered > 0:
            analytics.success_rate = (
                analytics.times_correct / analytics.times_answered
            ) * 100

            # Calculate difficulty index (inverse of success rate)
            analytics.difficulty_index = 100 - analytics.success_rate

        # Time analysis
        time_stats = answers.filter(selected_option__isnull=False).aggregate(
            avg_time=Avg("time_spent_seconds"),
            min_time=Min("time_spent_seconds"),
            max_time=Max("time_spent_seconds"),
        )

        analytics.average_time_spent = time_stats["avg_time"] or 0.0

        # Get fastest and slowest correct times
        correct_answers = answers.filter(is_correct=True)
        if correct_answers.exists():
            correct_time_stats = correct_answers.aggregate(
                min_time=Min("time_spent_seconds"), max_time=Max("time_spent_seconds")
            )
            analytics.fastest_correct_time = correct_time_stats["min_time"] or 0.0
            analytics.slowest_correct_time = correct_time_stats["max_time"] or 0.0

        # Option analysis
        option_stats = {}
        from apps.questions.models import QuestionOption

        options = QuestionOption.objects.filter(question=question)
        for option in options:
            selection_count = answers.filter(selected_option=option).count()
            if analytics.times_answered > 0:
                selection_percentage = (
                    selection_count / analytics.times_answered
                ) * 100
            else:
                selection_percentage = 0

            option_stats[str(option.id)] = {
                "text": option.option_text[:50],
                "selections": selection_count,
                "percentage": round(selection_percentage, 2),
                "is_correct": option.is_correct,
            }

        analytics.option_selection_stats = option_stats

        # Calculate discrimination index
        analytics.discrimination_index = calculate_discrimination_index(question_id)

        # Quality assessment
        quality_score = assess_question_quality(analytics)
        analytics.quality_score = quality_score

        # Determine if needs review
        review_reasons = []

        if analytics.success_rate < 20:
            review_reasons.append("Very low success rate")
        elif analytics.success_rate > 95:
            review_reasons.append("Very high success rate")

        if analytics.discrimination_index < 0.2:
            review_reasons.append("Poor discrimination")

        if analytics.average_time_spent < 10:
            review_reasons.append("Answered too quickly")
        elif analytics.average_time_spent > 300:
            review_reasons.append("Takes too long to answer")

        analytics.needs_review = len(review_reasons) > 0
        analytics.review_reasons = review_reasons

        analytics.save()

        logger.info(f"Analytics calculated for question {question_id}")
        return {"success": True, "analytics_id": str(analytics.id)}

    except Question.DoesNotExist:
        logger.error(f"Question {question_id} not found")
        return {"success": False, "error": "Question not found"}
    except Exception as e:
        logger.error(f"Error calculating question analytics: {str(e)}")
        raise


@shared_task
def batch_calculate_analytics():
    """
    Batch task to calculate analytics for all entities.
    Run daily.
    """
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()

        # Calculate user analytics
        users_with_results = User.objects.filter(exam_results__isnull=False).distinct()

        for user in users_with_results:
            calculate_user_analytics.delay(user.id)

        # Calculate exam analytics
        exams_with_results = Exam.objects.filter(results__isnull=False).distinct()

        for exam in exams_with_results:
            calculate_exam_analytics.delay(exam.id)

        # Calculate question analytics
        questions_with_answers = Question.objects.filter(
            examanswer__isnull=False
        ).distinct()[
            :100
        ]  # Limit to 100 questions at a time

        for question in questions_with_answers:
            calculate_question_analytics.delay(question.id)

        logger.info("Batch analytics calculation initiated")
        return {"success": True}

    except Exception as e:
        logger.error(f"Error in batch analytics calculation: {str(e)}")
        raise


# Helper functions


def calculate_trend(scores):
    """Calculate trend from a list of scores."""
    if len(scores) < 2:
        return 0

    x = np.arange(len(scores))
    y = np.array(scores)

    # Simple linear regression
    coefficients = np.polyfit(x, y, 1)
    return coefficients[0]  # Slope indicates trend


def calculate_discrimination_index(question_id):
    """
    Calculate discrimination index for a question.
    Measures how well the question discriminates between high and low performers.
    """
    try:
        # Get all answers for this question with user scores
        answers = ExamAnswer.objects.filter(question_id=question_id).select_related(
            "session__result"
        )

        if answers.count() < 10:
            return 0.0

        # Group users by performance
        user_scores = []
        for answer in answers:
            if hasattr(answer.session, "result"):
                user_scores.append(
                    {
                        "score": answer.session.result.percentage_score,
                        "correct": answer.is_correct,
                    }
                )

        if not user_scores:
            return 0.0

        # Sort by score and split into high and low groups
        sorted_scores = sorted(user_scores, key=lambda x: x["score"], reverse=True)

        group_size = len(sorted_scores) // 3
        high_group = sorted_scores[:group_size]
        low_group = sorted_scores[-group_size:]

        # Calculate success rate for each group
        high_correct = sum(1 for s in high_group if s["correct"])
        low_correct = sum(1 for s in low_group if s["correct"])

        if group_size > 0:
            discrimination = (high_correct - low_correct) / group_size
            return max(0, min(1, discrimination))  # Clamp between 0 and 1

        return 0.0

    except Exception as e:
        logger.error(f"Error calculating discrimination index: {str(e)}")
        return 0.0


def assess_question_quality(analytics):
    """Assess overall quality of a question based on analytics."""
    quality_score = 50.0  # Start with base score

    # Success rate factor (ideal: 40-80%)
    if 40 <= analytics.success_rate <= 80:
        quality_score += 20
    elif 20 <= analytics.success_rate <= 90:
        quality_score += 10
    else:
        quality_score -= 10

    # Discrimination index factor (ideal: > 0.3)
    if analytics.discrimination_index >= 0.4:
        quality_score += 20
    elif analytics.discrimination_index >= 0.3:
        quality_score += 10
    elif analytics.discrimination_index >= 0.2:
        quality_score += 5
    else:
        quality_score -= 10

    # Time factor (ideal: 30-120 seconds)
    if 30 <= analytics.average_time_spent <= 120:
        quality_score += 10
    elif 15 <= analytics.average_time_spent <= 180:
        quality_score += 5
    else:
        quality_score -= 5

    return max(0, min(100, quality_score))


def analyze_exam_questions(exam_id):
    """Analyze questions in an exam."""
    try:
        exam_answers = (
            ExamAnswer.objects.filter(session__exam_id=exam_id)
            .values("question")
            .annotate(
                total_attempts=Count("id"),
                correct_count=Count("id", filter=Q(is_correct=True)),
                avg_time=Avg("time_spent_seconds"),
            )
        )

        question_stats = []
        for answer_stat in exam_answers:
            success_rate = 0
            if answer_stat["total_attempts"] > 0:
                success_rate = (
                    answer_stat["correct_count"] / answer_stat["total_attempts"]
                ) * 100

            question_stats.append(
                {
                    "question_id": str(answer_stat["question"]),
                    "success_rate": success_rate,
                    "attempts": answer_stat["total_attempts"],
                    "avg_time": answer_stat["avg_time"] or 0,
                }
            )

        # Sort by success rate
        sorted_by_success = sorted(question_stats, key=lambda x: x["success_rate"])

        return {
            "most_missed": [q["question_id"] for q in sorted_by_success[:10]],
            "easiest": [q["question_id"] for q in sorted_by_success[-10:]],
            "hardest": [q["question_id"] for q in sorted_by_success[:10]],
            "difficulty_distribution": {
                "easy": len([q for q in question_stats if q["success_rate"] >= 80]),
                "medium": len(
                    [q for q in question_stats if 50 <= q["success_rate"] < 80]
                ),
                "hard": len([q for q in question_stats if q["success_rate"] < 50]),
            },
        }

    except Exception as e:
        logger.error(f"Error analyzing exam questions: {str(e)}")
        return {
            "most_missed": [],
            "easiest": [],
            "hardest": [],
            "difficulty_distribution": {},
        }


def calculate_exam_trend(exam_id, trend_type="score"):
    """Calculate trend for exam metrics."""
    try:
        if trend_type == "score":
            # Get scores over time
            results = (
                ExamResult.objects.filter(exam_id=exam_id)
                .order_by("created_at")
                .values_list("percentage_score", flat=True)
            )

            if len(results) >= 5:
                recent_scores = list(results[-10:])
                trend = calculate_trend(recent_scores)

                if trend > 0.5:
                    return "Improving"
                elif trend < -0.5:
                    return "Declining"

        elif trend_type == "participation":
            # Get participation over time (weekly)
            from django.db.models.functions import TruncWeek

            weekly_counts = (
                ExamResult.objects.filter(exam_id=exam_id)
                .annotate(week=TruncWeek("created_at"))
                .values("week")
                .annotate(count=Count("id"))
                .order_by("week")
            )

            if weekly_counts.count() >= 4:
                counts = [w["count"] for w in weekly_counts[-8:]]
                trend = calculate_trend(counts)

                if trend > 0.5:
                    return "Increasing"
                elif trend < -0.5:
                    return "Decreasing"

        return "Stable"

    except Exception as e:
        logger.error(f"Error calculating exam trend: {str(e)}")
        return "Unknown"


def generate_study_recommendations(user, analytics):
    """Generate personalized study recommendations."""
    recommendations = []

    # Based on weak subjects
    if analytics.subject_weaknesses:
        recommendations.append(
            {
                "type": "focus_area",
                "priority": "high",
                "message": f"Focus on improving weak subjects",
                "subjects": analytics.subject_weaknesses[:3],
            }
        )

    # Based on consistency
    if analytics.consistency_rating == "Inconsistent":
        recommendations.append(
            {
                "type": "practice",
                "priority": "medium",
                "message": "Practice regularly to improve consistency",
                "suggestion": "Take at least 2-3 practice exams per week",
            }
        )

    # Based on time management
    if analytics.average_score < 60 and analytics.total_time_spent_hours > 0:
        recommendations.append(
            {
                "type": "strategy",
                "priority": "high",
                "message": "Review exam-taking strategies",
                "suggestion": "Focus on time management and question prioritization",
            }
        )

    return recommendations


def generate_next_level_suggestions(user, analytics):
    """Generate suggestions for next learning level."""
    suggestions = []

    if analytics.average_score >= 80:
        suggestions.append(
            {
                "type": "advance",
                "message": "Ready for advanced difficulty exams",
                "action": "Try hard difficulty exams",
            }
        )
    elif analytics.average_score >= 60:
        suggestions.append(
            {
                "type": "practice",
                "message": "Continue with medium difficulty",
                "action": "Master current level before advancing",
            }
        )
    else:
        suggestions.append(
            {
                "type": "foundation",
                "message": "Strengthen fundamentals",
                "action": "Review basic concepts and take easy difficulty exams",
            }
        )

    return suggestions


def generate_exam_recommendations(analytics):
    """Generate recommendations for exam improvement."""
    recommendations = []

    # Based on pass rate
    if analytics.pass_rate < 40:
        recommendations.append(
            {
                "type": "difficulty",
                "message": "Consider reducing exam difficulty",
                "reason": "Low pass rate indicates exam may be too difficult",
            }
        )

    # Based on completion rate
    if analytics.completion_rate < 70:
        recommendations.append(
            {
                "type": "duration",
                "message": "Review exam duration settings",
                "reason": "Low completion rate may indicate time constraints",
            }
        )

    # Based on standard deviation
    if analytics.standard_deviation > 25:
        recommendations.append(
            {
                "type": "consistency",
                "message": "Review question difficulty distribution",
                "reason": "High score variance suggests inconsistent difficulty",
            }
        )

    return recommendations


# Import these at the top if not already imported
from django.db.models import Max, Min, Variance
