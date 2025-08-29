from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import QuestionViewSet, QuestionTagViewSet

router = DefaultRouter()
router.register(r"questions", QuestionViewSet, basename="questions")
router.register(r"tags", QuestionTagViewSet, basename="question-tags")

urlpatterns = [
    path("", include(router.urls)),
]
