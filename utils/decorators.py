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
    Decorator to log API calls - temporarily disabled to avoid issues.
    """
    # Temporarily return the original function without decoration
    return func


def require_subscription(func):
    """
    Decorator to check if user has active subscription.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Handle both function-based views and class-based views
        if len(args) > 0 and hasattr(args[0], "__class__"):
            # Class-based view: first arg is self, second is request
            if len(args) > 1:
                request = args[1]
            else:
                request = kwargs.get("request")
        else:
            # Function-based view: first arg is request
            request = args[0] if args else kwargs.get("request")

        if not request or not hasattr(request, "user"):
            return Response(
                {"error": "Authentication required"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

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
            return func(*args, **kwargs)

        # Check subscription
        from apps.subscriptions.models import Subscription

        if not Subscription.objects.filter(user=request.user, is_active=True).exists():
            return Response(
                {"error": "Active subscription required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        return func(*args, **kwargs)

    return wrapper
