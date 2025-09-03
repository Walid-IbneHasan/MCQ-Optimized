from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from .models import OTPVerification, LoginAttempt
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task
def cleanup_expired_otps():
    """
    Remove expired OTP records.
    """
    try:
        expired_otps = OTPVerification.objects.filter(
            expires_at__lt=timezone.now(),
            created_at__lt=timezone.now() - timedelta(hours=24),
        )
        count = expired_otps.count()
        expired_otps.delete()

        logger.info(f"Cleaned up {count} expired OTP records")
        return f"Cleaned up {count} expired OTP records"
    except Exception as e:
        logger.error(f"Error cleaning up expired OTPs: {str(e)}")
        raise


@shared_task
def cleanup_old_login_attempts():
    """
    Remove old login attempt records.
    """
    try:
        old_attempts = LoginAttempt.objects.filter(
            created_at__lt=timezone.now() - timedelta(days=30)
        )
        count = old_attempts.count()
        old_attempts.delete()

        logger.info(f"Cleaned up {count} old login attempt records")
        return f"Cleaned up {count} old login attempt records"
    except Exception as e:
        logger.error(f"Error cleaning up old login attempts: {str(e)}")
        raise


@shared_task
def unlock_locked_accounts():
    """
    Unlock accounts that have passed their lock time.
    """
    try:
        locked_users = User.objects.filter(account_locked_until__lt=timezone.now())
        count = locked_users.count()

        locked_users.update(account_locked_until=None, failed_login_attempts=0)

        logger.info(f"Unlocked {count} user accounts")
        return f"Unlocked {count} user accounts"
    except Exception as e:
        logger.error(f"Error unlocking accounts: {str(e)}")
        raise
