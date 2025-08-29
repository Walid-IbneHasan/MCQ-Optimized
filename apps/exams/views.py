from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Avg
from .models import Exam, ExamSession, ExamAnswer, ExamQuestion
from .serializers import (
    ExamListSerializer,
    ExamDetailSerializer,
    ExamCreateSerializer,
    ExamSessionSerializer,
    ExamStartSerializer,
    ExamAnswerSerializer,
    ExamSubmissionSerializer,
    ExamQuestionSerializer,
)
from utils.permissions import IsTeacherOrAbove, HasActiveSubscription
from utils.decorators import log_api_call, require_subscription
from utils.redis_client import redis_client
from apps.core.views import BaseViewSet
from apps.subscriptions.models import Subscription, SubscriptionUsage
import logging
import random
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample,
    OpenApiResponse,
    inline_serializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()



@extend_schema_view(
    list=extend_schema(
        summary='List available exams',
        description='''
        Retrieve a list of available exams based on user permissions and filters.
        
        **Filtering Options:**
        - `type`: Filter by exam type (self_paced, scheduled, practice)
        - `subject`: Filter by subject ID
        - `chapter`: Filter by chapter ID
        - `search`: Search in exam title and description
        
        **Permission Levels:**
        - Students: Only public exams
        - Teachers/Moderators/Admins: All exams
        
        **Response includes:**
        - Exam basic information
        - Availability status
        - User's attempt history summary
        ''',
        parameters=[
            OpenApiParameter(
                name='type',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Filter by exam type',
                enum=['self_paced', 'scheduled', 'practice']
            ),
            OpenApiParameter(
                name='subject',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Filter by subject ID (UUID)'
            ),
            OpenApiParameter(
                name='search',
                type=str,
                location=OpenApiParameter.QUERY,
                description='Search in exam title and description'
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name='ExamListResponse',
                    fields={
                        'success': serializers.BooleanField(default=True),
                        'exams': ExamListSerializer(many=True),
                        'count': serializers.IntegerField(),
                        'next': serializers.URLField(allow_null=True),
                        'previous': serializers.URLField(allow_null=True),
                    }
                ),
                description='List of available exams'
            )
        },
        tags=['Exams']
    ),
    create=extend_schema(
        summary='Create new exam',
        description='''
        Create a new exam. Only available to Teachers, Moderators, and Admins.
        
        **Required Fields:**
        - title: Exam title
        - chapters: List of chapter IDs
        - total_questions: Number of questions
        - duration_minutes: Exam duration
        
        **Exam Types:**
        - `self_paced`: Students can take anytime
        - `scheduled`: Available only during specified time window
        - `practice`: Free practice exam (no subscription required)
        
        **Scheduling:**
        For scheduled exams, both `scheduled_start` and `scheduled_end` are required.
        ''',
        request=ExamCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=ExamDetailSerializer,
                description='Exam created successfully'
            ),
            400: 'Validation errors',
            403: 'Permission denied - Teachers and above only'
        },
        tags=['Exams']
    )
)
class ExamViewSet(BaseViewSet):
    """
    ViewSet for exams.
    """

    search_fields = [
        "title",
        "description",
        "chapters__name",
        "chapters__subject__name",
    ]

    def get_queryset(self):
        """Get exams based on user permissions and filters."""
        user = self.request.user
        queryset = Exam.objects.filter(is_active=True)

        # Filter based on user role
        if not user.is_teacher_or_above:
            queryset = queryset.filter(is_public=True)

        # Filter by exam type
        exam_type = self.request.query_params.get("type")
        if exam_type:
            queryset = queryset.filter(exam_type=exam_type)

        # Filter by subject
        subject_id = self.request.query_params.get("subject")
        if subject_id:
            queryset = queryset.filter(chapters__subject_id=subject_id).distinct()

        # Filter by chapter
        chapter_id = self.request.query_params.get("chapter")
        if chapter_id:
            queryset = queryset.filter(chapters_id=chapter_id)

        return queryset.select_related("created_by").prefetch_related("chapters")

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            self.permission_classes = [IsTeacherOrAbove]
        elif self.action in ["start_exam", "submit_exam"]:
            self.permission_classes = [permissions.IsAuthenticated]
        else:
            self.permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in self.permission_classes]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return ExamCreateSerializer
        elif self.action == "retrieve":
            return ExamDetailSerializer
        elif self.action == "start_exam":
            return ExamStartSerializer
        elif self.action == "submit_exam":
            return ExamSubmissionSerializer
        return ExamListSerializer

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List available exams."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                {"success": True, "exams": serializer.data}
            )

        serializer = self.get_serializer(queryset, many=True)
        return Response({"success": True, "exams": serializer.data})

    @log_api_call
    def retrieve(self, request, *args, **kwargs):
        """Get exam details."""
        exam = self.get_object()
        serializer = self.get_serializer(exam)

        # Get user's attempt history for this exam
        user_attempts = ExamSession.objects.filter(
            exam=exam, user=request.user
        ).order_by("-created_at")[:5]

        attempts_data = ExamSessionSerializer(user_attempts, many=True).data

        return Response(
            {
                "success": True,
                "exam": serializer.data,
                "user_attempts": attempts_data,
                "can_attempt": self._can_user_attempt_exam(request.user, exam),
            }
        )

    def _can_user_attempt_exam(self, user, exam):
        """Check if user can attempt this exam."""
        # Check if exam is active
        if not exam.can_start_now:
            return {"can_attempt": False, "reason": "Exam is not available"}

        # Check subscription requirement
        if exam.requires_subscription and not user.is_teacher_or_above:
            if not Subscription.objects.filter(user=user, is_active=True).exists():
                return {"can_attempt": False, "reason": "Active subscription required"}

        # Check maximum attempts
        if exam.max_attempts > 0:
            attempts_count = ExamSession.objects.filter(
                exam=exam, user=user, status__in=["completed", "auto_submitted"]
            ).count()

            if attempts_count >= exam.max_attempts:
                return {
                    "can_attempt": False,
                    "reason": f"Maximum {exam.max_attempts} attempts reached",
                }

        # Check if user has an active session
        active_session = ExamSession.objects.filter(
            exam=exam, user=user, status="in_progress"
        ).first()

        if active_session:
            return {
                "can_attempt": False,
                "reason": "You have an active session for this exam",
                "active_session_id": active_session.id,
            }

        return {"can_attempt": True, "reason": "Can start exam"}

    @action(detail=True, methods=["post"])
    @require_subscription
    def start_exam(self, request, pk=None):
        """Start an exam session."""
        exam = self.get_object()
        serializer = ExamStartSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            # Check if user can attempt this exam
            can_attempt = self._can_user_attempt_exam(request.user, exam)
            if not can_attempt["can_attempt"]:
                return Response(
                    {"success": False, "error": can_attempt["reason"]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Use subscription attempt if required
            if exam.requires_subscription and not request.user.is_teacher_or_above:
                subscription = Subscription.objects.filter(
                    user=request.user, is_active=True
                ).first()

                if not subscription or not subscription.use_exam_attempt():
                    return Response(
                        {
                            "success": False,
                            "error": "No exam attempts remaining in your subscription",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            with transaction.atomic():
                # Create exam session
                duration = serializer.validated_data.get(
                    "custom_duration", exam.duration_minutes
                )

                session = ExamSession.objects.create(
                    exam=exam,
                    user=request.user,
                    duration_minutes=duration,
                    ip_address=self._get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )

                # Generate questions for this session
                questions = exam.get_questions(request.user)
                question_ids = [q.id for q in questions]
                session.session_questions = question_ids


@extend_schema_view(
    start_exam=extend_schema(
        summary='Start an exam session',
        description='''
        Start a new exam session for the authenticated user.
        
        **Prerequisites:**
        - Active subscription (unless free exam or staff user)
        - Exam must be available (time window for scheduled exams)
        - No active session for the same exam
        - Remaining attempts available (if max_attempts set)
        
        **Process:**
        1. Validates exam availability and user eligibility
        2. Uses subscription attempt (if required)
        3. Creates exam session with randomized questions
        4. Returns session details for real-time connection
        
        **Response includes:**
        - Session ID for WebSocket connection
        - Exam questions and options (randomized if enabled)
        - Timer information
        ''',
        request=ExamStartSerializer,
        responses={
            201: OpenApiResponse(
                response=inline_serializer(
                    name='ExamStartResponse',
                    fields={
                        'success': serializers.BooleanField(default=True),
                        'message': serializers.CharField(),
                        'session': ExamSessionSerializer(),
                    }
                ),
                description='Exam session started successfully',
                examples=[
                    OpenApiExample(
                        'Exam Started',
                        value={
                            'success': True,
                            'message': 'Exam started successfully',
                            'session': {
                                'id': 'session-uuid-here',
                                'exam_detail': {
                                    'id': 'exam-uuid-here',
                                    'title': 'Mathematics Chapter 1 Test'
                                },
                                'duration_minutes': 60,
                                'status': 'in_progress',
                                'time_remaining_seconds': 3600
                            }
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description='Cannot start exam',
                examples=[
                    OpenApiExample(
                        'No Subscription',
                        value={
                            'success': False,
                            'error': 'Active subscription required'
                        }
                    ),
                    OpenApiExample(
                        'Exam Not Available',
                        value={
                            'success': False,
                            'error': 'Exam is not available at this time'
                        }
                    )
                ]
            )
        },
        tags=['Exam Sessions']
    ),
    submit_exam=extend_schema(
        summary='Submit exam answers',
        description='''
        Submit exam answers and complete the session.
        
        **Request Format:**
        - session_id: UUID of the active exam session
        - answers: Array of answer objects with question_id and selected_option_id
        
        **Answer Object Format:**
        ```json
        {
            "question_id": "uuid",
            "selected_option_id": "uuid", // null for unanswered
            "time_spent_seconds": 45,
            "is_marked_for_review": false
        }
        ```
        
        **Process:**
        1. Validates session belongs to user and is active
        2. Saves all provided answers
        3. Submits session and triggers score calculation
        4. Returns session summary
        
        **Auto-submission:**
        Sessions are automatically submitted when time expires with a 30-second grace period.
        ''',
        request=ExamSubmissionSerializer,
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name='ExamSubmissionResponse',
                    fields={
                        'success': serializers.BooleanField(default=True),
                        'message': serializers.CharField(),
                        'session': ExamSessionSerializer(),
                    }
                ),
                description='Exam submitted successfully'
            ),
            400: 'Invalid session or submission data',
            404: 'Session not found'
        },
        tags=['Exam Sessions']
    )
)