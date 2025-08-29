from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from apps.core.models import TimeStampedModel, UUIDModel
from apps.core.managers import SoftDeleteManager
from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel, UUIDModel):
    """
    Custom User model with phone number as username.
    """

    ROLE_CHOICES = [
        ("student", "Student"),
        ("teacher", "Teacher"),
        ("moderator", "Moderator"),
        ("admin", "Admin"),
    ]

    phone_number = models.CharField(max_length=15, unique=True)
    email = models.EmailField(blank=True, null=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    # Profile fields
    date_of_birth = models.DateField(blank=True, null=True)
    profile_picture = models.ImageField(
        upload_to="profile_pics/", blank=True, null=True
    )
    bio = models.TextField(blank=True)

    # Role and status
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="student")
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)

    # Authentication fields
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    account_locked_until = models.DateTimeField(blank=True, null=True)

    # Social login fields
    google_id = models.CharField(max_length=100, blank=True, null=True)
    facebook_id = models.CharField(max_length=100, blank=True, null=True)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["phone_number"]),
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.phone_number

    @property
    def is_teacher_or_above(self):
        """Check if user is teacher, moderator, or admin."""
        return self.role in ["teacher", "moderator", "admin"] or self.is_superuser

    @property
    def is_moderator_or_above(self):
        """Check if user is moderator or admin."""
        return self.role in ["moderator", "admin"] or self.is_superuser

    def has_permission(self, permission_name):
        """Check if user has specific permission."""
        if self.is_superuser:
            return True

        return UserPermission.objects.filter(
            user=self, permission__name=permission_name, is_granted=True
        ).exists()


class Permission(TimeStampedModel, UUIDModel):
    """
    Custom permission model.
    """

    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = "permissions"
        ordering = ["category", "display_name"]

    def __str__(self):
        return self.display_name


class UserPermission(TimeStampedModel, UUIDModel):
    """
    User-specific permissions.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_permissions_custom"
    )
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    is_granted = models.BooleanField(default=True)
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="granted_permissions"
    )

    class Meta:
        db_table = "user_permissions"
        unique_together = ["user", "permission"]

    def __str__(self):
        status = "Granted" if self.is_granted else "Denied"
        return f"{self.user.phone_number} - {self.permission.name} ({status})"


class OTPVerification(TimeStampedModel, UUIDModel):
    """
    OTP verification model for phone numbers.
    """

    OTP_TYPES = [
        ("registration", "Registration"),
        ("login", "Login"),
        ("password_reset", "Password Reset"),
        ("phone_verification", "Phone Verification"),
    ]

    phone_number = models.CharField(max_length=15)
    otp_code = models.CharField(max_length=6)
    otp_type = models.CharField(max_length=20, choices=OTP_TYPES)
    is_verified = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)

    class Meta:
        db_table = "otp_verifications"
        indexes = [
            models.Index(fields=["phone_number", "otp_type"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.otp_type}"

    def is_expired(self):
        """Check if OTP is expired."""
        from django.utils import timezone

        return timezone.now() > self.expires_at

    def can_attempt(self):
        """Check if more attempts are allowed."""
        return self.attempts < self.max_attempts


class LoginAttempt(TimeStampedModel, UUIDModel):
    """
    Track login attempts for security.
    """

    phone_number = models.CharField(max_length=15)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    is_successful = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "login_attempts"
        indexes = [
            models.Index(fields=["phone_number", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
        ]

    def __str__(self):
        status = "Success" if self.is_successful else "Failed"
        return f"{self.phone_number} - {status}"
