from mcq_platform.celery import shared_task
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta
from .models import Subscription, SubscriptionPlan
from apps.core.utils import send_notification_email, send_notification_sms
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task
def check_expired_subscriptions():
    """
    Check and deactivate expired subscriptions.
    """
    try:
        expired_subscriptions = Subscription.objects.filter(
            is_active=True, end_date__lt=timezone.now()
        )

        count = 0
        for subscription in expired_subscriptions:
            subscription.is_active = False
            subscription.save(update_fields=["is_active"])
            count += 1

            logger.info(
                f"Deactivated expired subscription: {subscription.transaction_id}"
            )

            # Send expiration notification
            send_subscription_expired_notification.delay(subscription.id)

        logger.info(f"Deactivated {count} expired subscriptions")
        return f"Deactivated {count} expired subscriptions"

    except Exception as e:
        logger.error(f"Error checking expired subscriptions: {str(e)}")
        raise


@shared_task
def send_subscription_reminders():
    """
    Send subscription renewal reminders.
    """
    try:
        # Get subscriptions expiring in 7 days
        reminder_date = timezone.now() + timedelta(days=7)

        subscriptions_to_remind = Subscription.objects.filter(
            is_active=True,
            end_date__date=reminder_date.date(),
            renewal_reminder_sent=False,
        ).select_related("user", "plan")

        count = 0
        for subscription in subscriptions_to_remind:
            # Send reminder
            send_renewal_reminder.delay(subscription.id)

            # Mark reminder as sent
            subscription.renewal_reminder_sent = True
            subscription.save(update_fields=["renewal_reminder_sent"])
            count += 1

        logger.info(f"Sent {count} subscription renewal reminders")
        return f"Sent {count} subscription renewal reminders"

    except Exception as e:
        logger.error(f"Error sending subscription reminders: {str(e)}")
        raise


@shared_task
def send_subscription_confirmation(subscription_id):
    """
    Send subscription confirmation to user.
    """
    try:
        subscription = Subscription.objects.get(id=subscription_id)
        user = subscription.user

        # Send email confirmation
        if user.email:
            send_notification_email(
                to_email=user.email,
                subject="Subscription Activated Successfully",
                template_name="subscriptions/confirmation_email.html",
                context={
                    "user": user,
                    "subscription": subscription,
                    "plan": subscription.plan,
                },
            )

        # Send SMS confirmation
        message = (
            f"Your {subscription.plan.name} subscription has been activated successfully. "
            f"Valid until {subscription.end_date.strftime('%d %b %Y')}. "
            f"You can take {subscription.plan.exam_limit} exams."
        )
        send_notification_sms(user.phone_number, message)

        logger.info(
            f"Sent subscription confirmation for: {subscription.transaction_id}"
        )

    except Subscription.DoesNotExist:
        logger.error(f"Subscription not found: {subscription_id}")
    except Exception as e:
        logger.error(f"Error sending subscription confirmation: {str(e)}")


@shared_task
def send_renewal_reminder(subscription_id):
    """
    Send subscription renewal reminder.
    """
    try:
        subscription = Subscription.objects.get(id=subscription_id)
        user = subscription.user

        # Send email reminder
        if user.email:
            send_notification_email(
                to_email=user.email,
                subject="Subscription Renewal Reminder",
                template_name="subscriptions/renewal_reminder_email.html",
                context={
                    "user": user,
                    "subscription": subscription,
                    "days_remaining": subscription.days_remaining,
                },
            )

        # Send SMS reminder
        message = (
            f"Hi {user.first_name}, your subscription expires in {subscription.days_remaining} days "
            f"({subscription.end_date.strftime('%d %b %Y')}). Renew now to continue accessing exams."
        )
        send_notification_sms(user.phone_number, message)

        logger.info(f"Sent renewal reminder for: {subscription.transaction_id}")

    except Subscription.DoesNotExist:
        logger.error(f"Subscription not found: {subscription_id}")
    except Exception as e:
        logger.error(f"Error sending renewal reminder: {str(e)}")


@shared_task
def send_subscription_expired_notification(subscription_id):
    """
    Send subscription expiration notification.
    """
    try:
        subscription = Subscription.objects.get(id=subscription_id)
        user = subscription.user

        # Send email notification
        if user.email:
            send_notification_email(
                to_email=user.email,
                subject="Subscription Expired",
                template_name="subscriptions/expired_email.html",
                context={"user": user, "subscription": subscription},
            )

        # Send SMS notification
        message = (
            f"Hi {user.first_name}, your subscription has expired. "
            f"Renew now to continue accessing premium features and exams."
        )
        send_notification_sms(user.phone_number, message)

        logger.info(f"Sent expiration notification for: {subscription.transaction_id}")

    except Subscription.DoesNotExist:
        logger.error(f"Subscription not found: {subscription_id}")
    except Exception as e:
        logger.error(f"Error sending expiration notification: {str(e)}")


@shared_task
def cleanup_failed_transactions():
    """
    Clean up old failed payment transactions.
    """
    try:
        # Delete failed transactions older than 30 days
        cutoff_date = timezone.now() - timedelta(days=30)

        failed_transactions = Subscription.objects.filter(
            payment_status="failed", created_at__lt=cutoff_date
        )

        count = failed_transactions.count()
        failed_transactions.delete()

        logger.info(f"Cleaned up {count} failed transactions")
        return f"Cleaned up {count} failed transactions"

    except Exception as e:
        logger.error(f"Error cleaning up failed transactions: {str(e)}")
        raise
