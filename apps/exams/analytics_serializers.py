# apps/exams/analytics_serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from .models import Exam, ExamSession, ExamAnswer
from apps.results.models import ExamResult
from apps.questions.models import Question

User = get_user_model()


class ExamParticipantSerializer(serializers.ModelSerializer):
    """Serializer for exam participants with their performance."""

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    user_phone = serializers.CharField(source="user.phone_number", read_only=True)
    user_role = serializers.CharField(source="user.role", read_only=True)
    session_details = serializers.SerializerMethodField()
    performance_summary = serializers.SerializerMethodField()

    class Meta:
        model = ExamResult
        fields = [
            "id",
            "user_name",
            "user_phone",
            "user_role",
            "total_questions",
            "attempted_questions",
            "correct_answers",
            "wrong_answers",
            "unanswered_questions",
            "marks_obtained",
            "score_percentage",
            "is_passed",
            "grade",
            "time_taken_seconds",
            "session_details",
            "performance_summary",
            "created_at",
        ]

    def get_session_details(self, obj):
        """Get session details."""
        session = obj.session
        return {
            "id": str(session.id),
            "status": session.status,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "duration_minutes": session.duration_minutes,
            "tab_switches": session.tab_switches,
            "ip_address": session.ip_address,
            "user_agent": session.user_agent[:100] if session.user_agent else None,
        }

    def get_performance_summary(self, obj):
        """Get performance summary by difficulty and subject."""
        # Get all answers for this session
        answers = ExamAnswer.objects.filter(session=obj.session).select_related(
            "question"
        )

        # Group by difficulty
        difficulty_stats = {
            "easy": {"attempted": 0, "correct": 0},
            "medium": {"attempted": 0, "correct": 0},
            "hard": {"attempted": 0, "correct": 0},
        }

        # Group by subject
        subject_stats = {}

        for answer in answers:
            question = answer.question
            difficulty = question.difficulty
            subject_name = question.chapter.subject.name

            # Difficulty stats
            if answer.selected_option:
                difficulty_stats[difficulty]["attempted"] += 1
                if answer.is_correct:
                    difficulty_stats[difficulty]["correct"] += 1

            # Subject stats
            if subject_name not in subject_stats:
                subject_stats[subject_name] = {
                    "attempted": 0,
                    "correct": 0,
                    "total_marks": 0,
                    "obtained_marks": 0,
                }

            if answer.selected_option:
                subject_stats[subject_name]["attempted"] += 1
                if answer.is_correct:
                    subject_stats[subject_name]["correct"] += 1

            subject_stats[subject_name]["total_marks"] += question.marks
            subject_stats[subject_name]["obtained_marks"] += answer.marks_awarded

        return {
            "difficulty_breakdown": difficulty_stats,
            "subject_breakdown": subject_stats,
        }


class QuestionAnalyticsSerializer(serializers.Serializer):
    """Serializer for question-wise analytics."""

    question_id = serializers.CharField()
    question_text = serializers.CharField()
    question_number = serializers.IntegerField()
    difficulty = serializers.CharField()
    marks = serializers.FloatField()
    chapter_name = serializers.CharField()
    subject_name = serializers.CharField()

    # Statistics
    total_attempts = serializers.IntegerField()
    correct_attempts = serializers.IntegerField()
    wrong_attempts = serializers.IntegerField()
    unanswered = serializers.IntegerField()
    success_rate = serializers.FloatField()
    average_time_spent = serializers.FloatField()

    # Option-wise breakdown
    option_statistics = serializers.DictField()

    # User performance for this question
    user_responses = serializers.ListField()


class ExamAnalyticsDetailSerializer(serializers.Serializer):
    """Comprehensive exam analytics serializer."""

    exam_info = serializers.DictField()
    participation_stats = serializers.DictField()
    performance_stats = serializers.DictField()
    time_analysis = serializers.DictField()
    question_analytics = QuestionAnalyticsSerializer(many=True)
    participants = ExamParticipantSerializer(many=True)
    top_performers = serializers.ListField()
    struggling_participants = serializers.ListField()
    recommendations = serializers.ListField()


class UserExamDetailSerializer(serializers.Serializer):
    """Detailed breakdown for a specific user's exam attempt."""

    user_info = serializers.DictField()
    session_info = serializers.DictField()
    overall_performance = serializers.DictField()
    question_by_question = serializers.ListField()
    time_analysis = serializers.DictField()
    comparison_with_others = serializers.DictField()
    recommendations = serializers.ListField()


class ExamComparisonSerializer(serializers.Serializer):
    """Compare multiple exam attempts or users."""

    comparison_type = serializers.CharField()  # 'users' or 'attempts'
    participants = serializers.ListField()
    metrics_comparison = serializers.DictField()
    question_wise_comparison = serializers.ListField()
    insights = serializers.ListField()
