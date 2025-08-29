from celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.db.models import Q
from datetime import timedelta
from .models import (
    Notification,
    NotificationPreference,
    NotificationType,
    NotificationLog,
    NotificationTemplate,
    BulkNotification,
)
from utils.redis_client import redis_client
import json
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task
def send_notification(
    notification_id=None, user_id=None, notification_type=None, context=None
):
    """
    Send a notification to a user through configured channels.
    Can either send an existing notification or create and send a new one.
    """
    try:
        if notification_id:
            # Send existing notification
            notification = Notification.objects.select_related(
                "recipient", "notification_type"
            ).get(id=notification_id)
        else:
            # Create new notification
            if not user_id or not notification_type or not context:
                logger.error("Missing required parameters for creating notification")
                return {"success": False, "error": "Missing parameters"}

            user = User.objects.get(id=user_id)
            notif_type = NotificationType.objects.get(name=notification_type)

            # Generate notification content from template
            title, message, html_content = generate_notification_content(
                notif_type, context
            )

            notification = Notification.objects.create(
                recipient=user,
                notification_type=notif_type,
                title=title,
                message=message,
                html_content=html_content,
                context_data=context,
                action_url=context.get("action_url", ""),
                action_text=context.get("action_text", ""),
            )

        # Check user preferences
        preference = NotificationPreference.objects.filter(
            user=notification.recipient,
            notification_type=notification.notification_type,
        ).first()

        if not preference:
            # Use defaults from notification type
            preference = NotificationPreference(
                email_enabled=notification.notification_type.default_email,
                sms_enabled=notification.notification_type.default_sms,
                in_app_enabled=notification.notification_type.default_in_app,
            )

        # Check quiet hours
        if preference.quiet_hours_start and preference.quiet_hours_end:
            current_time = timezone.now().time()
            if (
                preference.quiet_hours_start
                <= current_time
                <= preference.quiet_hours_end
            ):
                # Schedule for after quiet hours
                next_send_time = timezone.now().replace(
                    hour=preference.quiet_hours_end.hour,
                    minute=preference.quiet_hours_end.minute,
                ) + timedelta(minutes=1)

                send_notification.apply_async(
                    args=[notification.id], eta=next_send_time
                )

                logger.info(
                    f"Notification {notification.id} scheduled for after quiet hours"
                )
                return {"success": True, "scheduled": True}

        results = {"email": False, "sms": False, "in_app": False}

        # Send via email
        if preference.email_enabled and notification.recipient.email:
            results["email"] = send_email_notification(notification)

        # Send via SMS
        if preference.sms_enabled:
            results["sms"] = send_sms_notification(notification)

        # Send via in-app (always mark as sent for in-app)
        if preference.in_app_enabled:
            notification.in_app_sent = True
            notification.save(update_fields=["in_app_sent"])
            results["in_app"] = True

            # Send real-time notification via WebSocket
            send_websocket_notification(notification)

        # Update notification status
        if any(results.values()):
            notification.status = "sent"
        else:
            notification.status = "failed"
        notification.save(update_fields=["status"])

        logger.info(f"Notification {notification.id} sent: {results}")
        return {"success": True, "results": results}

    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        return {"success": False, "error": str(e)}


def send_email_notification(notification):
    """
    Send notification via email.
    """
    try:
        from django.core.mail import send_mail
        from django.conf import settings

        subject = notification.title
        message = notification.message
        html_message = notification.html_content or message

        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.recipient.email],
            html_message=html_message,
            fail_silently=False,
        )

        notification.email_sent = True
        notification.email_sent_at = timezone.now()
        notification.email_delivered = True
        notification.save(
            update_fields=["email_sent", "email_sent_at", "email_delivered"]
        )

        # Log success
        NotificationLog.objects.create(
            notification=notification,
            delivery_method="email",
            success=True,
            provider_name="Django Mail",
        )

        return True

    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")

        # Log failure
        NotificationLog.objects.create(
            notification=notification,
            delivery_method="email",
            success=False,
            error_message=str(e),
        )

        return False


def send_sms_notification(notification):
    """
    Send notification via SMS.
    """
    try:
        from utils.sms_api import send_sms

        # Truncate message for SMS (160 chars)
        sms_message = notification.message[:160]

        result = send_sms(
            phone_number=notification.recipient.phone_number, message=sms_message
        )

        if result["success"]:
            notification.sms_sent = True
            notification.sms_sent_at = timezone.now()
            notification.sms_delivered = True
            notification.save(
                update_fields=["sms_sent", "sms_sent_at", "sms_delivered"]
            )

            # Log success
            NotificationLog.objects.create(
                notification=notification,
                delivery_method="sms",
                success=True,
                provider_name="SMS Provider",
                provider_message_id=result.get("message_id"),
            )

            return True
        else:
            raise Exception(result.get("error", "SMS sending failed"))

    except Exception as e:
        logger.error(f"Error sending SMS notification: {str(e)}")

        # Log failure
        NotificationLog.objects.create(
            notification=notification,
            delivery_method="sms",
            success=False,
            error_message=str(e),
        )

        return False


def send_websocket_notification(notification):
    """
    Send real-time notification via WebSocket.
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()

        # Send to user's personal channel
        async_to_sync(channel_layer.group_send)(
            f"user_{notification.recipient.id}",
            {
                "type": "notification_message",
                "notification": {
                    "id": str(notification.id),
                    "title": notification.title,
                    "message": notification.message,
                    "action_url": notification.action_url,
                    "action_text": notification.action_text,
                    "type": notification.notification_type.name,
                    "created_at": notification.created_at.isoformat(),
                },
            },
        )

        return True

    except Exception as e:
        logger.error(f"Error sending WebSocket notification: {str(e)}")
        return False


def generate_notification_content(notification_type, context):
    """
    Generate notification content from templates.
    """
    try:
        # Get template for the notification type
        template = NotificationTemplate.objects.filter(
            notification_type=notification_type, template_type="in_app", is_active=True
        ).first()

        if template:
            from .utils import render_template

            title = render_template(
                template.subject_template or notification_type.display_name, context
            )
            message = render_template(template.content_template, context)
            html_content = (
                render_template(template.html_template, context)
                if template.html_template
                else None
            )
        else:
            # Default content if no template
            title = notification_type.display_name
            message = context.get("message", "You have a new notification")
            html_content = None

        return title, message, html_content

    except Exception as e:
        logger.error(f"Error generating notification content: {str(e)}")
        return notification_type.display_name, str(context), None


@shared_task
def process_bulk_notification(bulk_notification_id):
    """
    Process and send bulk notifications.
    """
    try:
        bulk_notif = BulkNotification.objects.get(id=bulk_notification_id)

        if bulk_notif.status != "scheduled":
            bulk_notif.status = "sending"
            bulk_notif.started_at = timezone.now()
            bulk_notif.save(update_fields=["status", "started_at"])

        # Get recipients
        if bulk_notif.recipient_type == "all_users":
            recipients = User.objects.filter(is_active=True)
        elif bulk_notif.recipient_type == "students":
            recipients = User.objects.filter(role="student", is_active=True)
        elif bulk_notif.recipient_type == "teachers":
            recipients = User.objects.filter(role="teacher", is_active=True)
        elif bulk_notif.recipient_type == "subscribers":
            from apps.subscriptions.models import Subscription

            recipients = User.objects.filter(
                subscriptions__is_active=True, is_active=True
            ).distinct()
        else:  # custom
            recipients = User.objects.filter(
                id__in=bulk_notif.custom_recipients or [], is_active=True
            )

        # Update total recipients
        bulk_notif.total_recipients = recipients.count()
        bulk_notif.save(update_fields=["total_recipients"])

        # Create notifications for each recipient
        sent_count = 0
        for recipient in recipients:
            notification = Notification.objects.create(
                recipient=recipient,
                notification_type=bulk_notif.notification_type,
                title=bulk_notif.notification_title,
                message=bulk_notif.notification_message,
                html_content=bulk_notif.notification_html_content,
                action_url=bulk_notif.notification_action_url or "",
                action_text=bulk_notif.notification_action_text or "",
            )

            # Send notification
            send_notification.delay(notification.id)
            sent_count += 1

        # Update bulk notification status
        bulk_notif.status = "completed"
        bulk_notif.completed_at = timezone.now()
        bulk_notif.sent_count = sent_count
        bulk_notif.save(update_fields=["status", "completed_at", "sent_count"])

        logger.info(
            f"Bulk notification {bulk_notification_id} completed: {sent_count} sent"
        )
        return {"success": True, "sent_count": sent_count}

    except BulkNotification.DoesNotExist:
        logger.error(f"Bulk notification {bulk_notification_id} not found")
        return {"success": False, "error": "Bulk notification not found"}
    except Exception as e:
        logger.error(f"Error processing bulk notification: {str(e)}")

        # Update status to failed
        try:
            bulk_notif = BulkNotification.objects.get(id=bulk_notification_id)
            bulk_notif.status = "failed"
            bulk_notif.save(update_fields=["status"])
        except:
            pass

        return {"success": False, "error": str(e)}


@shared_task
def process_notification_digest():
    """
    Process and send notification digests.
    Run hourly/daily/weekly based on user preferences.
    """
    try:
        # Get users with digest preferences
        preferences = NotificationPreference.objects.exclude(
            digest_frequency="immediate"
        ).select_related("user")

        for preference in preferences:
            # Check if it's time to send digest
            should_send = False

            if preference.digest_frequency == "hourly":
                should_send = True
            elif preference.digest_frequency == "daily":
                # Send at 9 AM
                if timezone.now().hour == 9:
                    should_send = True
            elif preference.digest_frequency == "weekly":
                # Send on Monday at 9 AM
                if timezone.now().weekday() == 0 and timezone.now().hour == 9:
                    should_send = True

            if should_send:
                send_notification_digest.delay(preference.user.id)

        return {"success": True}

    except Exception as e:
        logger.error(f"Error processing notification digests: {str(e)}")
        return {"success": False, "error": str(e)}


@shared_task
def send_notification_digest(user_id):
    """
    Send notification digest to a specific user.
    """
    try:
        user = User.objects.get(id=user_id)

        # Get unread notifications
        notifications = Notification.objects.filter(
            recipient=user,
            in_app_read=False,
            created_at__gte=timezone.now() - timedelta(days=7),
        ).order_by("-created_at")[:20]

        if not notifications.exists():
            return {"success": True, "message": "No notifications to send"}

        # Create digest email content
        from django.template.loader import render_to_string

        html_content = render_to_string(
            "notifications/digest_email.html",
            {
                "user": user,
                "notifications": notifications,
                "count": notifications.count(),
            },
        )

        # Send email
        from django.core.mail import send_mail
        from django.conf import settings

        send_mail(
            subject=f"Your notification digest - {notifications.count()} updates",
            message="You have new notifications. Please check your account.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )

        logger.info(
            f"Sent digest to user {user_id} with {notifications.count()} notifications"
        )
        return {"success": True, "count": notifications.count()}

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return {"success": False, "error": "User not found"}
    except Exception as e:
        logger.error(f"Error sending notification digest: {str(e)}")
        return {"success": False, "error": str(e)}


@shared_task
def cleanup_old_notifications():
    """
    Clean up old read notifications.
    Run daily.
    """
    try:
        # Delete read notifications older than 30 days
        cutoff_date = timezone.now() - timedelta(days=30)

        old_notifications = Notification.objects.filter(
            in_app_read=True, created_at__lt=cutoff_date
        )

        count = old_notifications.count()
        old_notifications.delete()

        logger.info(f"Cleaned up {count} old notifications")
        return f"Cleaned up {count} old notifications"

    except Exception as e:
        logger.error(f"Error cleaning up old notifications: {str(e)}")
        raise
