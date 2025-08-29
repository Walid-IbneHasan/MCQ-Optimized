from string import Template
import re
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


def render_template(template_string, context):
    """
    Render a template string with context variables.
    Supports both $variable and ${variable} syntax.
    """
    try:
        if not template_string:
            return ""

        # Convert context values to strings
        str_context = {k: str(v) for k, v in context.items()}

        # Use Python's Template for safe substitution
        template = Template(template_string)
        return template.safe_substitute(**str_context)

    except Exception as e:
        logger.error(f"Error rendering template: {str(e)}")
        return template_string


def validate_phone_number(phone_number):
    """
    Validate Bangladeshi phone number format.
    """
    pattern = r"^(\+8801|01)[3-9]\d{8}$"
    return bool(re.match(pattern, phone_number))


def get_notification_context(notification_type, **kwargs):
    """
    Get standard context for different notification types.
    """
    context = {
        "site_name": "MCQ Platform",
        "site_url": "https://mcq-platform.com",
        "current_year": timezone.now().year,
        "timestamp": timezone.now().isoformat(),
    }

    # Add type-specific context
    if notification_type == "exam_completed":
        context.update(
            {
                "exam_title": kwargs.get("exam_title"),
                "score": kwargs.get("score"),
                "passed": kwargs.get("passed"),
                "result_url": f"/results/{kwargs.get('result_id')}",
            }
        )

    elif notification_type == "exam_reminder":
        context.update(
            {
                "exam_title": kwargs.get("exam_title"),
                "start_time": kwargs.get("start_time"),
                "duration": kwargs.get("duration"),
                "exam_url": f"/exams/{kwargs.get('exam_id')}",
            }
        )

    elif notification_type == "subscription_expiring":
        context.update(
            {
                "days_remaining": kwargs.get("days_remaining"),
                "expiry_date": kwargs.get("expiry_date"),
                "renewal_url": "/subscriptions/renew",
            }
        )

    elif notification_type == "subscription_renewed":
        context.update(
            {
                "plan_name": kwargs.get("plan_name"),
                "expiry_date": kwargs.get("expiry_date"),
                "amount": kwargs.get("amount"),
            }
        )

    elif notification_type == "leaderboard_update":
        context.update(
            {
                "new_rank": kwargs.get("new_rank"),
                "old_rank": kwargs.get("old_rank"),
                "leaderboard_type": kwargs.get("leaderboard_type"),
                "leaderboard_url": "/leaderboards",
            }
        )

    elif notification_type == "new_exam_available":
        context.update(
            {
                "exam_title": kwargs.get("exam_title"),
                "subject": kwargs.get("subject"),
                "chapters": kwargs.get("chapters"),
                "exam_url": f"/exams/{kwargs.get('exam_id')}",
            }
        )

    return context


def should_send_notification(user, notification_type):
    """
    Check if notification should be sent based on user preferences and quiet hours.
    """
    from .models import NotificationPreference

    try:
        preference = NotificationPreference.objects.get(
            user=user, notification_type__name=notification_type
        )

        if not preference.is_active:
            return False

        # Check quiet hours
        if preference.quiet_hours_start and preference.quiet_hours_end:
            current_time = timezone.now().time()
            if (
                preference.quiet_hours_start
                <= current_time
                <= preference.quiet_hours_end
            ):
                return False

        return True

    except NotificationPreference.DoesNotExist:
        # Default to sending if no preference exists
        return True


def batch_create_notifications(recipients, notification_type, title, message, **kwargs):
    """
    Create notifications for multiple recipients efficiently.
    """
    from .models import Notification

    notifications = []
    for recipient in recipients:
        notification = Notification(
            recipient=recipient,
            notification_type=notification_type,
            title=title,
            message=message,
            html_content=kwargs.get("html_content"),
            action_url=kwargs.get("action_url", ""),
            action_text=kwargs.get("action_text", ""),
            context_data=kwargs.get("context_data", {}),
            scheduled_for=kwargs.get("scheduled_for"),
        )
        notifications.append(notification)

    # Bulk create
    created_notifications = Notification.objects.bulk_create(notifications)

    return created_notifications


def get_unread_count(user):
    """
    Get unread notification count for a user.
    """
    from .models import Notification

    return Notification.objects.filter(recipient=user, in_app_read=False).count()


def mark_notifications_as_read(user, notification_ids=None):
    """
    Mark notifications as read for a user.
    """
    from .models import Notification

    queryset = Notification.objects.filter(recipient=user, in_app_read=False)

    if notification_ids:
        queryset = queryset.filter(id__in=notification_ids)

    count = queryset.update(
        in_app_read=True, in_app_read_at=timezone.now(), status="read"
    )

    return count
