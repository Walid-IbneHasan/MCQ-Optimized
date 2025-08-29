from rest_framework import permissions
from django.contrib.auth import get_user_model
from apps.subscriptions.models import Subscription

User = get_user_model()


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user


class IsAdminOrModerator(permissions.BasePermission):
    """
    Custom permission for admin and moderator access.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser or request.user.role in ["admin", "moderator"]
        )


class IsTeacherOrAbove(permissions.BasePermission):
    """
    Custom permission for teacher, moderator, and admin access.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser
            or request.user.role in ["admin", "moderator", "teacher"]
        )


class HasActiveSubscription(permissions.BasePermission):
    """
    Custom permission to check if user has active subscription.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # Allow staff users
        if request.user.is_staff or request.user.role in [
            "admin",
            "moderator",
            "teacher",
        ]:
            return True

        # Check for active subscription
        return Subscription.objects.filter(user=request.user, is_active=True).exists()


class CanCreateExam(permissions.BasePermission):
    """
    Custom permission for exam creation.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser
            or request.user.role in ["admin", "moderator", "teacher"]
        )


class CanManageQuestions(permissions.BasePermission):
    """
    Custom permission for question management.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_superuser
            or request.user.role in ["admin", "moderator", "teacher"]
        )
