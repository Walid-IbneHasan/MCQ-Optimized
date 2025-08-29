from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Count, Case, When, IntegerField
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    NotificationType,
    NotificationPreference,
    Notification,
    NotificationTemplate,
    NotificationLog,
    BulkNotification,
)
from .serializers import (
    NotificationTypeSerializer,
    NotificationPreferenceSerializer,
    NotificationListSerializer,
    NotificationDetailSerializer,
    NotificationCreateSerializer,
    NotificationTemplateSerializer,
    NotificationLogSerializer,
    BulkNotificationSerializer,
    MarkAsReadSerializer,
    NotificationStatsSerializer,
)
from utils.permissions import IsTeacherOrAbove
from utils.decorators import log_api_call
from apps.core.views import BaseViewSet
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationViewSet(BaseViewSet):
    """
    ViewSet for user notifications.
    """

    search_fields = ["title", "message"]

    def get_queryset(self):
        """Get notifications for the current user."""
        queryset = Notification.objects.filter(
            recipient=self.request.user
        ).select_related("notification_type")

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by read status
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            is_read = is_read.lower() == "true"
            queryset = queryset.filter(in_app_read=is_read)

        # Filter by notification type
        notification_type = self.request.query_params.get("type")
        if notification_type:
            queryset = queryset.filter(notification_type__name=notification_type)

        # Filter by date range
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        return queryset.order_by("-created_at")

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return NotificationCreateSerializer
        elif self.action == "retrieve":
            return NotificationDetailSerializer
        return NotificationListSerializer

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List user notifications with unread count."""
        queryset = self.filter_queryset(self.get_queryset())

        # Get unread count
        unread_count = queryset.filter(in_app_read=False).count()

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data["unread_count"] = unread_count
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "success": True,
                "notifications": serializer.data,
                "unread_count": unread_count,
            }
        )

    @log_api_call
    def retrieve(self, request, *args, **kwargs):
        """Get notification details and mark as read."""
        notification = self.get_object()

        # Mark as read automatically when viewed
        if not notification.in_app_read:
            notification.mark_as_read()

        serializer = self.get_serializer(notification)
        return Response({"success": True, "notification": serializer.data})

    @action(detail=False, methods=["post"])
    def mark_as_read(self, request):
        """Mark multiple notifications as read."""
        serializer = MarkAsReadSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            notification_ids = serializer.validated_data["notification_ids"]

            notifications = Notification.objects.filter(
                id__in=notification_ids, recipient=request.user, in_app_read=False
            )

            count = notifications.count()
            for notification in notifications:
                notification.mark_as_read()

            return Response(
                {"success": True, "message": f"{count} notifications marked as read"}
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=["post"])
    def mark_all_as_read(self, request):
        """Mark all notifications as read."""
        notifications = Notification.objects.filter(
            recipient=request.user, in_app_read=False
        )

        count = notifications.count()
        notifications.update(
            in_app_read=True, in_app_read_at=timezone.now(), status="read"
        )

        return Response(
            {"success": True, "message": f"{count} notifications marked as read"}
        )

    @action(detail=False, methods=["delete"])
    def clear_all(self, request):
        """Clear all read notifications."""
        notifications = Notification.objects.filter(
            recipient=request.user, in_app_read=True
        )

        count = notifications.count()
        notifications.delete()

        return Response({"success": True, "message": f"{count} notifications cleared"})

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get notification statistics."""
        notifications = Notification.objects.filter(recipient=request.user)

        # Calculate statistics
        stats = {
            "total_notifications": notifications.count(),
            "unread_count": notifications.filter(in_app_read=False).count(),
            "read_count": notifications.filter(in_app_read=True).count(),
            "by_type": {},
            "by_status": {},
        }

        # Group by notification type
        type_counts = notifications.values("notification_type__display_name").annotate(
            count=Count("id")
        )

        for item in type_counts:
            stats["by_type"][item["notification_type__display_name"]] = item["count"]

        # Group by status
        status_counts = notifications.values("status").annotate(count=Count("id"))
        for item in status_counts:
            stats["by_status"][item["status"]] = item["count"]

        # Get recent notifications
        recent_notifications = notifications.order_by("-created_at")[:5]

        return Response(
            {
                "success": True,
                "stats": stats,
                "recent_notifications": NotificationListSerializer(
                    recent_notifications, many=True
                ).data,
            }
        )


class NotificationPreferenceViewSet(BaseViewSet):
    """
    ViewSet for notification preferences.
    """

    serializer_class = NotificationPreferenceSerializer

    def get_queryset(self):
        """Get notification preferences for current user."""
        return NotificationPreference.objects.filter(
            user=self.request.user
        ).select_related("notification_type")

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List all notification preferences with defaults."""
        # Get all notification types
        notification_types = NotificationType.objects.filter(is_active=True)

        preferences = []
        for notif_type in notification_types:
            preference, created = NotificationPreference.objects.get_or_create(
                user=request.user,
                notification_type=notif_type,
                defaults={
                    "email_enabled": notif_type.default_email,
                    "sms_enabled": notif_type.default_sms,
                    "in_app_enabled": notif_type.default_in_app,
                },
            )
            preferences.append(preference)

        serializer = self.get_serializer(preferences, many=True)
        return Response({"success": True, "preferences": serializer.data})

    @action(detail=False, methods=["post"])
    def bulk_update(self, request):
        """Update multiple notification preferences at once."""
        updates = request.data.get("updates", [])

        updated_count = 0
        for update in updates:
            try:
                preference = NotificationPreference.objects.get(
                    id=update.get("id"), user=request.user
                )

                # Update fields
                for field in [
                    "email_enabled",
                    "sms_enabled",
                    "in_app_enabled",
                    "digest_frequency",
                    "is_active",
                ]:
                    if field in update:
                        setattr(preference, field, update[field])

                preference.save()
                updated_count += 1

            except NotificationPreference.DoesNotExist:
                continue

        return Response(
            {"success": True, "message": f"{updated_count} preferences updated"}
        )

    @action(detail=False, methods=["post"])
    def enable_all(self, request):
        """Enable all notification channels."""
        NotificationPreference.objects.filter(user=request.user).update(
            email_enabled=True, sms_enabled=True, in_app_enabled=True, is_active=True
        )

        return Response({"success": True, "message": "All notifications enabled"})

    @action(detail=False, methods=["post"])
    def disable_all(self, request):
        """Disable all notification channels."""
        NotificationPreference.objects.filter(user=request.user).update(
            email_enabled=False, sms_enabled=False, in_app_enabled=False
        )

        return Response({"success": True, "message": "All notifications disabled"})


class NotificationTypeViewSet(BaseViewSet):
    """
    ViewSet for notification types (admin only).
    """

    queryset = NotificationType.objects.filter(is_active=True)
    serializer_class = NotificationTypeSerializer
    permission_classes = [IsTeacherOrAbove]
    search_fields = ["name", "display_name", "description"]

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List all notification types."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)

        return Response({"success": True, "notification_types": serializer.data})


class BulkNotificationViewSet(BaseViewSet):
    """
    ViewSet for bulk notifications (admin/teacher only).
    """

    serializer_class = BulkNotificationSerializer
    permission_classes = [IsTeacherOrAbove]
    search_fields = ["title", "description"]

    def get_queryset(self):
        """Get bulk notifications."""
        queryset = BulkNotification.objects.all().select_related(
            "notification_type", "created_by"
        )

        # Filter by status
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by("-created_at")

    @log_api_call
    def create(self, request, *args, **kwargs):
        """Create and schedule bulk notification."""
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            bulk_notification = serializer.save(created_by=request.user)

            # Schedule the bulk notification
            from .tasks import process_bulk_notification

            if bulk_notification.scheduled_for:
                # Schedule for later
                process_bulk_notification.apply_async(
                    args=[bulk_notification.id], eta=bulk_notification.scheduled_for
                )
            else:
                # Send immediately
                process_bulk_notification.delay(bulk_notification.id)

            return Response(
                {
                    "success": True,
                    "message": "Bulk notification created",
                    "bulk_notification": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel a scheduled bulk notification."""
        bulk_notification = self.get_object()

        if bulk_notification.status not in ["draft", "scheduled"]:
            return Response(
                {
                    "success": False,
                    "error": "Cannot cancel notification in current status",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        bulk_notification.status = "cancelled"
        bulk_notification.save(update_fields=["status"])

        return Response({"success": True, "message": "Bulk notification cancelled"})

    @action(detail=True, methods=["get"])
    def recipients(self, request, pk=None):
        """Get list of recipients for bulk notification."""
        bulk_notification = self.get_object()

        # Get recipients based on type
        if bulk_notification.recipient_type == "all_users":
            users = User.objects.filter(is_active=True)
        elif bulk_notification.recipient_type == "students":
            users = User.objects.filter(role="student", is_active=True)
        elif bulk_notification.recipient_type == "teachers":
            users = User.objects.filter(role="teacher", is_active=True)
        elif bulk_notification.recipient_type == "subscribers":
            from apps.subscriptions.models import Subscription

            users = User.objects.filter(
                subscriptions__is_active=True, is_active=True
            ).distinct()
        else:  # custom
            user_ids = bulk_notification.custom_recipients or []
            users = User.objects.filter(id__in=user_ids, is_active=True)

        from apps.authentication.serializers import UserProfileSerializer

        serializer = UserProfileSerializer(users[:100], many=True)  # Limit to 100

        return Response(
            {
                "success": True,
                "total_recipients": users.count(),
                "sample_recipients": serializer.data,
            }
        )


class NotificationTemplateViewSet(BaseViewSet):
    """
    ViewSet for notification templates (admin only).
    """

    queryset = NotificationTemplate.objects.filter(is_active=True)
    serializer_class = NotificationTemplateSerializer
    permission_classes = [IsTeacherOrAbove]

    def get_queryset(self):
        """Get templates with filters."""
        queryset = super().get_queryset()

        # Filter by notification type
        notif_type = self.request.query_params.get("notification_type")
        if notif_type:
            queryset = queryset.filter(notification_type_id=notif_type)

        # Filter by template type
        template_type = self.request.query_params.get("template_type")
        if template_type:
            queryset = queryset.filter(template_type=template_type)

        # Filter by language
        language = self.request.query_params.get("language")
        if language:
            queryset = queryset.filter(language=language)

        return queryset.select_related("notification_type")

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        """Preview a notification template with sample data."""
        template = self.get_object()
        sample_data = request.data.get("sample_data", {})

        from .utils import render_template

        try:
            rendered = render_template(template.content_template, sample_data)
            html_rendered = None
            if template.html_template:
                html_rendered = render_template(template.html_template, sample_data)

            return Response(
                {
                    "success": True,
                    "preview": {
                        "content": rendered,
                        "html": html_rendered,
                        "subject": (
                            render_template(template.subject_template, sample_data)
                            if template.subject_template
                            else None
                        ),
                    },
                }
            )
        except Exception as e:
            return Response(
                {"success": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST
            )
