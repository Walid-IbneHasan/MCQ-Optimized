from rest_framework import serializers
from .models import Subject, Chapter


class SubjectSerializer(serializers.ModelSerializer):
    """
    Serializer for subjects.
    """

    chapters_count = serializers.ReadOnlyField()
    questions_count = serializers.ReadOnlyField()

    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "description",
            "code",
            "is_active",
            "sort_order",
            "image",
            "chapters_count",
            "questions_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ChapterSerializer(serializers.ModelSerializer):
    """
    Serializer for chapters.
    """

    subject_name = serializers.CharField(source="subject.name", read_only=True)
    questions_count = serializers.ReadOnlyField()
    exams_count = serializers.ReadOnlyField()

    class Meta:
        model = Chapter
        fields = [
            "id",
            "subject",
            "subject_name",
            "name",
            "description",
            "chapter_number",
            "is_active",
            "difficulty_level",
            "content",
            "questions_count",
            "exams_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ChapterDetailSerializer(ChapterSerializer):
    """
    Detailed serializer for chapters with subject details.
    """

    subject_detail = SubjectSerializer(source="subject", read_only=True)

    class Meta(ChapterSerializer.Meta):
        fields = ChapterSerializer.Meta.fields + ["subject_detail"]
