from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExamViewSet,
    ExamSessionViewSet,
    ExamQuestionView,
    ExamAnswerView,
    ExamTimerView,
    ExamSubmissionView,
    ExamProgressView,
)
from .analytics_views import (
    ExamAnalyticsView,
    UserExamDetailView,
    ExamComparisonView,
)
from .question_set_views import QuestionSetViewSet

app_name = "exams"

# Create router for viewsets
router = DefaultRouter()
router.register(r"exams", ExamViewSet, basename="exam")
router.register(r"sessions", ExamSessionViewSet, basename="session")
router.register(r"question-sets", QuestionSetViewSet, basename="question-set")

# Additional URL patterns
urlpatterns = [
    # Include router URLs
    path("", include(router.urls)),
    # Question and Answer management during exam (APIView endpoints)
    path(
        "sessions/<uuid:session_id>/questions/",
        ExamQuestionView.as_view(),
        name="session-questions",
    ),
    path(
        "sessions/<uuid:session_id>/questions/<int:question_number>/",
        ExamQuestionView.as_view(),
        name="session-question-detail",
    ),
    path(
        "sessions/<uuid:session_id>/answer/",
        ExamAnswerView.as_view(),
        name="session-answer",
    ),
    path(
        "sessions/<uuid:session_id>/answer/<uuid:question_id>/",
        ExamAnswerView.as_view(),
        name="session-answer-detail",
    ),
    # Timer and Progress endpoints
    path(
        "sessions/<uuid:session_id>/timer/",
        ExamTimerView.as_view(),
        name="session-timer",
    ),
    path(
        "sessions/<uuid:session_id>/progress/",
        ExamProgressView.as_view(),
        name="session-progress",
    ),
    # Final submission
    path(
        "sessions/<uuid:session_id>/submit/",
        ExamSubmissionView.as_view(),
        name="session-submit",
    ),
    path(
        "exams/get_chapter_questions/",
        ExamViewSet.as_view({"post": "get_chapter_questions"}),
        name="get-chapter-questions",
    ),
    path(
        "exams/validate_question_selection/",
        ExamViewSet.as_view({"post": "validate_question_selection"}),
        name="validate-question-selection",
    ),
    path(
        "exams/<uuid:pk>/preview_questions/",
        ExamViewSet.as_view({"get": "preview_questions"}),
        name="preview-exam-questions",
    ),
    path(
        "sessions/<uuid:pk>/bulk_submit_answers/",
        ExamSessionViewSet.as_view({"post": "bulk_submit_answers"}),
        name="bulk-submit-answers",
    ),
    # Analytics endpoints (Teachers/Admins only)
    path(
        "exams/<uuid:exam_id>/analytics/",
        ExamAnalyticsView.as_view(),
        name="exam-analytics",
    ),
    path(
        "exams/<uuid:exam_id>/participants/<uuid:user_id>/",
        UserExamDetailView.as_view(),
        name="user-exam-detail",
    ),
    path(
        "exams/<uuid:exam_id>/compare/",
        ExamComparisonView.as_view(),
        name="exam-comparison",
    ),
    path(
        "exams/<uuid:pk>/detailed_analytics/",
        ExamViewSet.as_view({"get": "detailed_analytics"}),
        name="exam-detailed-analytics",
    ),
]
