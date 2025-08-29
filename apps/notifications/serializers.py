from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    NotificationType,
    NotificationPreference,
    Notification,
    NotificationTemplate,
    NotificationLog,
    BulkNotification,
)

User = get_user_model()


class NotificationTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for notification types.
    """

    class Meta:
        model = NotificationType
        fields = [
            "id",
            "name",
            "display_name",
            "description",
            "priority",
            "is_system_generated",
            "default_email",
            "default_sms",
            "default_in_app",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """
    Serializer for notification preferences.
    """

    notification_type_detail = NotificationTypeSerializer(
        source="notification_type", read_only=True
    )

    class Meta:
        model = NotificationPreference
        fields = [
            "id",
            "notification_type",
            "notification_type_detail",
            "email_enabled",
            "sms_enabled",
            "in_app_enabled",
            "quiet_hours_start",
            "quiet_hours_end",
            "digest_frequency",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        """Validate quiet hours."""
        start = attrs.get("quiet_hours_start")
        end = attrs.get("quiet_hours_end")

        if start and end and start >= end:
            raise serializers.ValidationError(
                "Quiet hours end time must be after start time."
            )

        return attrs


class NotificationListSerializer(serializers.ModelSerializer):
    """
    Serializer for notification list.
    """

    notification_type_name = serializers.CharField(
        source="notification_type.display_name", read_only=True
    )
    is_read = serializers.ReadOnlyField()
    is_delivered = serializers.ReadOnlyField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type_name",
            "title",
            "message",
            "action_url",
            "action_text",
            "status",
            "in_app_read",
            "in_app_read_at",
            "is_read",
            "is_delivered",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class NotificationDetailSerializer(NotificationListSerializer):
    """
    Detailed serializer for notifications.
    """

    notification_type_detail = NotificationTypeSerializer(
        source="notification_type", read_only=True
    )

    class Meta(NotificationListSerializer.Meta):
        fields = NotificationListSerializer.Meta.fields + [
            "notification_type_detail",
            "html_content",
            "email_sent",
            "email_sent_at",
            "email_delivered",
            "sms_sent",
            "sms_sent_at",
            "sms_delivered",
            "in_app_sent",
            "context_data",
        ]


class NotificationCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating notifications.
    """

    recipient_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )
    send_immediately = serializers.BooleanField(default=True, write_only=True)

    class Meta:
        model = Notification
        fields = [
            "recipient",
            "recipient_ids",
            "notification_type",
            "title",
            "message",
            "html_content",
            "action_url",
            "action_text",
            "context_data",
            "scheduled_for",
            "send_immediately",
        ]

    def validate_recipient_ids(self, value):
        """Validate recipient IDs exist."""
        if value:
            users = User.objects.filter(id__in=value, is_active=True)
            if len(users) != len(value):
                raise serializers.ValidationError(
                    "One or more recipient IDs are invalid."
                )
        return value

    def create(self, validated_data):
        """Create notification(s)."""
        recipient_ids = validated_data.pop("recipient_ids", [])
        send_immediately = validated_data.pop("send_immediately", True)

        notifications = []

        # Create for single recipient
        if validated_data.get("recipient"):
            notification = Notification.objects.create(**validated_data)
            notifications.append(notification)

            if send_immediately:
                from .tasks import send_notification

                send_notification.delay(notification.id)

        # Create for multiple recipients
        for recipient_id in recipient_ids:
            notification_data = validated_data.copy()
            notification_data["recipient_id"] = recipient_id
            notification = Notification.objects.create(**notification_data)
            notifications.append(notification)

            if send_immediately:
                from .tasks import send_notification

                send_notification.delay(notification.id)

        return notifications[0] if len(notifications) == 1 else notifications


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for notification templates.
    """

    class Meta:
        model = NotificationTemplate
        fields = [
            "id",
            "notification_type",
            "template_type",
            "subject_template",
            "content_template",
            "html_template",
            "available_variables",
            "is_active",
            "language",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class NotificationLogSerializer(serializers.ModelSerializer):
    """
    Serializer for notification logs.
    """

    class Meta:
        model = NotificationLog
        fields = [
            "id",
            "notification",
            "delivery_method",
            "attempt_number",
            "attempted_at",
            "success",
            "response_data",
            "error_message",
            "provider_name",
            "provider_message_id",
        ]
        read_only_fields = ["id", "attempted_at"]


class BulkNotificationSerializer(serializers.ModelSerializer):
    """
    Serializer for bulk notifications.
    """

    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True
    )
    total_recipients = serializers.ReadOnlyField()
    sent_count = serializers.ReadOnlyField()

    class Meta:
        model = BulkNotification
        fields = [
            "id",
            "title",
            "description",
            "notification_type",
            "recipient_type",
            "custom_recipients",
            "notification_title",
            "notification_message",
            "notification_html_content",
            "notification_action_url",
            "notification_action_text",
            "scheduled_for",
            "status",
            "created_by",
            "created_by_name",
            "total_recipients",
            "sent_count",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_by",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]


class MarkAsReadSerializer(serializers.Serializer):
    """
    Serializer for marking notifications as read.
    """

    notification_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False
    )

    def validate_notification_ids(self, value):
        """Validate notification IDs."""
        user = self.context["request"].user
        notifications = Notification.objects.filter(id__in=value, recipient=user)

        if len(notifications) != len(value):
            raise serializers.ValidationError(
                "One or more notification IDs are invalid or don't belong to you."
            )

        return value


class NotificationStatsSerializer(serializers.Serializer):
    """
    Serializer for notification statistics.
    """

    total_notifications = serializers.IntegerField()
    unread_count = serializers.IntegerField()
    read_count = serializers.IntegerField()
    by_type = serializers.DictField()
    by_status = serializers.DictField()
    recent_notifications = NotificationListSerializer(many=True)
