from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SubjectViewSet, ChapterViewSet

router = DefaultRouter()
router.register(r"subjects", SubjectViewSet, basename="subjects")
router.register(r"chapters", ChapterViewSet, basename="chapters")

urlpatterns = [
    path("", include(router.urls)),
]
