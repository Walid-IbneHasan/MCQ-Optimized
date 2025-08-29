from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from utils.sms_api import send_sms
import logging

logger = logging.getLogger(__name__)


def send_notification_email(to_email, subject, template_name, context=None):
    """
    Send notification email using template.
    """
    if context is None:
        context = {}

    try:
        html_message = render_to_string(template_name, context)
        send_mail(
            subject=subject,
            message="",  # Plain text version
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email sending failed: {str(e)}")
        return False


def send_notification_sms(phone_number, message):
    """
    Send notification SMS.
    """
    try:
        result = send_sms(phone_number, message)
        return result["success"]
    except Exception as e:
        logger.error(f"SMS sending failed: {str(e)}")
        return False


def generate_transaction_id():
    """
    Generate unique transaction ID.
    """
    import time
    import random

    timestamp = str(int(time.time()))
    random_num = str(random.randint(1000, 9999))
    return f"TXN{timestamp}{random_num}"
