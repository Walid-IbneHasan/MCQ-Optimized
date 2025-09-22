# apps/exams/analytics_views.py - Fixed field names
from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q, Sum, Max, Min
from django.utils import timezone
from datetime import timedelta

from .models import Exam, ExamSession, ExamAnswer, ExamQuestion
from apps.results.models import ExamResult
from apps.questions.models import Question, QuestionOption
from .analytics_serializers import (
    ExamAnalyticsDetailSerializer,
    ExamParticipantSerializer,
    QuestionAnalyticsSerializer,
    UserExamDetailSerializer,
    ExamComparisonSerializer,
)
from utils.permissions import IsTeacherOrAbove
from utils.decorators import log_api_call
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class ExamAnalyticsView(APIView):
    """
    Comprehensive exam analytics for teachers, moderators, and admins.
    """

    permission_classes = [IsTeacherOrAbove]

    @log_api_call
    def get(self, request, exam_id):
        """Get comprehensive analytics for an exam."""
        exam = get_object_or_404(Exam, id=exam_id)

        logger.info(f"Getting analytics for exam {exam_id}")

        # Get all results for this exam
        results = (
            ExamResult.objects.filter(exam=exam)
            .select_related("user", "session")
            .prefetch_related("session__answers")
        )

        logger.info(f"Found {results.count()} ExamResult records for exam {exam_id}")

        # Also check for sessions to see if there are completed sessions without results
        sessions = ExamSession.objects.filter(
            exam=exam, status__in=["completed", "auto_submitted"]
        ).select_related("user")

        logger.info(f"Found {sessions.count()} completed sessions for exam {exam_id}")

        # If we have sessions but no results, create the missing results
        if sessions.exists() and not results.exists():
            logger.warning(
                f"Found {sessions.count()} completed sessions but no ExamResult records. Creating missing results..."
            )

            # Process each completed session that doesn't have a result
            for session in sessions:
                try:
                    # Check if result already exists
                    existing_result = ExamResult.objects.filter(session=session).first()
                    if not existing_result:
                        logger.info(f"Creating missing result for session {session.id}")
                        from .tasks import calculate_session_score

                        # Call synchronously to create the result immediately
                        calculate_session_score(session.id)
                except Exception as e:
                    logger.error(
                        f"Error creating result for session {session.id}: {str(e)}"
                    )

            # Refresh the results queryset
            results = (
                ExamResult.objects.filter(exam=exam)
                .select_related("user", "session")
                .prefetch_related("session__answers")
            )
            logger.info(f"After processing: Found {results.count()} ExamResult records")

        if not results.exists():
            # Check if there are any sessions at all
            all_sessions = ExamSession.objects.filter(exam=exam).count()
            logger.info(f"Total sessions for exam {exam_id}: {all_sessions}")

            return Response(
                {
                    "success": True,
                    "message": f"No completed attempts found for this exam yet. Total sessions created: {all_sessions}",
                    "analytics": None,
                    "debug_info": {
                        "exam_id": str(exam_id),
                        "total_sessions": all_sessions,
                        "completed_sessions": sessions.count(),
                        "results_count": results.count(),
                    },
                }
            )

        # Build comprehensive analytics
        analytics_data = self._build_exam_analytics(exam, results)

        serializer = ExamAnalyticsDetailSerializer(analytics_data)

        return Response(
            {
                "success": True,
                "analytics": serializer.data,
                "debug_info": {
                    "exam_id": str(exam_id),
                    "results_processed": results.count(),
                    "sessions_found": sessions.count(),
                },
            }
        )

    def _build_exam_analytics(self, exam, results):
        """Build comprehensive analytics data."""

        # Basic exam info
        exam_info = {
            "id": str(exam.id),
            "title": exam.title,
            "description": exam.description,
            "exam_type": exam.exam_type,
            "total_questions": exam.total_questions,
            "duration_minutes": exam.duration_minutes,
            "passing_percentage": exam.passing_percentage,
            "created_at": exam.created_at,
            "created_by": exam.created_by.get_full_name(),
        }

        # Participation statistics
        total_sessions = ExamSession.objects.filter(exam=exam).count()
        completed_sessions = results.count()
        unique_participants = results.values("user").distinct().count()

        participation_stats = {
            "total_sessions_started": total_sessions,
            "completed_sessions": completed_sessions,
            "completion_rate": (
                (completed_sessions / total_sessions * 100) if total_sessions > 0 else 0
            ),
            "unique_participants": unique_participants,
            "average_attempts_per_user": (
                completed_sessions / unique_participants
                if unique_participants > 0
                else 0
            ),
        }

        # Performance statistics
        avg_score = results.aggregate(avg=Avg("percentage_score"))["avg"] or 0
        passed_count = results.filter(is_passed=True).count()

        performance_stats = {
            "average_score": round(avg_score, 2),
            "highest_score": results.aggregate(max=Max("percentage_score"))["max"] or 0,
            "lowest_score": results.aggregate(min=Min("percentage_score"))["min"] or 0,
            "pass_rate": (
                (passed_count / completed_sessions * 100)
                if completed_sessions > 0
                else 0
            ),
            "total_passed": passed_count,
            "total_failed": completed_sessions - passed_count,
            "score_distribution": self._get_score_distribution(results),
            "grade_distribution": self._get_grade_distribution(results),
        }

        # Time analysis
        avg_time = results.aggregate(avg=Avg("time_taken_minutes"))["avg"] or 0
        time_analysis = {
            "average_time_taken": round(avg_time, 2),  # in minutes
            "fastest_completion": results.aggregate(min=Min("time_taken_minutes"))[
                "min"
            ]
            or 0,
            "slowest_completion": results.aggregate(max=Max("time_taken_minutes"))[
                "max"
            ]
            or 0,
            "time_distribution": self._get_time_distribution(results),
        }

        # Question-wise analytics
        question_analytics = self._get_question_analytics(exam, results)

        # Participants data
        participants = ExamParticipantSerializer(
            results[:50], many=True
        ).data  # Limit for performance

        # Top performers and struggling participants
        top_performers = self._get_top_performers(results)
        struggling_participants = self._get_struggling_participants(results)

        # Recommendations
        recommendations = self._generate_recommendations(
            exam, results, performance_stats
        )

        return {
            "exam_info": exam_info,
            "participation_stats": participation_stats,
            "performance_stats": performance_stats,
            "time_analysis": time_analysis,
            "question_analytics": question_analytics,
            "participants": participants,
            "top_performers": top_performers,
            "struggling_participants": struggling_participants,
            "recommendations": recommendations,
        }

    def _get_score_distribution(self, results):
        """Get score distribution in ranges."""
        ranges = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]

        distribution = {}
        for min_score, max_score in ranges:
            count = results.filter(
                percentage_score__gte=min_score,
                percentage_score__lt=max_score if max_score < 100 else 101,
            ).count()
            distribution[f"{min_score}-{max_score}"] = count

        return distribution

    def _get_grade_distribution(self, results):
        """Get grade distribution."""
        grades = {}
        for result in results:
            grade = result.grade or "F"
            grades[grade] = grades.get(grade, 0) + 1
        return grades

    def _get_time_distribution(self, results):
        """Get time distribution in ranges."""
        ranges = [(0, 30), (30, 60), (60, 90), (90, 120), (120, float("inf"))]

        distribution = {}
        for min_time, max_time in ranges:
            count = results.filter(
                time_taken_minutes__gte=min_time,
                time_taken_minutes__lt=(
                    max_time if max_time != float("inf") else float("inf")
                ),
            ).count()

            if max_time == float("inf"):
                distribution[f"{min_time}+ minutes"] = count
            else:
                distribution[f"{min_time}-{max_time} minutes"] = count

        return distribution

    def _get_question_analytics(self, exam, results):
        """Get detailed question-wise analytics."""
        # Get all questions for this exam
        questions = exam.get_questions()[:20]  # Limit for performance

        question_analytics = []

        for idx, question in enumerate(questions, 1):
            # Get all answers for this question
            answers = ExamAnswer.objects.filter(
                session__exam=exam, question=question
            ).select_related("selected_option")

            total_attempts = answers.count()
            correct_attempts = answers.filter(is_correct=True).count()
            wrong_attempts = answers.filter(
                is_correct=False, selected_option__isnull=False
            ).count()
            unanswered = answers.filter(selected_option__isnull=True).count()

            success_rate = (
                (correct_attempts / total_attempts * 100) if total_attempts > 0 else 0
            )
            avg_time = answers.aggregate(avg=Avg("time_spent_seconds"))["avg"] or 0

            # Option-wise statistics
            option_stats = {}
            for option in question.options.all():
                selection_count = answers.filter(selected_option=option).count()
                option_stats[str(option.id)] = {
                    "option_text": option.option_text[:50],
                    "is_correct": option.is_correct,
                    "selections": selection_count,
                    "percentage": (
                        (selection_count / total_attempts * 100)
                        if total_attempts > 0
                        else 0
                    ),
                }

            # User responses (sample)
            user_responses = []
            for answer in answers[:10]:  # Limit sample
                user_responses.append(
                    {
                        "user_name": answer.session.user.get_full_name(),
                        "selected_option": (
                            answer.selected_option.option_text
                            if answer.selected_option
                            else "Not answered"
                        ),
                        "is_correct": answer.is_correct,
                        "time_spent": answer.time_spent_seconds,
                    }
                )

            question_analytics.append(
                {
                    "question_id": str(question.id),
                    "question_text": question.question_text,
                    "question_number": idx,
                    "difficulty": question.difficulty,
                    "marks": question.marks,
                    "chapter_name": question.chapter.name,
                    "subject_name": question.chapter.subject.name,
                    "total_attempts": total_attempts,
                    "correct_attempts": correct_attempts,
                    "wrong_attempts": wrong_attempts,
                    "unanswered": unanswered,
                    "success_rate": round(success_rate, 2),
                    "average_time_spent": round(avg_time, 2),
                    "option_statistics": option_stats,
                    "user_responses": user_responses,
                }
            )

        return question_analytics

    def _get_top_performers(self, results):
        """Get top 10 performers."""
        top_results = results.order_by("-percentage_score")[:10]

        return [
            {
                "user_name": result.user.get_full_name(),
                "user_phone": result.user.phone_number,
                "score_percentage": result.percentage_score,
                "grade": result.grade,
                "time_taken_minutes": result.time_taken_minutes,
                "attempt_date": result.created_at,
            }
            for result in top_results
        ]

    def _get_struggling_participants(self, results):
        """Get participants who might need help."""
        struggling = results.filter(
            Q(percentage_score__lt=40) | Q(is_passed=False)
        ).order_by("percentage_score")[:10]

        return [
            {
                "user_name": result.user.get_full_name(),
                "user_phone": result.user.phone_number,
                "score_percentage": result.percentage_score,
                "issues": self._identify_issues(result),
                "attempt_date": result.created_at,
            }
            for result in struggling
        ]

    def _identify_issues(self, result):
        """Identify specific issues for struggling participants."""
        issues = []

        if result.percentage_score < 30:
            issues.append("Very low score")
        if result.time_taken_minutes < 10:  # Less than 10 minutes
            issues.append("Completed too quickly")
        if result.unanswered_questions > result.total_questions * 0.3:
            issues.append("Many unanswered questions")
        if result.session.tab_switches > 5:
            issues.append("Frequent tab switching")

        return issues

    def _generate_recommendations(self, exam, results, performance_stats):
        """Generate recommendations for exam improvement."""
        recommendations = []

        avg_score = performance_stats["average_score"]
        pass_rate = performance_stats["pass_rate"]

        if avg_score < 50:
            recommendations.append(
                {
                    "type": "difficulty",
                    "message": "Consider reducing exam difficulty or providing additional study materials",
                    "priority": "high",
                }
            )

        if pass_rate < 60:
            recommendations.append(
                {
                    "type": "passing_criteria",
                    "message": "Review passing percentage or exam content alignment with course material",
                    "priority": "medium",
                }
            )

        # Check for problematic questions
        question_analytics = self._get_question_analytics(exam, results)
        low_performing_questions = [
            q for q in question_analytics if q["success_rate"] < 30
        ]

        if low_performing_questions:
            recommendations.append(
                {
                    "type": "questions",
                    "message": f"{len(low_performing_questions)} questions have very low success rates and may need review",
                    "priority": "medium",
                }
            )

        return recommendations


class UserExamDetailView(APIView):
    """
    Detailed analysis for a specific user's exam attempt.
    """

    permission_classes = [IsTeacherOrAbove]

    def get(self, request, exam_id, user_id):
        """Get detailed analysis for a specific user's exam attempt."""
        exam = get_object_or_404(Exam, id=exam_id)
        user = get_object_or_404(User, id=user_id)

        # Get the most recent result for this user and exam
        result = (
            ExamResult.objects.filter(exam=exam, user=user)
            .select_related("session")
            .first()
        )

        if not result:
            return Response(
                {"success": False, "error": "No exam attempt found for this user"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Build detailed analysis
        analysis_data = self._build_user_analysis(exam, user, result)

        serializer = UserExamDetailSerializer(analysis_data)

        return Response({"success": True, "analysis": serializer.data})

    def _build_user_analysis(self, exam, user, result):
        """Build detailed user analysis with correct field names."""
        session = result.session

        # User info
        user_info = {
            "id": str(user.id),
            "name": user.get_full_name(),
            "phone_number": user.phone_number,
            "role": user.role,
        }

        # Session info
        session_info = {
            "id": str(session.id),
            "status": session.status,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "duration_minutes": session.duration_minutes,
            "time_spent_seconds": session.time_spent_seconds,
            "tab_switches": session.tab_switches,
            "ip_address": session.ip_address,
        }

        # Overall performance - FIXED: Use correct field names from ExamResult model
        overall_performance = {
            "total_questions": result.total_questions,
            "attempted_questions": result.questions_attempted,  # FIXED: correct field name
            "correct_answers": result.correct_answers,
            "wrong_answers": result.wrong_answers,
            "unanswered_questions": result.unanswered_questions,
            "marks_obtained": result.marks_obtained,
            "score_percentage": result.percentage_score,  # FIXED: correct field name
            "grade": result.grade,
            "is_passed": result.is_passed,
            "time_taken_seconds": result.time_taken_seconds,  # FIXED: use time_taken_seconds
        }

        # Question-by-question analysis
        answers = (
            ExamAnswer.objects.filter(session=session)
            .select_related("question", "selected_option")
            .order_by("question__id")
        )

        question_by_question = []
        for answer in answers:
            question = answer.question

            # Get correct option
            correct_option = question.options.filter(is_correct=True).first()

            question_by_question.append(
                {
                    "question_number": len(question_by_question) + 1,
                    "question_text": question.question_text,
                    "difficulty": question.difficulty,
                    "marks": question.marks,
                    "chapter_name": question.chapter.name,
                    "subject_name": question.chapter.subject.name,
                    "user_answer": (
                        answer.selected_option.option_text
                        if answer.selected_option
                        else "Not answered"
                    ),
                    "correct_answer": (
                        correct_option.option_text if correct_option else "Unknown"
                    ),
                    "is_correct": answer.is_correct,
                    "marks_awarded": answer.marks_awarded,
                    "time_spent_seconds": answer.time_spent_seconds,
                    "explanation": question.explanation,
                }
            )

        # Time analysis
        avg_time_per_question = (
            session.time_spent_seconds / result.total_questions
            if result.total_questions > 0
            else 0
        )
        time_analysis = {
            "total_time_seconds": session.time_spent_seconds,
            "average_time_per_question": round(avg_time_per_question, 2),
            "fastest_question": (
                min([q["time_spent_seconds"] for q in question_by_question])
                if question_by_question
                else 0
            ),
            "slowest_question": (
                max([q["time_spent_seconds"] for q in question_by_question])
                if question_by_question
                else 0
            ),
        }

        # Comparison with others
        all_results = ExamResult.objects.filter(exam=exam)
        rank = (
            all_results.filter(percentage_score__gt=result.percentage_score).count() + 1
        )

        comparison_with_others = {
            "rank": rank,
            "total_participants": all_results.count(),
            "percentile": (
                round((all_results.count() - rank + 1) / all_results.count() * 100, 2)
                if all_results.count() > 0
                else 0
            ),
            "average_score": round(
                all_results.aggregate(avg=Avg("percentage_score"))["avg"] or 0, 2
            ),
            "performance_vs_average": result.percentage_score
            - (all_results.aggregate(avg=Avg("percentage_score"))["avg"] or 0),
        }

        # Recommendations
        recommendations = self._generate_user_recommendations(
            result, question_by_question
        )

        return {
            "user_info": user_info,
            "session_info": session_info,
            "overall_performance": overall_performance,
            "question_by_question": question_by_question,
            "time_analysis": time_analysis,
            "comparison_with_others": comparison_with_others,
            "recommendations": recommendations,
        }

    def _generate_user_recommendations(self, result, questions):
        """Generate personalized recommendations for the user."""
        recommendations = []

        # Performance-based recommendations
        if result.percentage_score < 60:
            recommendations.append(
                {
                    "type": "study_more",
                    "message": "Consider additional study time and practice exams",
                    "priority": "high",
                }
            )

        # Time management recommendations
        if result.time_taken_seconds < 600:  # Less than 10 minutes
            recommendations.append(
                {
                    "type": "time_management",
                    "message": "Take more time to carefully read and consider each question",
                    "priority": "medium",
                }
            )

        # Subject-specific recommendations
        subject_performance = {}
        for question in questions:
            subject = question["subject_name"]
            if subject not in subject_performance:
                subject_performance[subject] = {"correct": 0, "total": 0}

            subject_performance[subject]["total"] += 1
            if question["is_correct"]:
                subject_performance[subject]["correct"] += 1

        weak_subjects = []
        for subject, perf in subject_performance.items():
            if perf["total"] > 0 and (perf["correct"] / perf["total"]) < 0.5:
                weak_subjects.append(subject)

        if weak_subjects:
            recommendations.append(
                {
                    "type": "subject_focus",
                    "message": f'Focus on improving in: {", ".join(weak_subjects)}',
                    "priority": "medium",
                }
            )

        return recommendations


class ExamComparisonView(APIView):
    """
    Compare exam performance across multiple users or attempts.
    """

    permission_classes = [IsTeacherOrAbove]

    def post(self, request, exam_id):
        """Compare users or attempts for an exam."""
        exam = get_object_or_404(Exam, id=exam_id)

        comparison_type = request.data.get("comparison_type", "users")
        participant_ids = request.data.get("participant_ids", [])

        if not participant_ids:
            return Response(
                {"success": False, "error": "Participant IDs are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if comparison_type == "users":
            comparison_data = self._compare_users(exam, participant_ids)
        else:
            comparison_data = self._compare_attempts(exam, participant_ids)

        serializer = ExamComparisonSerializer(comparison_data)

        return Response({"success": True, "comparison": serializer.data})

    def _compare_users(self, exam, user_ids):
        """Compare performance of different users."""
        results = ExamResult.objects.filter(
            exam=exam, user_id__in=user_ids
        ).select_related("user", "session")

        participants = []
        for result in results:
            participants.append(
                {
                    "user_id": str(result.user.id),
                    "user_name": result.user.get_full_name(),
                    "score_percentage": result.percentage_score,
                    "time_taken": result.time_taken_seconds,
                    "correct_answers": result.correct_answers,
                    "wrong_answers": result.wrong_answers,
                    "grade": result.grade,
                }
            )

        # Metrics comparison
        metrics_comparison = {
            "average_score": (
                sum(p["score_percentage"] for p in participants) / len(participants)
                if participants
                else 0
            ),
            "score_range": {
                "min": (
                    min(p["score_percentage"] for p in participants)
                    if participants
                    else 0
                ),
                "max": (
                    max(p["score_percentage"] for p in participants)
                    if participants
                    else 0
                ),
            },
            "average_time": (
                sum(p["time_taken"] for p in participants) / len(participants)
                if participants
                else 0
            ),
        }

        return {
            "comparison_type": "users",
            "participants": participants,
            "metrics_comparison": metrics_comparison,
            "question_wise_comparison": [],  # Can be implemented if needed
            "insights": self._generate_comparison_insights(participants),
        }

    def _compare_attempts(self, exam, session_ids):
        """Compare multiple attempts (possibly from same user)."""
        # Implementation similar to _compare_users but for sessions
        pass

    def _generate_comparison_insights(self, participants):
        """Generate insights from comparison."""
        insights = []

        if not participants:
            return insights

        scores = [p["score_percentage"] for p in participants]
        score_variance = max(scores) - min(scores) if scores else 0

        if score_variance > 30:
            insights.append(
                "High variance in performance - consider reviewing exam difficulty or preparation materials"
            )

        return insights
