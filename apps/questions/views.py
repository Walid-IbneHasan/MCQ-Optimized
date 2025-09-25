from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db.models import Q, Avg, Count
from django.shortcuts import get_object_or_404
from .models import Question, QuestionOption, QuestionTag
from .serializers import (
    QuestionListSerializer,
    QuestionDetailSerializer,
    QuestionCreateSerializer,
    QuestionBulkCreateSerializer,
    QuestionTagSerializer,
)
from utils.permissions import IsTeacherOrAbove, CanManageQuestions
from utils.decorators import log_api_call
from apps.core.views import BaseViewSet
import logging

logger = logging.getLogger(__name__)


class QuestionViewSet(BaseViewSet):
    """
    ViewSet for questions.
    """

    parser_classes = [MultiPartParser, FormParser, JSONParser]
    search_fields = ["question_text", "chapter__name", "chapter__subject__name"]

    def get_queryset(self):
        """Get questions with various filters."""
        queryset = (
            Question.objects.filter(is_active=True)
            .select_related("chapter", "chapter__subject", "created_by")
            .prefetch_related("options", "tags")
        )

        # Filter by chapter
        chapter_id = self.request.query_params.get("chapter")
        if chapter_id:
            queryset = queryset.filter(chapter_id=chapter_id)

        # Filter by subject
        subject_id = self.request.query_params.get("subject")
        if subject_id:
            queryset = queryset.filter(chapter__subject_id=subject_id)

        # Filter by difficulty
        difficulty = self.request.query_params.get("difficulty")
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        # Filter by tags
        tags = self.request.query_params.get("tags")
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",")]
            queryset = queryset.filter(tags__name__in=tag_list).distinct()

        return queryset

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in [
            "create",
            "update",
            "partial_update",
            "destroy",
            "bulk_create",
        ]:
            self.permission_classes = [CanManageQuestions]
        elif self.action in ["list", "retrieve"]:
            self.permission_classes = [permissions.IsAuthenticated]
        else:
            self.permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in self.permission_classes]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return QuestionCreateSerializer
        elif self.action == "bulk_create":
            return QuestionBulkCreateSerializer
        elif self.action == "retrieve":
            return QuestionDetailSerializer
        return QuestionListSerializer

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List questions."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                {"success": True, "questions": serializer.data}
            )

        serializer = self.get_serializer(queryset, many=True)
        return Response({"success": True, "questions": serializer.data})

    @log_api_call
    def create(self, request, *args, **kwargs):
        """Create a new question."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            question = serializer.save()
            logger.info(
                f"Question created by {request.user.phone_number}: {question.id}"
            )

            return Response(
                {
                    "success": True,
                    "message": "Question created successfully.",
                    "question": QuestionDetailSerializer(question).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=["post"])
    def bulk_create(self, request):
        """Bulk create questions."""
        serializer = QuestionBulkCreateSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            questions = serializer.save()
            logger.info(
                f"Bulk created {len(questions)} questions by {request.user.phone_number}"
            )

            return Response(
                {
                    "success": True,
                    "message": f"{len(questions)} questions created successfully.",
                    "questions_count": len(questions),
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=["get"])
    def random(self, request):
        """Get random questions for practice."""
        count = min(int(request.query_params.get("count", 10)), 50)  # Max 50 questions
        chapter_id = request.query_params.get("chapter")
        difficulty = request.query_params.get("difficulty")

        queryset = self.get_queryset()

        if chapter_id:
            queryset = queryset.filter(chapter_id=chapter_id)
        if difficulty:
            queryset = queryset.filter(difficulty=difficulty)

        # Get random questions
        random_questions = queryset.order_by("?")[:count]
        serializer = self.get_serializer(random_questions, many=True)

        return Response(
            {
                "success": True,
                "questions": serializer.data,
                "count": len(random_questions),
            }
        )

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """Get question statistics."""
        question = self.get_object()

        # Only teachers and above can see detailed stats
        if not request.user.is_teacher_or_above:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        stats = {
            "times_used": question.times_used,
            "total_attempts": question.total_attempts,
            "correct_attempts": question.correct_attempts,
            "success_rate": question.success_rate,
            "difficulty": question.difficulty,
            "average_time": 0,  # This would need to be tracked separately
        }

        return Response({"success": True, "question_id": question.id, "stats": stats})


class QuestionTagViewSet(BaseViewSet):
    """
    ViewSet for question tags.
    """

    queryset = QuestionTag.objects.all()
    serializer_class = QuestionTagSerializer
    search_fields = ["name", "description"]

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            self.permission_classes = [IsTeacherOrAbove]
        else:
            self.permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in self.permission_classes]

    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get popular tags based on usage."""
        popular_tags = QuestionTag.objects.annotate(
            usage_count=Count("questions")
        ).order_by("-usage_count")[:20]

        serializer = self.get_serializer(popular_tags, many=True)
        return Response({"success": True, "tags": serializer.data})
