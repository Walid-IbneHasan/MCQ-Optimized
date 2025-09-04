from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count, Avg
from django.db import models
from .models import Subject, Chapter
from .serializers import SubjectSerializer, ChapterSerializer, ChapterDetailSerializer
from utils.permissions import IsTeacherOrAbove
from apps.core.views import BaseViewSet


class SubjectViewSet(BaseViewSet):
    """
    ViewSet for subjects.
    """

    queryset = Subject.objects.filter(is_active=True)
    serializer_class = SubjectSerializer
    search_fields = ["name", "description", "code"]

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            self.permission_classes = [IsTeacherOrAbove]
        else:
            self.permission_classes = [permissions.AllowAny]
        return [permission() for permission in self.permission_classes]

    def list(self, request, *args, **kwargs):
        """List all active subjects with chapter counts."""
        queryset = self.get_queryset().prefetch_related("chapters")
        serializer = self.get_serializer(queryset, many=True)
        return Response({"success": True, "subjects": serializer.data})

    @action(detail=True, methods=["get"])
    def chapters(self, request, pk=None):
        """Get all chapters for a subject."""
        subject = self.get_object()
        chapters = Chapter.objects.filter(subject=subject, is_active=True).order_by(
            "chapter_number"
        )

        serializer = ChapterSerializer(chapters, many=True)
        return Response(
            {
                "success": True,
                "subject": SubjectSerializer(subject).data,
                "chapters": serializer.data,
            }
        )

    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get popular subjects based on exam participation."""
        popular_subjects = (
            Subject.objects.filter(is_active=True)
            .annotate(exam_count=Count("chapters__exams"))
            .order_by("-exam_count")[:5]
        )

        serializer = self.get_serializer(popular_subjects, many=True)
        return Response({"success": True, "subjects": serializer.data})


class ChapterViewSet(BaseViewSet):
    """
    ViewSet for chapters.
    """

    serializer_class = ChapterSerializer
    search_fields = ["name", "description", "content"]

    def get_queryset(self):
        """Get chapters, optionally filtered by subject."""
        queryset = Chapter.objects.filter(is_active=True).select_related("subject")

        subject_id = self.request.query_params.get("subject")
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)

        return queryset

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            self.permission_classes = [IsTeacherOrAbove]
        else:
            self.permission_classes = [permissions.AllowAny]
        return [permission() for permission in self.permission_classes]

    def get_serializer_class(self):
        """Use detailed serializer for retrieve action."""
        if self.action == "retrieve":
            return ChapterDetailSerializer
        return ChapterSerializer

    def list(self, request, *args, **kwargs):
        """List chapters."""
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def questions(self, request, pk=None):
        """Get all questions for a chapter."""
        chapter = self.get_object()

        # Import here to avoid circular import
        from apps.questions.models import Question
        from apps.questions.serializers import QuestionListSerializer

        questions = Question.objects.filter(
            chapter=chapter, is_active=True
        ).select_related("chapter", "created_by")

        serializer = QuestionListSerializer(questions, many=True)
        return Response(
            {
                "success": True,
                "chapter": ChapterDetailSerializer(chapter).data,
                "questions": serializer.data,
            }
        )

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """Get chapter statistics."""
        chapter = self.get_object()

        from apps.questions.models import Question
        from apps.exams.models import Exam
        from apps.results.models import ExamResult

        # Get statistics
        questions_count = Question.objects.filter(
            chapter=chapter, is_active=True
        ).count()

        exams_count = Exam.objects.filter(chapters=chapter, is_active=True).count()

        # Average score for this chapter
        avg_score = (
            ExamResult.objects.filter(exam__chapters=chapter).aggregate(
                avg_score=models.Avg("percentage_score")
            )["avg_score"]
            or 0
        )

        return Response(
            {
                "success": True,
                "chapter": ChapterDetailSerializer(chapter).data,
                "stats": {
                    "questions_count": questions_count,
                    "exams_count": exams_count,
                    "average_score": round(avg_score, 2),
                },
            }
        )
