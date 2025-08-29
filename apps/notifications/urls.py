from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    NotificationViewSet,
    NotificationPreferenceViewSet,
    NotificationTypeViewSet,
    BulkNotificationViewSet,
    NotificationTemplateViewSet,
)

app_name = "notifications"

router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(r"preferences", NotificationPreferenceViewSet, basename="preference")
router.register(r"types", NotificationTypeViewSet, basename="type")
router.register(r"bulk", BulkNotificationViewSet, basename="bulk")
router.register(r"templates", NotificationTemplateViewSet, basename="template")

urlpatterns = [
    path("", include(router.urls)),
]
