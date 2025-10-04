# apps/exams/question_set_serializers.py (NEW FILE)

import logging
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import QuestionSet
from apps.subjects.models import Chapter
from apps.questions.models import Question
from apps.questions.serializers import QuestionListSerializer
from django.utils import timezone

logger = logging.getLogger(__name__)

User = get_user_model()


class QuestionSetListSerializer(serializers.ModelSerializer):
    """Serializer for question set list."""

    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )
    chapters_count = serializers.SerializerMethodField()
    chapters_names = serializers.SerializerMethodField()

    class Meta:
        model = QuestionSet
        fields = [
            "id",
            "name",
            "description",
            "created_by_name",
            "total_questions",
            "chapters_count",
            "chapters_names",
            "usage_count",
            "last_used_at",
            "difficulty_distribution",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "usage_count", "last_used_at", "created_at"]

    def get_chapters_count(self, obj):
        return obj.chapters.count()

    def get_chapters_names(self, obj):
        return [f"{ch.subject.name} - {ch.name}" for ch in obj.chapters.all()[:3]]


class QuestionSetDetailSerializer(QuestionSetListSerializer):
    """Detailed serializer with question details."""

    questions_detail = serializers.SerializerMethodField()
    chapters_detail = serializers.SerializerMethodField()

    class Meta(QuestionSetListSerializer.Meta):
        fields = QuestionSetListSerializer.Meta.fields + [
            "questions",
            "questions_detail",
            "chapters_detail",
        ]

    def get_questions_detail(self, obj):
        """Get full question details."""
        questions = (
            Question.objects.filter(id__in=obj.questions, is_active=True)
            .select_related("chapter", "chapter__subject")
            .prefetch_related("options")
        )

        return QuestionListSerializer(questions, many=True).data

    def get_chapters_detail(self, obj):
        """Get chapter details."""
        from apps.subjects.serializers import ChapterSerializer

        return ChapterSerializer(obj.chapters.all(), many=True).data


class QuestionSetCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating question sets."""

    chapters = serializers.ListField(child=serializers.UUIDField(), write_only=True)
    questions = serializers.ListField(child=serializers.UUIDField(), required=True)
    name = serializers.CharField(required=False, allow_blank=True, max_length=200)

    class Meta:
        model = QuestionSet
        fields = [
            "name",
            "description",
            "chapters",
            "questions",
        ]

    def validate_questions(self, value):
        """Validate that questions exist."""
        if not value:
            raise serializers.ValidationError("At least one question is required.")

        # Check if questions exist
        existing_questions = Question.objects.filter(
            id__in=value, is_active=True
        ).values_list("id", flat=True)

        if len(existing_questions) != len(value):
            raise serializers.ValidationError(
                "Some questions do not exist or are inactive."
            )

        return [str(q_id) for q_id in value]

    def validate_chapters(self, value):
        """Validate that chapters exist."""
        if not value:
            raise serializers.ValidationError("At least one chapter is required.")

        existing_chapters = Chapter.objects.filter(id__in=value, is_active=True).count()

        if existing_chapters != len(value):
            raise serializers.ValidationError(
                "Some chapters do not exist or are inactive."
            )

        return value

    def create(self, validated_data):
        """Create question set."""
        chapters_data = validated_data.pop("chapters")
        questions_data = validated_data["questions"]

        # Auto-generate name if not provided
        if not validated_data.get("name"):
            validated_data["name"] = (
                f"Question Set {timezone.now().strftime('%Y-%m-%d %H:%M')}"
            )

        validated_data["created_by"] = self.context["request"].user
        validated_data["total_questions"] = len(questions_data)

        # Calculate difficulty distribution
        questions = Question.objects.filter(id__in=questions_data)
        difficulty_dist = {
            "easy": questions.filter(difficulty="easy").count(),
            "medium": questions.filter(difficulty="medium").count(),
            "hard": questions.filter(difficulty="hard").count(),
        }
        validated_data["difficulty_distribution"] = difficulty_dist

        # Create question set
        question_set = QuestionSet.objects.create(**validated_data)

        # Add chapters
        question_set.chapters.set(Chapter.objects.filter(id__in=chapters_data))

        logger.info(
            f"Question set created: {question_set.id} by {question_set.created_by.phone_number}"
        )

        return question_set


class QuestionSetUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating question sets."""

    class Meta:
        model = QuestionSet
        fields = ["name", "description", "is_active"]
