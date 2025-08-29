from functools import wraps
from django.core.cache import cache
from django.http import JsonResponse
from django_ratelimit.decorators import ratelimit
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def cache_response(timeout=300, key_prefix="view"):
    """
    Decorator to cache view responses.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            # Generate cache key
            cache_key = (
                f"{key_prefix}:{request.path}:{hash(frozenset(request.GET.items()))}"
            )

            # Try to get from cache
            cached_response = cache.get(cache_key)
            if cached_response:
                return cached_response

            # Get fresh response
            response = func(request, *args, **kwargs)

            # Cache the response
            if response.status_code == 200:
                cache.set(cache_key, response, timeout)

            return response

        return wrapper

    return decorator


def log_api_call(func):
    """
    Decorator to log API calls.
    """

    @wraps(func)
    def wrapper(request, *args, **kwargs):
        logger.info(f"API Call: {request.method} {request.path} - User: {request.user}")
        try:
            response = func(request, *args, **kwargs)
            logger.info(f"API Response: {response.status_code}")
            return response
        except Exception as e:
            logger.error(f"API Error: {str(e)}")
            raise

    return wrapper


def require_subscription(func):
    """
    Decorator to check if user has active subscription.
    """

    @wraps(func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Allow staff users
        if request.user.is_staff or request.user.role in [
            "admin",
            "moderator",
            "teacher",
        ]:
            return func(request, *args, **kwargs)

        # Check subscription
        from apps.subscriptions.models import Subscription

        if not Subscription.objects.filter(user=request.user, is_active=True).exists():
            return Response(
                {"error": "Active subscription required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return func(request, *args, **kwargs)

    return wrapper
