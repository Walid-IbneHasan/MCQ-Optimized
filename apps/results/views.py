from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import (
    ExamResult,
    UserPerformanceAnalytics,
    SubjectPerformance,
    ExamAnalytics,
    QuestionAnalytics,
)
from .serializers import (
    ExamResultSerializer,
    ExamResultDetailSerializer,
    UserPerformanceAnalyticsSerializer,
    SubjectPerformanceSerializer,
    ExamAnalyticsSerializer,
    QuestionAnalyticsSerializer,
    UserDashboardSerializer,
)
from utils.permissions import IsTeacherOrAbove, IsOwnerOrReadOnly
from utils.decorators import log_api_call
from apps.core.views import BaseViewSet
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class ExamResultViewSet(BaseViewSet):
    """
    ViewSet for exam results.
    """

    serializer_class = ExamResultSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get exam results based on user permissions."""
        user = self.request.user

        if user.is_teacher_or_above:
            # Teachers and above can see all results
            queryset = ExamResult.objects.all()

            # Filter by exam if specified
            exam_id = self.request.query_params.get("exam")
            if exam_id:
                queryset = queryset.filter(exam_id=exam_id)

            # Filter by user if specified
            user_id = self.request.query_params.get("user")
            if user_id:
                queryset = queryset.filter(user_id=user_id)
        else:
            # Students can only see their own results
            queryset = ExamResult.objects.filter(user=user)

        return queryset.select_related("exam", "user", "session").order_by(
            "-created_at"
        )

    def get_serializer_class(self):
        """Return detailed serializer for retrieve action."""
        if self.action == "retrieve":
            return ExamResultDetailSerializer
        return ExamResultSerializer

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List exam results."""
        queryset = self.filter_queryset(self.get_queryset())

        # Filter by date range
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                {"success": True, "results": serializer.data}
            )

        serializer = self.get_serializer(queryset, many=True)
        return Response({"success": True, "results": serializer.data})

    @action(detail=False, methods=["get"])
    def my_results(self, request):
        """Get user's exam results with analytics."""
        user = request.user
        results = (
            ExamResult.objects.filter(user=user)
            .select_related("exam", "session")
            .order_by("-created_at")
        )

        # Get summary statistics
        total_exams = results.count()
        passed_exams = results.filter(is_passed=True).count()
        average_score = results.aggregate(avg=Avg("percentage_score"))["avg"] or 0

        # Get subject-wise performance
        subject_performance = SubjectPerformance.objects.filter(
            user=user
        ).select_related("subject")

        page = self.paginate_queryset(results)
        if page is not None:
            results_serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                {
                    "success": True,
                    "summary": {
                        "total_exams": total_exams,
                        "passed_exams": passed_exams,
                        "pass_rate": (
                            (passed_exams / total_exams * 100) if total_exams > 0 else 0
                        ),
                        "average_score": round(average_score, 2),
                    },
                    "subject_performance": SubjectPerformanceSerializer(
                        subject_performance, many=True
                    ).data,
                    "results": results_serializer.data,
                }
            )

        results_serializer = self.get_serializer(results, many=True)
        return Response(
            {
                "success": True,
                "summary": {
                    "total_exams": total_exams,
                    "passed_exams": passed_exams,
                    "pass_rate": (
                        (passed_exams / total_exams * 100) if total_exams > 0 else 0
                    ),
                    "average_score": round(average_score, 2),
                },
                "subject_performance": SubjectPerformanceSerializer(
                    subject_performance, many=True
                ).data,
                "results": results_serializer.data,
            }
        )

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        """Get comprehensive user dashboard."""
        user = request.user

        # Get or create user analytics
        analytics, created = UserPerformanceAnalytics.objects.get_or_create(user=user)

        # Get recent results
        recent_results = (
            ExamResult.objects.filter(user=user)
            .select_related("exam")
            .order_by("-created_at")[:10]
        )

        # Get subject performances
        subject_performances = SubjectPerformance.objects.filter(
            user=user
        ).select_related("subject")

        dashboard_data = {
            "user": user,
            "analytics": analytics,
            "recent_results": recent_results,
            "subject_performances": subject_performances,
        }

        serializer = UserDashboardSerializer(dashboard_data)
        return Response({"success": True, "dashboard": serializer.data})

    @action(detail=True, methods=["get"])
    def detailed_analysis(self, request, pk=None):
        """Get detailed analysis for a specific result."""
        result = self.get_object()

        if result.user != request.user and not request.user.is_teacher_or_above:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get answer-wise analysis
        from apps.exams.models import ExamAnswer

        answers = (
            ExamAnswer.objects.filter(session=result.session)
            .select_related("question", "selected_option")
            .order_by("question__id")
        )

        question_analysis = []
        for answer in answers:
            question_data = {
                "question_id": answer.question.id,
                "question_text": answer.question.question_text,
                "selected_option": (
                    answer.selected_option.option_text
                    if answer.selected_option
                    else None
                ),
                "is_correct": answer.is_correct,
                "marks_awarded": answer.marks_awarded,
                "time_spent": answer.time_spent_seconds,
                "difficulty": answer.question.difficulty,
                "chapter": answer.question.chapter.name,
                "subject": answer.question.chapter.subject.name,
            }

            # Add correct answer for analysis (only for completed exams or teachers)
            if (
                result.session.status in ["completed", "auto_submitted"]
                or request.user.is_teacher_or_above
            ):
                correct_option = answer.question.options.filter(is_correct=True).first()
                question_data["correct_answer"] = (
                    correct_option.option_text if correct_option else None
                )
                question_data["explanation"] = answer.question.explanation

            question_analysis.append(question_data)

        return Response(
            {
                "success": True,
                "result": ExamResultDetailSerializer(result).data,
                "question_analysis": question_analysis,
                "session_stats": {
                    "total_time": result.session.time_spent_seconds,
                    "tab_switches": result.session.tab_switches,
                    "suspicious_activities": len(result.session.suspicious_activity),
                },
            }
        )


class UserPerformanceAnalyticsViewSet(BaseViewSet):
    """
    ViewSet for user performance analytics.
    """

    serializer_class = UserPerformanceAnalyticsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get analytics based on user permissions."""
        user = self.request.user

        if user.is_teacher_or_above:
            return UserPerformanceAnalytics.objects.all().select_related("user")
        else:
            return UserPerformanceAnalytics.objects.filter(user=user)

    @action(detail=False, methods=["get"])
    def my_analytics(self, request):
        """Get current user's analytics."""
        analytics, created = UserPerformanceAnalytics.objects.get_or_create(
            user=request.user
        )

        serializer = self.get_serializer(analytics)
        return Response(
            {"success": True, "analytics": serializer.data, "is_new": created}
        )

    @action(detail=False, methods=["post"])
    def refresh_analytics(self, request):
        """Refresh user analytics."""
        from .tasks import calculate_user_analytics

        task = calculate_user_analytics.delay(request.user.id)

        return Response(
            {
                "success": True,
                "message": "Analytics refresh initiated",
                "task_id": task.id,
            }
        )


class SubjectPerformanceViewSet(BaseViewSet):
    """
    ViewSet for subject performance.
    """

    serializer_class = SubjectPerformanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get subject performance based on user permissions."""
        user = self.request.user

        if user.is_teacher_or_above:
            queryset = SubjectPerformance.objects.all()

            # Filter by user if specified
            user_id = self.request.query_params.get("user")
            if user_id:
                queryset = queryset.filter(user_id=user_id)
        else:
            queryset = SubjectPerformance.objects.filter(user=user)

        return queryset.select_related("user", "subject")

    @action(detail=False, methods=["get"])
    def my_subjects(self, request):
        """Get current user's subject performance."""
        performances = self.get_queryset().filter(user=request.user)
        serializer = self.get_serializer(performances, many=True)

        return Response({"success": True, "subjects": serializer.data})


class ExamAnalyticsViewSet(BaseViewSet):
    """
    ViewSet for exam analytics (Teachers and above only).
    """

    queryset = ExamAnalytics.objects.all()
    serializer_class = ExamAnalyticsSerializer
    permission_classes = [IsTeacherOrAbove]

    @action(detail=True, methods=["post"])
    def refresh_analytics(self, request, pk=None):
        """Refresh analytics for specific exam."""
        analytics = self.get_object()

        from .tasks import calculate_exam_analytics

        task = calculate_exam_analytics.delay(analytics.exam.id)

        return Response(
            {
                "success": True,
                "message": "Exam analytics refresh initiated",
                "task_id": task.id,
            }
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Get summary of all exam analytics."""
        analytics = self.get_queryset()

        total_exams = analytics.count()
        avg_completion_rate = (
            analytics.aggregate(avg_completion=Avg("completion_rate"))["avg_completion"]
            or 0
        )

        avg_pass_rate = analytics.aggregate(avg_pass=Avg("pass_rate"))["avg_pass"] or 0

        return Response(
            {
                "success": True,
                "summary": {
                    "total_exams": total_exams,
                    "average_completion_rate": round(avg_completion_rate, 2),
                    "average_pass_rate": round(avg_pass_rate, 2),
                },
            }
        )


class QuestionAnalyticsViewSet(BaseViewSet):
    """
    ViewSet for question analytics (Teachers and above only).
    """

    queryset = QuestionAnalytics.objects.all()
    serializer_class = QuestionAnalyticsSerializer
    permission_classes = [IsTeacherOrAbove]
    lookup_field = 'question_id'

    @action(detail=False, methods=["get"])
    def needs_review(self, request):
        """Get questions that need review."""
        questions_needing_review = self.get_queryset().filter(needs_review=True)

        serializer = self.get_serializer(questions_needing_review, many=True)
        return Response(
            {
                "success": True,
                "questions": serializer.data,
                "count": questions_needing_review.count(),
            }
        )

    @action(detail=False, methods=["get"])
    def difficulty_analysis(self, request):
        """Get question difficulty analysis."""
        analytics = self.get_queryset()

        # Group by difficulty index ranges
        very_easy = analytics.filter(success_rate__gte=90).count()
        easy = analytics.filter(success_rate__gte=70, success_rate__lt=90).count()
        medium = analytics.filter(success_rate__gte=50, success_rate__lt=70).count()
        hard = analytics.filter(success_rate__gte=30, success_rate__lt=50).count()
        very_hard = analytics.filter(success_rate__lt=30).count()

        return Response(
            {
                "success": True,
                "difficulty_distribution": {
                    "very_easy": very_easy,
                    "easy": easy,
                    "medium": medium,
                    "hard": hard,
                    "very_hard": very_hard,
                },
                "total_questions": analytics.count(),
            }
        )
