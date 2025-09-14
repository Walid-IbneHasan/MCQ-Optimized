import json
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
from rest_framework.views import APIView

logger = logging.getLogger(__name__)
User = get_user_model()


@extend_schema_view(
    list=extend_schema(
        summary="List available exams",
        description="""
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
        """,
        parameters=[
            OpenApiParameter(
                name="type",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by exam type",
                enum=["self_paced", "scheduled", "practice"],
            ),
            OpenApiParameter(
                name="subject",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by subject ID (UUID)",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search in exam title and description",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="ExamListResponse",
                    fields={
                        "success": serializers.BooleanField(default=True),
                        "exams": ExamListSerializer(many=True),
                        "count": serializers.IntegerField(),
                        "next": serializers.URLField(allow_null=True),
                        "previous": serializers.URLField(allow_null=True),
                    },
                ),
                description="List of available exams",
            )
        },
        tags=["Exams"],
    ),
    create=extend_schema(
        summary="Create new exam",
        description="""
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
        """,
        request=ExamCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=ExamDetailSerializer, description="Exam created successfully"
            ),
            400: "Validation errors",
            403: "Permission denied - Teachers and above only",
        },
        tags=["Exams"],
    ),
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

    # Add these methods to your ExamViewSet class in views.py

    def _get_client_ip(self, request):
        """Get client IP address from request."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip

    @action(detail=False, methods=["get"])
    def my_exams(self, request):
        """Get user's exam history."""
        sessions = (
            ExamSession.objects.filter(user=request.user)
            .select_related("exam")
            .order_by("-created_at")
        )

        # Group by exam
        exam_stats = {}
        for session in sessions:
            exam_id = str(session.exam.id)
            if exam_id not in exam_stats:
                exam_stats[exam_id] = {
                    "exam": ExamListSerializer(session.exam).data,
                    "attempts": 0,
                    "best_score": 0,
                    "last_attempt": None,
                }

            exam_stats[exam_id]["attempts"] += 1
            if session.percentage_score > exam_stats[exam_id]["best_score"]:
                exam_stats[exam_id]["best_score"] = session.percentage_score

            if (
                not exam_stats[exam_id]["last_attempt"]
                or session.created_at > exam_stats[exam_id]["last_attempt"]
            ):
                exam_stats[exam_id]["last_attempt"] = session.created_at

        return Response({"success": True, "exam_history": list(exam_stats.values())})

    @action(detail=False, methods=["get"])
    def upcoming_exams(self, request):
        """Get upcoming scheduled exams."""
        upcoming = (
            self.get_queryset()
            .filter(exam_type="scheduled", scheduled_start__gt=timezone.now())
            .order_by("scheduled_start")[:10]
        )

        serializer = self.get_serializer(upcoming, many=True)
        return Response({"success": True, "upcoming_exams": serializer.data})

    @action(detail=True, methods=["get"])
    def get_questions(self, request, pk=None):
        """Get questions for an exam (preview for teachers)."""
        exam = self.get_object()

        # Only teachers can preview questions
        if not request.user.is_teacher_or_above:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        questions = exam.get_questions()
        from apps.questions.serializers import QuestionListSerializer

        serializer = QuestionListSerializer(questions, many=True)
        return Response(
            {"success": True, "questions": serializer.data, "total": len(questions)}
        )

    @action(detail=True, methods=["get"])
    def analytics(self, request, pk=None):
        """Get exam analytics (teachers only)."""
        exam = self.get_object()

        if not request.user.is_teacher_or_above:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        from apps.results.models import ExamAnalytics

        try:
            analytics = ExamAnalytics.objects.get(exam=exam)
            from apps.results.serializers import ExamAnalyticsSerializer

            serializer = ExamAnalyticsSerializer(analytics)
            return Response({"success": True, "analytics": serializer.data})
        except ExamAnalytics.DoesNotExist:
            return Response(
                {
                    "success": True,
                    "analytics": None,
                    "message": "No analytics available yet",
                }
            )

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        """Clone an exam (teachers only)."""
        exam = self.get_object()

        if not request.user.is_teacher_or_above:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Create a copy of the exam
        cloned_exam = Exam.objects.create(
            title=f"{exam.title} (Copy)",
            description=exam.description,
            created_by=request.user,
            exam_type=exam.exam_type,
            total_questions=exam.total_questions,
            duration_minutes=exam.duration_minutes,
            marks_per_question=exam.marks_per_question,
            negative_marking_enabled=exam.negative_marking_enabled,
            negative_marks=exam.negative_marks,
            passing_percentage=exam.passing_percentage,
            is_public=False,  # Make it private by default
            requires_subscription=exam.requires_subscription,
            allow_retakes=exam.allow_retakes,
            max_attempts=exam.max_attempts,
            randomize_questions=exam.randomize_questions,
            randomize_options=exam.randomize_options,
        )

        # Copy chapters
        cloned_exam.chapters.set(exam.chapters.all())

        serializer = ExamDetailSerializer(cloned_exam)
        return Response(
            {
                "success": True,
                "message": "Exam cloned successfully",
                "exam": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def export_exam(self, request, pk=None):
        """Export exam data (teachers only)."""
        exam = self.get_object()

        if not request.user.is_teacher_or_above:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get all exam data
        exam_data = ExamDetailSerializer(exam).data

        # Get questions if requested
        include_questions = (
            request.query_params.get("include_questions", "false").lower() == "true"
        )
        if include_questions:
            questions = exam.get_questions()
            from apps.questions.serializers import QuestionDetailSerializer

            exam_data["questions"] = QuestionDetailSerializer(questions, many=True).data

        # Get results if requested
        include_results = (
            request.query_params.get("include_results", "false").lower() == "true"
        )
        if include_results:
            from apps.results.models import ExamResult
            from apps.results.serializers import ExamResultSerializer

            results = ExamResult.objects.filter(exam=exam)
            exam_data["results"] = ExamResultSerializer(results, many=True).data

        return Response(
            {"success": True, "exam_data": exam_data, "exported_at": timezone.now()}
        )

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


    @action(detail=False, methods=["post"])
    def get_chapter_questions(self, request):
        """Get questions for selected chapters during exam creation."""
        chapter_ids = request.data.get('chapter_ids', [])
        
        if not chapter_ids:
            return Response(
                {"success": False, "error": "Chapter IDs are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from apps.questions.models import Question
        from apps.questions.serializers import QuestionListSerializer
        
        # Get questions grouped by chapter
        chapters_questions = {}
        for chapter_id in chapter_ids:
            questions = Question.objects.filter(
                chapter_id=chapter_id,
                is_active=True
            ).select_related('chapter').prefetch_related('options')
            
            serialized_questions = QuestionListSerializer(questions, many=True).data
            chapters_questions[chapter_id] = {
                'questions': serialized_questions,
                'count': len(serialized_questions)
            }
        
        return Response({
            "success": True,
            "chapters_questions": chapters_questions
        })

    @action(detail=False, methods=["post"])
    def validate_question_selection(self, request):
        """Validate question selection before exam creation."""
        data = request.data
        
        question_selection_method = data.get('question_selection_method', 'random')
        selected_questions = data.get('selected_questions', [])
        new_questions = data.get('new_questions', [])
        total_questions = data.get('total_questions', 0)
        chapters = data.get('chapters', [])
        
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'summary': {}
        }
        
        if question_selection_method == 'manual':
            total_available = len(selected_questions) + len(new_questions)
            validation_result['summary'] = {
                'selected_existing': len(selected_questions),
                'new_questions': len(new_questions),
                'total_available': total_available,
                'required': total_questions
            }
            
            if total_available < total_questions:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"Need {total_questions - total_available} more questions"
                )
            elif total_available > total_questions:
                validation_result['warnings'].append(
                    f"You have {total_available - total_questions} extra questions. "
                    f"Only first {total_questions} will be used."
                )
        
        elif question_selection_method == 'mixed':
            random_count = data.get('random_questions_count', 0)
            manual_count = len(selected_questions) + len(new_questions)
            
            validation_result['summary'] = {
                'manual_questions': manual_count,
                'random_questions': random_count,
                'total_planned': manual_count + random_count,
                'required': total_questions
            }
            
            if (manual_count + random_count) != total_questions:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    "Manual questions + random questions must equal total questions"
                )
        
        elif question_selection_method == 'random':
            # Check if enough questions available in chapters
            from apps.questions.models import Question
            available_questions = Question.objects.filter(
                chapter_id__in=chapters,
                is_active=True
            ).count()
            
            validation_result['summary'] = {
                'available_in_chapters': available_questions,
                'required': total_questions
            }
            
            if available_questions < total_questions:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"Only {available_questions} questions available in selected chapters. "
                    f"Need {total_questions - available_questions} more questions."
                )
        
        return Response({
            "success": True,
            "validation": validation_result
        })

    @action(detail=True, methods=["get"])
    def preview_questions(self, request, pk=None):
        """Preview questions that will be used in the exam."""
        exam = self.get_object()
        
        if not request.user.is_teacher_or_above:
            return Response(
                {"success": False, "error": "Permission denied"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get questions based on selection method
        questions = exam.get_questions(request.user)
        
        from apps.questions.serializers import QuestionDetailSerializer
        serializer = QuestionDetailSerializer(questions, many=True)
        
        return Response({
            "success": True,
            "questions": serializer.data,
            "total": len(questions),
            "selection_method": exam.question_selection_method
        })
    
    
    @action(detail=True, methods=["post"])
    @require_subscription
    def start_exam(self, request, pk=None):
        """Start an exam session."""
        exam = self.get_object()

        # Pass exam in context instead of validating exam_id
        serializer = ExamStartSerializer(
            data=request.data, context={"request": request, "exam": exam}
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
                from apps.subscriptions.models import Subscription

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

            try:
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
                    question_ids = [str(q.id) for q in questions]
                    session.session_questions = question_ids
                    session.save(update_fields=["session_questions"])

                    # Create ExamQuestion records for tracking
                    for i, question in enumerate(questions, 1):
                        ExamQuestion.objects.create(
                            session=session,
                            question=question,
                            question_number=i,
                            options_order=[
                                str(opt.id) for opt in question.options.all()
                            ],
                        )

                    # Start the session
                    session.start_session()

                    # Return success response
                    session_data = ExamSessionSerializer(session).data

                    return Response(
                        {
                            "success": True,
                            "message": "Exam started successfully",
                            "session": session_data,
                        },
                        status=status.HTTP_201_CREATED,
                    )

            except Exception as e:
                logger.error(f"Error starting exam session: {str(e)}")
                return Response(
                    {"success": False, "error": "Failed to start exam session"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # Return validation errors
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema_view(
    start_exam=extend_schema(
        summary="Start an exam session",
        description="""
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
        """,
        request=ExamStartSerializer,
        responses={
            201: OpenApiResponse(
                response=inline_serializer(
                    name="ExamStartResponse",
                    fields={
                        "success": serializers.BooleanField(default=True),
                        "message": serializers.CharField(),
                        "session": ExamSessionSerializer(),
                    },
                ),
                description="Exam session started successfully",
                examples=[
                    OpenApiExample(
                        "Exam Started",
                        value={
                            "success": True,
                            "message": "Exam started successfully",
                            "session": {
                                "id": "session-uuid-here",
                                "exam_detail": {
                                    "id": "exam-uuid-here",
                                    "title": "Mathematics Chapter 1 Test",
                                },
                                "duration_minutes": 60,
                                "status": "in_progress",
                                "time_remaining_seconds": 3600,
                            },
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Cannot start exam",
                examples=[
                    OpenApiExample(
                        "No Subscription",
                        value={
                            "success": False,
                            "error": "Active subscription required",
                        },
                    ),
                    OpenApiExample(
                        "Exam Not Available",
                        value={
                            "success": False,
                            "error": "Exam is not available at this time",
                        },
                    ),
                ],
            ),
        },
        tags=["Exam Sessions"],
    ),
    submit_exam=extend_schema(
        summary="Submit exam answers",
        description="""
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
        """,
        request=ExamSubmissionSerializer,
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="ExamSubmissionResponse",
                    fields={
                        "success": serializers.BooleanField(default=True),
                        "message": serializers.CharField(),
                        "session": ExamSessionSerializer(),
                    },
                ),
                description="Exam submitted successfully",
            ),
            400: "Invalid session or submission data",
            404: "Session not found",
        },
        tags=["Exam Sessions"],
    ),
)
class ExamSessionViewSet(BaseViewSet):
    """
    ViewSet for exam sessions.
    """

    serializer_class = ExamSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get sessions for the current user."""
        return ExamSession.objects.filter(user=self.request.user).select_related(
            "exam", "user"
        )

    @action(detail=False, methods=["get"])
    def my_sessions(self, request):
        """Get user's exam sessions."""
        sessions = self.get_queryset().order_by("-created_at")

        # Filter by status if provided
        status_filter = request.query_params.get("status")
        if status_filter:
            sessions = sessions.filter(status=status_filter)

        page = self.paginate_queryset(sessions)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(
                {"success": True, "sessions": serializer.data}
            )

        serializer = self.get_serializer(sessions, many=True)
        return Response({"success": True, "sessions": serializer.data})

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        """Pause an exam session."""
        session = self.get_object()

        if session.status != "in_progress":
            return Response(
                {"success": False, "error": "Session is not in progress"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.status = "paused"
        session.save(update_fields=["status"])

        return Response({"success": True, "message": "Session paused"})

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """Resume a paused session."""
        session = self.get_object()

        if session.status != "paused":
            return Response(
                {"success": False, "error": "Session is not paused"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.status = "in_progress"
        session.save(update_fields=["status"])

        return Response({"success": True, "message": "Session resumed"})

    @action(detail=True, methods=["post"])
    def abandon(self, request, pk=None):
        """Abandon an exam session."""
        session = self.get_object()

        if session.status in ["completed", "auto_submitted"]:
            return Response(
                {"success": False, "error": "Cannot abandon completed session"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.status = "abandoned"
        session.ended_at = timezone.now()
        session.save(update_fields=["status", "ended_at"])

        return Response({"success": True, "message": "Session abandoned"})

    @action(detail=True, methods=["post"])
    def mark_for_review(self, request, pk=None):
        """Mark a question for review."""
        session = self.get_object()
        question_id = request.data.get("question_id")

        try:
            answer = ExamAnswer.objects.get(session=session, question_id=question_id)
            answer.is_marked_for_review = True
            answer.save(update_fields=["is_marked_for_review"])

            return Response({"success": True, "message": "Question marked for review"})
        except ExamAnswer.DoesNotExist:
            return Response(
                {"success": False, "error": "Answer not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=["get"])
    def validate_session(self, request, pk=None):
        """Validate if session is still active."""
        session = self.get_object()

        is_valid = session.status == "in_progress" and not session.is_time_up

        return Response(
            {
                "success": True,
                "is_valid": is_valid,
                "status": session.status,
                "time_remaining": session.time_remaining_seconds,
            }
        )

    @action(detail=True, methods=["get"])
    def generate_report(self, request, pk=None):
        """Generate detailed report for a session."""
        session = self.get_object()

        if session.status not in ["completed", "auto_submitted"]:
            return Response(
                {
                    "success": False,
                    "error": "Report available only for completed sessions",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get result if exists
        from apps.results.models import ExamResult

        try:
            result = ExamResult.objects.get(session=session)
            from apps.results.serializers import ExamResultDetailSerializer

            result_data = ExamResultDetailSerializer(result).data
        except ExamResult.DoesNotExist:
            result_data = None

        return Response(
            {
                "success": True,
                "session": ExamSessionSerializer(session).data,
                "result": result_data,
            }
        )

    @action(detail=True, methods=["post"])
    def clear_review(self, request, pk=None):
        """Clear review flag for a question."""
        session = self.get_object()
        question_id = request.data.get("question_id")

        try:
            answer = ExamAnswer.objects.get(session=session, question_id=question_id)
            answer.is_marked_for_review = False
            answer.save(update_fields=["is_marked_for_review"])

            return Response({"success": True, "message": "Review flag cleared"})
        except ExamAnswer.DoesNotExist:
            return Response(
                {"success": False, "error": "Answer not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=["post"])
    def navigate_to_question(self, request, pk=None):
        """Navigate to a specific question."""
        session = self.get_object()
        question_number = request.data.get("question_number", 1)

        if session.status != "in_progress":
            return Response(
                {"success": False, "error": "Session is not active"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update current question index
        session.current_question_index = question_number - 1
        session.save(update_fields=["current_question_index"])

        return Response({"success": True, "current_question": question_number})

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        """Get current session status."""
        session = self.get_object()

        return Response(
            {
                "success": True,
                "status": session.status,
                "started_at": session.started_at,
                "time_remaining": session.time_remaining_seconds,
                "answers_submitted": session.answers_submitted,
                "total_questions": session.exam.total_questions,
            }
        )

    @action(detail=True, methods=["post"])
    def submit_exam(self, request, pk=None):
        """Submit the exam session."""
        session = self.get_object()

        if session.status in ["completed", "auto_submitted"]:
            return Response(
                {"success": False, "error": "Exam already submitted"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Process any final answers
        answers = request.data.get("answers", [])
        for answer_data in answers:
            question_id = answer_data.get("question_id")
            selected_option_id = answer_data.get("selected_option_id")

            if question_id:
                ExamAnswer.objects.update_or_create(
                    session=session,
                    question_id=question_id,
                    defaults={"selected_option_id": selected_option_id},
                )

        # Submit the session
        session.submit_session(auto_submitted=False)

        return Response(
            {
                "success": True,
                "message": "Exam submitted successfully",
                "session_id": str(session.id),
            }
        )


class ExamQuestionView(APIView):
    """
    View for handling exam questions during a session.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id, question_number=None):
        """Get questions for an exam session."""
        session = get_object_or_404(ExamSession, id=session_id, user=request.user)

        if session.status != "in_progress":
            return Response(
                {"success": False, "error": "Session is not active"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if question_number:
            # Get specific question
            try:
                exam_question = ExamQuestion.objects.get(
                    session=session, question_number=question_number
                )
                serializer = ExamQuestionSerializer(exam_question)
                return Response({"success": True, "question": serializer.data})
            except ExamQuestion.DoesNotExist:
                return Response(
                    {"success": False, "error": "Question not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            # Get all questions
            exam_questions = ExamQuestion.objects.filter(session=session).order_by(
                "question_number"
            )

            serializer = ExamQuestionSerializer(exam_questions, many=True)
            return Response(
                {
                    "success": True,
                    "questions": serializer.data,
                    "total": exam_questions.count(),
                }
            )


class ExamAnswerView(APIView):
    """
    View for handling answer submission during exam.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        """Submit an answer for a question."""
        session = get_object_or_404(ExamSession, id=session_id, user=request.user)

        if session.status != "in_progress":
            return Response(
                {"success": False, "error": "Session is not active"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        question_id = request.data.get("question_id")
        selected_option_id = request.data.get("selected_option_id")
        time_spent = request.data.get("time_spent_seconds", 0)

        with transaction.atomic():
            answer, created = ExamAnswer.objects.update_or_create(
                session=session,
                question_id=question_id,
                defaults={
                    "selected_option_id": selected_option_id,
                    "time_spent_seconds": time_spent,
                },
            )

            # Update session progress
            session.answers_submitted = ExamAnswer.objects.filter(
                session=session, selected_option__isnull=False
            ).count()
            session.save(update_fields=["answers_submitted"])

            # Cache the answer in Redis for quick access
            cache_key = f"session:{session_id}:answer:{question_id}"
            redis_client.set(
                cache_key,
                json.dumps(
                    {
                        "selected_option_id": (
                            str(selected_option_id) if selected_option_id else None
                        ),
                        "time_spent": time_spent,
                    }
                ),
                ex=3600,  # 1 hour expiry
            )

        return Response(
            {
                "success": True,
                "message": "Answer saved",
                "answer": ExamAnswerSerializer(answer).data,
            }
        )

    def get(self, request, session_id, question_id=None):
        """Get submitted answers."""
        session = get_object_or_404(ExamSession, id=session_id, user=request.user)

        if question_id:
            # Get specific answer
            answer = get_object_or_404(
                ExamAnswer, session=session, question_id=question_id
            )
            serializer = ExamAnswerSerializer(answer)
            return Response({"success": True, "answer": serializer.data})
        else:
            # Get all answers
            answers = ExamAnswer.objects.filter(session=session)
            serializer = ExamAnswerSerializer(answers, many=True)
            return Response(
                {
                    "success": True,
                    "answers": serializer.data,
                    "total_answered": answers.filter(
                        selected_option__isnull=False
                    ).count(),
                }
            )


class ExamTimerView(APIView):
    """
    View for handling exam timer.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        """Get current timer status."""
        session = get_object_or_404(ExamSession, id=session_id, user=request.user)

        return Response(
            {
                "success": True,
                "timer": {
                    "started_at": session.started_at,
                    "duration_minutes": session.duration_minutes,
                    "time_remaining_seconds": session.time_remaining_seconds,
                    "is_time_up": session.is_time_up,
                    "status": session.status,
                },
            }
        )

    def post(self, request, session_id):
        """Update timer (for tracking time spent)."""
        session = get_object_or_404(ExamSession, id=session_id, user=request.user)

        if session.status != "in_progress":
            return Response(
                {"success": False, "error": "Session is not active"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        time_spent = request.data.get("time_spent_seconds", 0)
        session.time_spent_seconds = time_spent
        session.save(update_fields=["time_spent_seconds"])

        return Response({"success": True, "message": "Timer updated"})


class ExamSubmissionView(APIView):
    """
    View for final exam submission.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        """Submit the exam."""
        session = get_object_or_404(ExamSession, id=session_id, user=request.user)

        if session.status in ["completed", "auto_submitted"]:
            return Response(
                {"success": False, "error": "Exam already submitted"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Submit the session
        session.submit_session(auto_submitted=False)

        return Response(
            {
                "success": True,
                "message": "Exam submitted successfully",
                "session_id": str(session.id),
            }
        )


class ExamProgressView(APIView):
    """
    View for tracking exam progress.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        """Get current exam progress."""
        session = get_object_or_404(ExamSession, id=session_id, user=request.user)

        total_questions = session.exam.total_questions
        answered = ExamAnswer.objects.filter(
            session=session, selected_option__isnull=False
        ).count()

        marked_for_review = ExamAnswer.objects.filter(
            session=session, is_marked_for_review=True
        ).count()

        return Response(
            {
                "success": True,
                "progress": {
                    "total_questions": total_questions,
                    "answered": answered,
                    "unanswered": total_questions - answered,
                    "marked_for_review": marked_for_review,
                    "percentage_complete": (
                        (answered / total_questions * 100) if total_questions > 0 else 0
                    ),
                    "current_question_index": session.current_question_index,
                    "time_spent_seconds": session.time_spent_seconds,
                },
            }
        )
