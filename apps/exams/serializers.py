from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from .models import Exam, ExamSession, ExamAnswer, ExamQuestion
from apps.subjects.serializers import ChapterSerializer
from apps.questions.serializers import QuestionListSerializer, QuestionOptionSerializer
from apps.questions.models import Question, QuestionOption
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class ExamListSerializer(serializers.ModelSerializer):
    """
    Serializer for exam list.
    """

    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True
    )
    chapters_count = serializers.SerializerMethodField()
    can_start_now = serializers.ReadOnlyField()
    is_scheduled_active = serializers.ReadOnlyField()

    class Meta:
        model = Exam
        fields = [
            "id",
            "title",
            "description",
            "exam_type",
            "total_questions",
            "duration_minutes",
            "scheduled_start",
            "scheduled_end",
            "marks_per_question",
            "negative_marking_enabled",
            "negative_marks",
            "passing_percentage",
            "is_active",
            "is_public",
            "requires_subscription",
            "allow_retakes",
            "max_attempts",
            "created_by_name",
            "chapters_count",
            "can_start_now",
            "is_scheduled_active",
            "total_attempts",
            "average_score",
            "created_at",
        ]
        read_only_fields = ["id", "total_attempts", "average_score", "created_at"]

    def get_chapters_count(self, obj):
        return obj.chapters.count()


class ExamDetailSerializer(ExamListSerializer):
    """
    Detailed serializer for exam with chapters.
    """

    chapters = ChapterSerializer(many=True, read_only=True)

    class Meta(ExamListSerializer.Meta):
        fields = ExamListSerializer.Meta.fields + [
            "chapters",
            "questions_per_chapter",
            "difficulty_distribution",
        ]


class ExamCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating exams.
    """

    chapters = serializers.ListField(child=serializers.UUIDField(), write_only=True)

    class Meta:
        model = Exam
        fields = [
            "title",
            "description",
            "exam_type",
            "chapters",
            "total_questions",
            "duration_minutes",
            "time_per_question",
            "allow_custom_duration",
            "max_duration_minutes",
            "scheduled_start",
            "scheduled_end",
            "marks_per_question",
            "negative_marking_enabled",
            "negative_marks",
            "passing_percentage",
            "is_public",
            "requires_subscription",
            "allow_retakes",
            "max_attempts",
            "randomize_questions",
            "randomize_options",
            "auto_submit_on_time_up",
            "grace_period_seconds",
        ]

    def validate_chapters(self, value):
        """Validate chapters exist and are active."""
        from apps.subjects.models import Chapter

        if len(value) == 0:
            raise serializers.ValidationError("At least one chapter is required.")

        chapters = Chapter.objects.filter(id__in=value, is_active=True)
        if len(chapters) != len(value):
            raise serializers.ValidationError(
                "One or more chapters are invalid or inactive."
            )

        return value

    def validate(self, attrs):
        """Validate exam configuration."""
        # Validate scheduled exam dates
        if attrs.get("exam_type") == "scheduled":
            start_date = attrs.get("scheduled_start")
            end_date = attrs.get("scheduled_end")

            if not start_date or not end_date:
                raise serializers.ValidationError(
                    "Scheduled exams must have start and end dates."
                )

            if start_date >= end_date:
                raise serializers.ValidationError("End date must be after start date.")

            if start_date <= timezone.now():
                raise serializers.ValidationError("Start date must be in the future.")

        # Validate duration settings
        if attrs.get("allow_custom_duration") and not attrs.get("max_duration_minutes"):
            attrs["max_duration_minutes"] = attrs.get("duration_minutes", 50) * 2

        return attrs

    def create(self, validated_data):
        """Create exam with chapters."""
        chapters_data = validated_data.pop("chapters")
        validated_data["created_by"] = self.context["request"].user

        exam = Exam.objects.create(**validated_data)

        # Add chapters
        from apps.subjects.models import Chapter

        chapters = Chapter.objects.filter(id__in=chapters_data)
        exam.chapters.set(chapters)

        logger.info(f"Exam created by {exam.created_by.phone_number}: {exam.id}")
        return exam


class ExamSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for exam sessions.
    """

    exam_detail = ExamListSerializer(source="exam", read_only=True)
    time_remaining_seconds = serializers.ReadOnlyField()
    is_time_up = serializers.ReadOnlyField()

    class Meta:
        model = ExamSession
        fields = [
            "id",
            "exam",
            "exam_detail",
            "status",
            "started_at",
            "ended_at",
            "submitted_at",
            "current_question_index",
            "answers_submitted",
            "time_spent_seconds",
            "duration_minutes",
            "time_remaining_seconds",
            "is_time_up",
            "total_score",
            "percentage_score",
            "is_passed",
            "tab_switches",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "started_at",
            "ended_at",
            "submitted_at",
            "time_spent_seconds",
            "total_score",
            "percentage_score",
            "is_passed",
            "created_at",
        ]


class ExamStartSerializer(serializers.Serializer):
    """
    Serializer for starting an exam.
    """

    custom_duration = serializers.IntegerField(required=False, min_value=1)

    def validate_custom_duration(self, value):
        """Validate custom duration."""
        # Get exam from context instead of initial_data
        exam = self.context.get("exam")
        if exam:
            if not exam.allow_custom_duration:
                raise serializers.ValidationError(
                    "Custom duration not allowed for this exam."
                )

            max_duration = exam.max_duration_minutes or exam.duration_minutes
            if value > max_duration:
                raise serializers.ValidationError(
                    f"Duration cannot exceed {max_duration} minutes."
                )

        return value


class ExamAnswerSerializer(serializers.ModelSerializer):
    """
    Serializer for exam answers.
    """

    question_text = serializers.CharField(
        source="question.question_text", read_only=True
    )
    selected_option_text = serializers.CharField(
        source="selected_option.option_text", read_only=True
    )

    class Meta:
        model = ExamAnswer
        fields = [
            "id",
            "question",
            "question_text",
            "selected_option",
            "selected_option_text",
            "is_correct",
            "marks_awarded",
            "time_spent_seconds",
            "is_marked_for_review",
            "answered_at",
        ]
        read_only_fields = ["id", "is_correct", "marks_awarded", "answered_at"]


class ExamSubmissionSerializer(serializers.Serializer):
    """
    Serializer for exam submission.
    """

    session_id = serializers.UUIDField()
    answers = serializers.ListField(child=serializers.DictField(), allow_empty=True)

    def validate_session_id(self, value):
        """Validate session exists and belongs to user."""
        user = self.context["request"].user
        try:
            session = ExamSession.objects.get(id=value, user=user, status="in_progress")
            return session
        except ExamSession.DoesNotExist:
            raise serializers.ValidationError("Invalid or inactive session.")

    def validate_answers(self, value):
        """Validate answer format."""
        for answer in value:
            if "question_id" not in answer:
                raise serializers.ValidationError(
                    "Question ID is required for each answer."
                )
            # selected_option_id can be None for unanswered questions
        return value


class ExamQuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for exam questions during exam session.
    """

    question_detail = QuestionListSerializer(source="question", read_only=True)
    options = serializers.SerializerMethodField()

    class Meta:
        model = ExamQuestion
        fields = [
            "question_number",
            "question_detail",
            "options",
            "visited_count",
            "time_spent_seconds",
        ]

    def get_options(self, obj):
        """Get options in the order specified for this session."""
        options = obj.question.options.all()

        # If options_order is specified, reorder accordingly
        if obj.options_order:
            ordered_options = []
            for option_id in obj.options_order:
                try:
                    option = options.get(id=option_id)
                    ordered_options.append(option)
                except QuestionOption.DoesNotExist:
                    pass
            options = ordered_options

        # Remove is_correct from options during exam
        options_data = QuestionOptionSerializer(options, many=True).data
        for option_data in options_data:
            option_data.pop("is_correct", None)

        return options_data
