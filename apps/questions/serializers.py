import json
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Question, QuestionOption, QuestionTag, QuestionTagging
from apps.subjects.serializers import ChapterSerializer

User = get_user_model()


class QuestionOptionSerializer(serializers.ModelSerializer):
    """
    Serializer for question options.
    """

    class Meta:
        model = QuestionOption
        fields = ["id", "option_text", "option_image", "option_order", "is_correct"]
        read_only_fields = ["id"]


class QuestionTagSerializer(serializers.ModelSerializer):
    """
    Serializer for question tags.
    """

    class Meta:
        model = QuestionTag
        fields = ["id", "name", "description", "color"]
        read_only_fields = ["id"]


class QuestionListSerializer(serializers.ModelSerializer):
    """
    Serializer for question list (without correct answers).
    """

    chapter_name = serializers.CharField(source="chapter.name", read_only=True)
    subject_name = serializers.CharField(source="chapter.subject.name", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True
    )
    options = QuestionOptionSerializer(many=True, read_only=True)
    tags = QuestionTagSerializer(many=True, read_only=True)
    success_rate = serializers.ReadOnlyField()
    options_count = serializers.ReadOnlyField()

    class Meta:
        model = Question
        fields = [
            "id",
            "chapter",
            "chapter_name",
            "subject_name",
            "question_text",
            "question_image",
            "difficulty",
            "marks",
            "negative_marks",
            "allow_negative_marking",
            "is_active",
            "options",
            "tags",
            "success_rate",
            "options_count",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "success_rate", "options_count", "created_at"]


class QuestionDetailSerializer(QuestionListSerializer):
    """
    Detailed serializer for questions (includes explanations for teachers).
    """

    chapter_detail = ChapterSerializer(source="chapter", read_only=True)

    class Meta(QuestionListSerializer.Meta):
        fields = QuestionListSerializer.Meta.fields + [
            "explanation",
            "chapter_detail",
            "times_used",
            "total_attempts",
        ]


class QuestionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating questions with image support.
    """

    options = serializers.CharField()  # Will be JSON string from FormData
    tags = serializers.CharField(
        required=False, allow_blank=True
    )  # Will be JSON string from FormData
    question_image = serializers.ImageField(required=False)

    class Meta:
        model = Question
        fields = [
            "chapter",
            "question_text",
            "question_image",
            "explanation",
            "difficulty",
            "marks",
            "negative_marks",
            "allow_negative_marking",
            "options",
            "tags",
        ]

    def validate_options(self, value):
        """Validate and parse question options from JSON string."""
        try:
            if isinstance(value, str):
                options_data = json.loads(value)
            else:
                options_data = value
        except (json.JSONDecodeError, TypeError):
            raise serializers.ValidationError("Invalid options format.")

        if not isinstance(options_data, list):
            raise serializers.ValidationError("Options must be a list.")

        if len(options_data) < 2:
            raise serializers.ValidationError("Question must have at least 2 options.")
        if len(options_data) > 6:
            raise serializers.ValidationError(
                "Question cannot have more than 6 options."
            )

        correct_options = [opt for opt in options_data if opt.get("is_correct")]
        if len(correct_options) != 1:
            raise serializers.ValidationError(
                "Question must have exactly one correct option."
            )

        # Validate option orders
        option_orders = [opt.get("option_order") for opt in options_data]
        if len(set(option_orders)) != len(option_orders):
            raise serializers.ValidationError("Option orders must be unique.")

        return options_data

    def validate_tags(self, value):
        """Validate and parse tags from JSON string."""
        if not value:
            return []

        try:
            if isinstance(value, str):
                tags_data = json.loads(value)
            else:
                tags_data = value
        except (json.JSONDecodeError, TypeError):
            raise serializers.ValidationError("Invalid tags format.")

        if not isinstance(tags_data, list):
            raise serializers.ValidationError("Tags must be a list.")

        return tags_data

    def create(self, validated_data):
        """Create question with options, tags, and image."""
        options_data = validated_data.pop("options")
        tags_data = validated_data.pop("tags", [])

        # Set created_by from request user
        validated_data["created_by"] = self.context["request"].user

        # Create question
        question = Question.objects.create(**validated_data)

        # Create options
        for option_data in options_data:
            QuestionOption.objects.create(question=question, **option_data)

        # Handle tags
        for tag_name in tags_data:
            tag_name = tag_name.strip()
            if tag_name:
                tag, created = QuestionTag.objects.get_or_create(name=tag_name)
                QuestionTagging.objects.create(question=question, tag=tag)

        return question

    def update(self, instance, validated_data):
        """Update question with options, tags, and image."""
        options_data = validated_data.pop("options", None)
        tags_data = validated_data.pop("tags", None)

        # Update question fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update options if provided
        if options_data is not None:
            # Delete existing options
            instance.options.all().delete()

            # Create new options
            for option_data in options_data:
                QuestionOption.objects.create(question=instance, **option_data)

        # Update tags if provided
        if tags_data is not None:
            # Clear existing tags
            QuestionTagging.objects.filter(question=instance).delete()

            # Add new tags
            for tag_name in tags_data:
                tag_name = tag_name.strip()
                if tag_name:
                    tag, created = QuestionTag.objects.get_or_create(name=tag_name)
                    QuestionTagging.objects.create(question=instance, tag=tag)

        return instance


class QuestionBulkCreateSerializer(serializers.Serializer):
    """
    Serializer for bulk question creation.
    """

    chapter = serializers.UUIDField()
    questions = serializers.ListField(child=serializers.DictField())

    def validate_chapter(self, value):
        """Validate chapter exists."""
        from apps.subjects.models import Chapter

        try:
            return Chapter.objects.get(id=value, is_active=True)
        except Chapter.DoesNotExist:
            raise serializers.ValidationError("Invalid chapter.")

    def validate_questions(self, value):
        """Validate questions data."""
        if not value:
            raise serializers.ValidationError("At least one question is required.")

        chapter_id = self.initial_data.get("chapter")
        validated_questions = []

        for question_data in value:
            # Add chapter ID to each question
            question_data["chapter"] = chapter_id

            # Convert options and tags to JSON strings for validation
            if "options" in question_data:
                question_data["options"] = json.dumps(question_data["options"])
            if "tags" in question_data:
                question_data["tags"] = json.dumps(question_data["tags"])

            # Validate using QuestionCreateSerializer
            serializer = QuestionCreateSerializer(data=question_data)
            if not serializer.is_valid():
                raise serializers.ValidationError(
                    f"Question validation failed: {serializer.errors}"
                )

            validated_questions.append(serializer.validated_data)

        return validated_questions

    def create(self, validated_data):
        """Bulk create questions."""
        chapter = validated_data["chapter"]
        questions_data = validated_data["questions"]

        created_questions = []
        for question_data in questions_data:
            # The chapter is already set in validate_questions
            # But we need to set created_by
            question_data["created_by"] = self.context["request"].user

            # Create question directly since it's already validated
            options_data = question_data.pop("options")
            tags_data = question_data.pop("tags", [])

            # Create question
            question = Question.objects.create(**question_data)

            # Create options
            for option_data in options_data:
                QuestionOption.objects.create(question=question, **option_data)

            # Handle tags
            for tag_name in tags_data:
                tag_name = tag_name.strip()
                if tag_name:
                    tag, created = QuestionTag.objects.get_or_create(name=tag_name)
                    QuestionTagging.objects.create(question=question, tag=tag)

            created_questions.append(question)

        return created_questions
