# apps/exams/question_set_views.py (NEW FILE)

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import QuestionSet
from .question_set_serializers import (
    QuestionSetListSerializer,
    QuestionSetDetailSerializer,
    QuestionSetCreateSerializer,
    QuestionSetUpdateSerializer,
)
from utils.permissions import IsTeacherOrAbove
from apps.core.views import BaseViewSet
import logging

logger = logging.getLogger(__name__)


class QuestionSetViewSet(BaseViewSet):
    """ViewSet for question sets."""

    search_fields = ["name", "description"]

    def get_queryset(self):
        """Get question sets."""
        user = self.request.user

        queryset = (
            QuestionSet.objects.filter(is_active=True)
            .select_related("created_by")
            .prefetch_related("chapters")
        )

        # Filter by creator
        if not user.is_teacher_or_above:
            queryset = queryset.filter(created_by=user)

        # Filter by search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search)
            )

        return queryset.order_by("-usage_count", "-created_at")

    def get_permissions(self):
        """Set permissions."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            self.permission_classes = [IsTeacherOrAbove]
        else:
            self.permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in self.permission_classes]

    def get_serializer_class(self):
        """Return appropriate serializer."""
        if self.action == "create":
            return QuestionSetCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return QuestionSetUpdateSerializer
        elif self.action == "retrieve":
            return QuestionSetDetailSerializer
        return QuestionSetListSerializer

    def list(self, request, *args, **kwargs):
        """List question sets."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                {"success": True, "question_sets": serializer.data}
            )

        serializer = self.get_serializer(queryset, many=True)
        return Response({"success": True, "question_sets": serializer.data})

    def create(self, request, *args, **kwargs):
        """Create a new question set."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            question_set = serializer.save()

            return Response(
                {
                    "success": True,
                    "message": "Question set created successfully.",
                    "question_set": QuestionSetDetailSerializer(question_set).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    def retrieve(self, request, *args, **kwargs):
        """Get question set details."""
        question_set = self.get_object()
        serializer = self.get_serializer(question_set)

        return Response(
            {
                "success": True,
                "question_set": serializer.data,
            }
        )

    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get popular question sets."""
        popular_sets = (
            self.get_queryset().filter(usage_count__gt=0).order_by("-usage_count")[:10]
        )

        serializer = self.get_serializer(popular_sets, many=True)

        return Response(
            {
                "success": True,
                "question_sets": serializer.data,
            }
        )

    @action(detail=True, methods=["post"])
    def increment_usage(self, request, pk=None):
        """Increment usage count (called when used in exam creation)."""
        question_set = self.get_object()
        question_set.increment_usage()

        return Response(
            {
                "success": True,
                "message": "Usage count updated.",
                "usage_count": question_set.usage_count,
            }
        )
