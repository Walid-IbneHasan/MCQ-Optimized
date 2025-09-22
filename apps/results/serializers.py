from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    ExamResult,
    UserPerformanceAnalytics,
    SubjectPerformance,
    ExamAnalytics,
    QuestionAnalytics,
)
from apps.exams.serializers import ExamListSerializer
from apps.subjects.serializers import SubjectSerializer

User = get_user_model()


class ExamResultSerializer(serializers.ModelSerializer):
    """
    Serializer for exam results.
    """

    exam_detail = ExamListSerializer(source="exam", read_only=True)
    # CORRECTED: Changed source from "user.full_name" to "user.get_full_name"
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    performance_rating = serializers.ReadOnlyField()

    class Meta:
        model = ExamResult
        fields = [
            "id",
            "exam",
            "exam_detail",
            "user_name",
            "total_questions",
            "questions_attempted",
            "correct_answers",
            "wrong_answers",
            "unanswered_questions",
            "total_marks",
            "marks_obtained",
            "negative_marks",
            "percentage_score",
            "is_passed",
            "grade",
            "rank",
            "time_taken_minutes",
            "time_taken_seconds",
            "average_time_per_question",
            "accuracy_rate",
            "performance_rating",
            "subject_wise_scores",
            "chapter_wise_scores",
            "difficulty_wise_scores",
            "weak_areas",
            "strong_areas",
            "suggested_retakes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class ExamResultDetailSerializer(ExamResultSerializer):
    """
    Detailed serializer for exam results with full analytics.
    """

    session_details = serializers.SerializerMethodField()

    class Meta(ExamResultSerializer.Meta):
        fields = ExamResultSerializer.Meta.fields + ["session_details"]

    def get_session_details(self, obj):
        """Get session details for result."""
        from apps.exams.serializers import ExamSessionSerializer

        return ExamSessionSerializer(obj.session).data


class UserPerformanceAnalyticsSerializer(serializers.ModelSerializer):
    """
    Serializer for user performance analytics.
    """

    # CORRECTED: Changed source from "user.full_name" to "user.get_full_name"
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    pass_rate = serializers.SerializerMethodField()

    class Meta:
        model = UserPerformanceAnalytics
        fields = [
            "id",
            "user_name",
            "total_exams_taken",
            "total_exams_passed",
            "pass_rate",
            "total_time_spent_hours",
            "average_score",
            "best_score",
            "worst_score",
            "score_variance",
            "consistency_rating",
            "subject_strengths",
            "subject_weaknesses",
            "subject_wise_averages",
            "improvement_trend",
            "progress_rate",
            "preferred_difficulty",
            "average_attempt_time",
            "peak_performance_hours",
            "study_recommendations",
            "next_level_suggestions",
            "last_calculated",
        ]
        read_only_fields = ["id", "last_calculated"]

    def get_pass_rate(self, obj):
        """Calculate pass rate percentage."""
        if obj.total_exams_taken == 0:
            return 0.0
        return (obj.total_exams_passed / obj.total_exams_taken) * 100


class SubjectPerformanceSerializer(serializers.ModelSerializer):
    """
    Serializer for subject performance.
    """

    subject_detail = SubjectSerializer(source="subject", read_only=True)
    # CORRECTED: Changed source from "user.full_name" to "user.get_full_name"
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    pass_rate = serializers.SerializerMethodField()

    class Meta:
        model = SubjectPerformance
        fields = [
            "id",
            "subject",
            "subject_detail",
            "user_name",
            "exams_taken",
            "exams_passed",
            "pass_rate",
            "average_score",
            "best_score",
            "latest_score",
            "first_attempt_score",
            "improvement",
            "trend",
            "chapter_scores",
            "weak_chapters",
            "strong_chapters",
            "difficulty_performance",
            "average_time_per_exam",
            "total_time_spent",
            "recommended_chapters",
            "study_priority",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_pass_rate(self, obj):
        """Calculate pass rate percentage."""
        if obj.exams_taken == 0:
            return 0.0
        return (obj.exams_passed / obj.exams_taken) * 100


class ExamAnalyticsSerializer(serializers.ModelSerializer):
    """
    Serializer for exam analytics.
    """

    exam_detail = ExamListSerializer(source="exam", read_only=True)

    class Meta:
        model = ExamAnalytics
        fields = [
            "id",
            "exam_detail",
            "total_attempts",
            "unique_users",
            "completion_rate",
            "average_score",
            "median_score",
            "highest_score",
            "lowest_score",
            "standard_deviation",
            "pass_rate",
            "total_passed",
            "total_failed",
            "average_completion_time",
            "fastest_completion",
            "slowest_completion",
            "question_difficulty_analysis",
            "most_missed_questions",
            "easiest_questions",
            "hardest_questions",
            "tab_switch_incidents",
            "suspicious_activities",
            "score_trend",
            "participation_trend",
            "exam_recommendations",
            "last_calculated",
        ]
        read_only_fields = ["id", "last_calculated"]


class QuestionAnalyticsSerializer(serializers.ModelSerializer):
    """
    Serializer for question analytics.
    """

    question_text = serializers.CharField(
        source="question.question_text", read_only=True
    )
    chapter_name = serializers.CharField(source="question.chapter.name", read_only=True)

    class Meta:
        model = QuestionAnalytics
        fields = [
            "id",
            "question_text",
            "chapter_name",
            "times_presented",
            "times_answered",
            "times_correct",
            "times_skipped",
            "success_rate",
            "difficulty_index",
            "discrimination_index",
            "average_time_spent",
            "fastest_correct_time",
            "slowest_correct_time",
            "option_selection_stats",
            "distractor_effectiveness",
            "performance_by_ability",
            "quality_score",
            "needs_review",
            "review_reasons",
            "last_calculated",
        ]
        read_only_fields = ["id", "last_calculated"]


class UserDashboardSerializer(serializers.Serializer):
    """
    Serializer for user dashboard with comprehensive analytics.
    """

    user_info = serializers.SerializerMethodField()
    performance_summary = serializers.SerializerMethodField()
    recent_results = serializers.SerializerMethodField()
    subject_performance = serializers.SerializerMethodField()
    recommendations = serializers.SerializerMethodField()
    progress_chart = serializers.SerializerMethodField()

    def get_user_info(self, obj):
        """Get basic user information."""
        user = obj["user"]
        return {
            "phone_number": user.phone_number,
            # CORRECTED: Called the get_full_name() method
            "full_name": user.get_full_name(),
            "role": user.role,
            "join_date": user.created_at,
            "is_verified": user.is_verified,
        }

    def get_performance_summary(self, obj):
        """Get performance summary."""
        analytics = obj.get("analytics")
        if not analytics:
            return {
                "total_exams": 0,
                "average_score": 0.0,
                "pass_rate": 0.0,
                "improvement_trend": "Unknown",
                "consistency_rating": "Unknown",
            }

        return UserPerformanceAnalyticsSerializer(analytics).data

    def get_recent_results(self, obj):
        """Get recent exam results."""
        results = obj.get("recent_results", [])
        return ExamResultSerializer(results, many=True).data[:5]

    def get_subject_performance(self, obj):
        """Get subject-wise performance."""
        performances = obj.get("subject_performances", [])
        return SubjectPerformanceSerializer(performances, many=True).data

    def get_recommendations(self, obj):
        """Get study recommendations."""
        analytics = obj.get("analytics")
        if not analytics:
            return []
        return analytics.study_recommendations

    def get_progress_chart(self, obj):
        """Get data for progress chart."""
        results = obj.get("recent_results", [])
        chart_data = []

        for result in results:
            chart_data.append(
                {
                    "date": result.created_at.date().isoformat(),
                    "score": result.percentage_score,
                    "exam_title": result.exam.title,
                }
            )

        return sorted(chart_data, key=lambda x: x["date"])
