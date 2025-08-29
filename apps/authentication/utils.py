import random
import string
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from utils.sms_api import send_sms
from utils.redis_client import redis_client
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

def generate_otp(length=6):
    """Generate random OTP."""
    return ''.join(random.choices(string.digits, k=length))

def send_otp_sms(phone_number, otp_code, otp_type):
    """Send OTP via SMS."""
    messages = {
        'registration': f'Your registration OTP is {otp_code}. It will expire in 5 minutes. Do not share this OTP.',
        'login': f'Your login OTP is {otp_code}. It will expire in 5 minutes. Do not share this OTP.',
        'password_reset': f'Your password reset OTP is {otp_code}. It will expire in 5 minutes. Do not share this OTP.',
    }
    
    message = messages.get(otp_type, f'Your OTP is {otp_code}. Do not share this OTP.')
    
    try:
        result = send_sms(phone_number, message)
        logger.info(f"OTP sent to {phone_number} for {otp_type}")
        return result['success']
    except Exception as e:
        logger.error(f"Failed to send OTP to {phone_number}: {str(e)}")
        return False

def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def create_login_attempt(phone_number, ip_address, user_agent, is_successful, failure_reason=''):
    """Create login attempt record."""
    from .models import LoginAttempt
    
    LoginAttempt.objects.create(
        phone_number=phone_number,
        ip_address=ip_address,
        user_agent=user_agent,
        is_successful=is_successful,
        failure_reason=failure_reason
    )

def check_rate_limit(phone_number, limit_type='login', max_attempts=5, window_minutes=15):
    """Check if phone number is rate limited."""
    cache_key = f"rate_limit:{limit_type}:{phone_number}"
    attempts = redis_client.get(cache_key) or 0
    
    if attempts >= max_attempts:
        return False
    
    # Increment attempts
    redis_client.set(cache_key, attempts + 1, timeout=window_minutes * 60)
    return True

def clear_rate_limit(phone_number, limit_type='login'):
    """Clear rate limit for phone number."""
    cache_key = f"rate_limit:{limit_type}:{phone_number}"
    redis_client.delete(cache_key)
    def full_name(self):
        """Return full name."""
        return f"{self.first_name} {self.last_name}".strip() or self.phone_number
    
    @property
    def is_admin(self):
        """Check if user is admin."""
        return self.role == 'admin' or self.is_superuser
    
   