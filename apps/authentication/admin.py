from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth import get_user_model
from .models import Permission, UserPermission, OTPVerification, LoginAttempt

User = get_user_model()


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom User admin.
    """

    list_display = [
        "phone_number",
        "email",
        "first_name",
        "last_name",
        "role",
        "is_active",
        "is_verified",
        "created_at",
    ]
    list_filter = ["role", "is_active", "is_verified", "created_at"]
    search_fields = ["phone_number", "email", "first_name", "last_name"]
    ordering = ["-created_at"]

    fieldsets = (
        (None, {"fields": ("phone_number", "password")}),
        (
            "Personal Info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "date_of_birth",
                    "profile_picture",
                    "bio",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_verified",
                )
            },
        ),
        (
            "Security",
            {
                "fields": (
                    "last_login_ip",
                    "failed_login_attempts",
                    "account_locked_until",
                )
            },
        ),
        ("Social", {"fields": ("google_id", "facebook_id")}),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone_number", "password1", "password2", "role"),
            },
        ),
    )

    readonly_fields = ["created_at", "updated_at"]


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """
    Permission admin.
    """

    list_display = ["name", "display_name", "category", "created_at"]
    list_filter = ["category", "created_at"]
    search_fields = ["name", "display_name", "description"]
    ordering = ["category", "display_name"]


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    """
    User Permission admin.
    """

    list_display = ["user", "permission", "is_granted", "granted_by", "created_at"]
    list_filter = ["is_granted", "created_at"]
    search_fields = ["user__phone_number", "permission__name"]
    raw_id_fields = ["user", "permission", "granted_by"]


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = [
        "phone_number",
        "otp_type",
        "is_verified",
        "is_consumed",
        "expires_at",
        "created_at",
    ]
    list_filter = ["otp_type", "is_verified", "is_consumed", "created_at"]
    search_fields = ["phone_number"]
    readonly_fields = ["consumed_at"]


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    """
    Login Attempt admin.
    """

    list_display = [
        "phone_number",
        "ip_address",
        "is_successful",
        "failure_reason",
        "created_at",
    ]
    list_filter = ["is_successful", "created_at"]
    search_fields = ["phone_number", "ip_address"]
    readonly_fields = ["user_agent"]
