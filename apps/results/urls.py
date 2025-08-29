from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExamResultViewSet,
    UserPerformanceAnalyticsViewSet,
    SubjectPerformanceViewSet,
    ExamAnalyticsViewSet,
    QuestionAnalyticsViewSet,
)

router = DefaultRouter()
router.register(r"exam-results", ExamResultViewSet, basename="exam-results")
router.register(
    r"user-analytics", UserPerformanceAnalyticsViewSet, basename="user-analytics"
)
router.register(
    r"subject-performance", SubjectPerformanceViewSet, basename="subject-performance"
)
router.register(r"exam-analytics", ExamAnalyticsViewSet, basename="exam-analytics")
router.register(
    r"question-analytics", QuestionAnalyticsViewSet, basename="question-analytics"
)

urlpatterns = [
    path("", include(router.urls)),
]
