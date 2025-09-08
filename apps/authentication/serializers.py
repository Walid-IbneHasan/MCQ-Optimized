from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Permission, UserPermission, OTPVerification
from .utils import generate_otp, send_otp_sms
from utils.redis_client import redis_client
from django.utils import timezone
from datetime import timedelta
import re
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample

User = get_user_model()


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Registration Example",
            summary="User registration with all fields",
            description="Example of user registration with complete information",
            value={
                "phone_number": "01712345678",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
            },
            request_only=True,
        ),
    ]
)
class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "password",
            "confirm_password",
        ]

    def validate_phone_number(self, value):
        """Validate phone number format."""
        if not re.match(r"^(\+8801|01)[3-9]\d{8}$", value):
            raise serializers.ValidationError(
                "Invalid Bangladeshi phone number format."
            )
        return value

    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("Passwords don't match.")
        return attrs

    def create(self, validated_data):
        """Create user without sending OTP."""
        validated_data.pop("confirm_password")
        phone_number = validated_data["phone_number"]

        if User.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError(
                "User with this phone number already exists."
            )

        user = User.objects.create_user(**validated_data)
        return user


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "OTP Verification Example",
            summary="Verify OTP for registration",
            value={
                "phone_number": "01712345678",
                "otp_code": "123456",
                "otp_type": "registration",
            },
            request_only=True,
        ),
    ]
)
class OTPVerificationSerializer(serializers.Serializer):
    """
    Serializer for OTP verification.
    """

    phone_number = serializers.CharField()
    otp_code = serializers.CharField(max_length=6, min_length=6)
    otp_type = serializers.ChoiceField(choices=OTPVerification.OTP_TYPES)

    def validate(self, attrs):
        """Validate OTP."""
        phone_number = attrs["phone_number"]
        otp_code = attrs["otp_code"]
        otp_type = attrs["otp_type"]

        try:
            otp_verification = OTPVerification.objects.get(
                phone_number=phone_number, otp_type=otp_type, is_verified=False
            )
        except OTPVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid OTP request.")

        if otp_verification.is_expired():
            raise serializers.ValidationError("OTP has expired.")

        if not otp_verification.can_attempt():
            raise serializers.ValidationError("Maximum OTP attempts exceeded.")

        if otp_verification.otp_code != otp_code:
            otp_verification.attempts += 1
            otp_verification.save()
            raise serializers.ValidationError("Invalid OTP code.")

        # Mark as verified
        otp_verification.is_verified = True
        otp_verification.save()

        # If registration OTP, activate user
        if otp_type == "registration":
            try:
                user = User.objects.get(phone_number=phone_number)
                user.is_active = True
                user.is_verified = True
                user.save()
            except User.DoesNotExist:
                raise serializers.ValidationError("User not found.")

        return attrs


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Login Example",
            summary="User login credentials",
            value={"phone_number": "01712345678", "password": "SecurePass123!"},
            request_only=True,
        ),
    ]
)
class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login.
    """

    phone_number = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Validate login credentials."""
        phone_number = attrs["phone_number"]
        password = attrs["password"]

        # Check if user exists and is active
        try:
            user = User.objects.get(phone_number=phone_number)
            if not user.is_active:
                raise serializers.ValidationError("Account is not activated.")
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials.")

        # Check if account is locked
        if user.account_locked_until and user.account_locked_until > timezone.now():
            raise serializers.ValidationError(
                "Account is temporarily locked. Try again later."
            )

        # Authenticate user
        user = authenticate(phone_number=phone_number, password=password)
        if not user:
            # Increment failed attempts
            try:
                existing_user = User.objects.get(phone_number=phone_number)
                existing_user.failed_login_attempts += 1

                # Lock account after 5 failed attempts
                if existing_user.failed_login_attempts >= 5:
                    existing_user.account_locked_until = timezone.now() + timedelta(
                        minutes=30
                    )

                existing_user.save()
            except User.DoesNotExist:
                pass

            raise serializers.ValidationError("Invalid credentials.")

        # Reset failed attempts on successful login
        user.failed_login_attempts = 0
        user.account_locked_until = None
        user.save()

        attrs["user"] = user
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile.
    """

    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "date_of_birth",
            "profile_picture",
            "bio",
            "role",
            "is_verified",
            "created_at",
        ]
        read_only_fields = ["id", "phone_number", "role", "is_verified", "created_at"]


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing password.
    """

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True, validators=[validate_password]
    )
    confirm_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        """Validate old password."""
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, attrs):
        """Validate password confirmation."""
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("New passwords don't match.")
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    """
    Serializer for password reset request.
    """

    phone_number = serializers.CharField()

    def validate_phone_number(self, value):
        """Validate phone number exists."""
        try:
            user = User.objects.get(phone_number=value, is_active=True)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this phone number not found.")
        return value


# apps/authentication/serializers.py
class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for password reset confirmation.
    """

    phone_number = serializers.CharField()
    otp_code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(
        write_only=True, validators=[validate_password]
    )
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        """Validate OTP and password confirmation."""
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("Passwords don't match.")

        # Validate OTP for password reset
        phone_number = attrs["phone_number"]
        otp_code = attrs["otp_code"]

        try:
            # For password reset, allow already verified OTPs that aren't consumed
            otp_verification = OTPVerification.objects.get(
                phone_number=phone_number,
                otp_type="password_reset",
                otp_code=otp_code,
                is_consumed=False,  # Must not be consumed yet
            )
        except OTPVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid or already used OTP.")

        # Check if OTP has expired
        if otp_verification.is_expired():
            raise serializers.ValidationError("OTP has expired.")

        # Check if OTP is verified
        if not otp_verification.is_verified:
            raise serializers.ValidationError("OTP must be verified first.")

        # Time-based validation: OTP must be verified within last 10 minutes
        from django.utils import timezone
        from datetime import timedelta

        # Check when the OTP was last updated (when it was verified)
        time_since_verification = timezone.now() - otp_verification.updated_at
        if time_since_verification > timedelta(minutes=10):
            raise serializers.ValidationError(
                "OTP verification has expired. Please request a new OTP."
            )

        # Store the OTP verification object for later use
        attrs["otp_verification"] = otp_verification
        return attrs


class PermissionSerializer(serializers.ModelSerializer):
    """
    Serializer for permissions.
    """

    class Meta:
        model = Permission
        fields = "__all__"


class UserPermissionSerializer(serializers.ModelSerializer):
    """
    Serializer for user permissions.
    """

    permission_detail = PermissionSerializer(source="permission", read_only=True)

    class Meta:
        model = UserPermission
        fields = ["id", "permission", "permission_detail", "is_granted", "created_at"]
