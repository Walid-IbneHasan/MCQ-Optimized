from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.core.models import BaseModel
from apps.core.managers import SoftDeleteManager

User = get_user_model()


class NotificationType(BaseModel):
    """
    Different types of notifications in the system.
    """

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    # Notification behavior
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )
    is_system_generated = models.BooleanField(default=True)

    # Default delivery methods
    default_email = models.BooleanField(default=True)
    default_sms = models.BooleanField(default=False)
    default_in_app = models.BooleanField(default=True)

    # Template settings
    email_template = models.CharField(max_length=200, blank=True)
    sms_template = models.CharField(max_length=500, blank=True)
    in_app_template = models.CharField(max_length=500, blank=True)

    is_active = models.BooleanField(default=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "notification_types"
        ordering = ["display_name"]

    def __str__(self):
        return self.display_name


class NotificationPreference(BaseModel):
    """
    User preferences for different notification types.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notification_preferences"
    )
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)

    # Delivery method preferences
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    in_app_enabled = models.BooleanField(default=True)

    # Timing preferences
    quiet_hours_start = models.TimeField(null=True, blank=True)  # Start of quiet hours
    quiet_hours_end = models.TimeField(null=True, blank=True)  # End of quiet hours

    # Frequency settings
    digest_frequency = models.CharField(
        max_length=20,
        choices=[
            ("immediate", "Immediate"),
            ("hourly", "Hourly"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
        ],
        default="immediate",
    )

    is_active = models.BooleanField(default=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "notification_preferences"
        unique_together = ["user", "notification_type"]

    def __str__(self):
        return f"{self.user.full_name} - {self.notification_type.display_name}"


class Notification(BaseModel):
    """
    Individual notification instances.
    """

    NOTIFICATION_STATUS = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("failed", "Failed"),
        ("read", "Read"),
    ]

    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)

    # Notification content
    title = models.CharField(max_length=200)
    message = models.TextField()

    # Rich content support
    html_content = models.TextField(blank=True)
    action_url = models.URLField(blank=True)
    action_text = models.CharField(max_length=100, blank=True)

    # Metadata
    context_data = models.JSONField(
        default=dict, blank=True
    )  # Additional context for templates

    # Delivery tracking
    email_sent = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_delivered = models.BooleanField(default=False)

    sms_sent = models.BooleanField(default=False)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    sms_delivered = models.BooleanField(default=False)

    in_app_sent = models.BooleanField(default=False)
    in_app_read = models.BooleanField(default=False)
    in_app_read_at = models.DateTimeField(null=True, blank=True)

    # Scheduling
    scheduled_for = models.DateTimeField(null=True, blank=True)

    # Status and error tracking
    status = models.CharField(
        max_length=20, choices=NOTIFICATION_STATUS, default="pending"
    )
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "status"]),
            models.Index(fields=["notification_type", "status"]),
            models.Index(fields=["scheduled_for"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.recipient.full_name}"

    @property
    def is_read(self):
        """Check if notification has been read (for in-app notifications)."""
        return self.in_app_read

    @property
    def is_delivered(self):
        """Check if notification was successfully delivered through any channel."""
        return self.email_delivered or self.sms_delivered or self.in_app_sent

    def mark_as_read(self):
        """Mark in-app notification as read."""
        if not self.in_app_read:
            self.in_app_read = True
            self.in_app_read_at = timezone.now()
            self.status = "read"
            self.save(update_fields=["in_app_read", "in_app_read_at", "status"])


class NotificationTemplate(BaseModel):
    """
    Templates for different notification types and delivery methods.
    """

    TEMPLATE_TYPES = [
        ("email", "Email"),
        ("sms", "SMS"),
        ("in_app", "In-App"),
    ]

    notification_type = models.ForeignKey(
        NotificationType, on_delete=models.CASCADE, related_name="templates"
    )
    template_type = models.CharField(max_length=10, choices=TEMPLATE_TYPES)

    # Template content
    subject_template = models.CharField(max_length=200, blank=True)  # For email
    content_template = models.TextField()
    html_template = models.TextField(blank=True)  # For email

    # Template variables documentation
    available_variables = models.JSONField(default=list, blank=True)

    # Template settings
    is_active = models.BooleanField(default=True)
    language = models.CharField(max_length=10, default="en")

    objects = SoftDeleteManager()

    class Meta:
        db_table = "notification_templates"
        unique_together = ["notification_type", "template_type", "language"]

    def __str__(self):
        return f"{self.notification_type.display_name} - {self.get_template_type_display()}"


class NotificationLog(BaseModel):
    """
    Detailed logs of notification delivery attempts.
    """

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="logs"
    )

    # Delivery details
    delivery_method = models.CharField(
        max_length=10,
        choices=[
            ("email", "Email"),
            ("sms", "SMS"),
            ("in_app", "In-App"),
        ],
    )

    # Attempt details
    attempt_number = models.PositiveIntegerField(default=1)
    attempted_at = models.DateTimeField(auto_now_add=True)

    # Results
    success = models.BooleanField(default=False)
    response_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    # Provider details (for email/SMS)
    provider_name = models.CharField(max_length=50, blank=True)
    provider_message_id = models.CharField(max_length=100, blank=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "notification_logs"
        ordering = ["-attempted_at"]
        indexes = [
            models.Index(fields=["notification", "delivery_method"]),
            models.Index(fields=["success", "attempted_at"]),
        ]

    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{self.notification.title} - {self.get_delivery_method_display()} ({status})"


class BulkNotification(BaseModel):
    """
    Bulk notification campaigns.
    """

    CAMPAIGN_STATUS = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("sending", "Sending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    RECIPIENT_TYPES = [
        ("all_users", "All Users"),
        ("students", "Students Only"),
        ("teachers", "Teachers Only"),
        ("subscribers", "Active Subscribers"),
        ("custom", "Custom Selection"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    # Campaign settings
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)
    # Campaign content
    notification_title = models.CharField(max_length=200)
    notification_message = models.TextField()
    notification_html_content = models.TextField(blank=True)
    notification_action_url = models.URLField(blank=True)
    notification_action_text = models.CharField(max_length=100, blank=True)

    # Recipients
    recipient_type = models.CharField(max_length=20, choices=RECIPIENT_TYPES)
    custom_recipients = models.JSONField(
        default=list, blank=True
    )  # List of user IDs for custom selection

    # Scheduling
    scheduled_for = models.DateTimeField(null=True, blank=True)

    # Campaign status
    status = models.CharField(max_length=20, choices=CAMPAIGN_STATUS, default="draft")
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_bulk_notifications"
    )

    # Campaign tracking
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    read_count = models.PositiveIntegerField(default=0)

    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "bulk_notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_for"]),
            models.Index(fields=["created_by", "status"]),
        ]

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"

    @property
    def success_rate(self):
        """Calculate delivery success rate."""
        if self.sent_count == 0:
            return 0
        return (self.delivered_count / self.sent_count) * 100

    @property
    def read_rate(self):
        """Calculate read rate."""
        if self.delivered_count == 0:
            return 0
        return (self.read_count / self.delivered_count) * 100
