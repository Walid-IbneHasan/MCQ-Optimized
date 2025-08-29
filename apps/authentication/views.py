from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from .serializers import (
    UserRegistrationSerializer,
    OTPVerificationSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    ChangePasswordSerializer,
    PasswordResetSerializer,
    PasswordResetConfirmSerializer,
    PermissionSerializer,
    UserPermissionSerializer,
)
from .models import OTPVerification, Permission, UserPermission
from .utils import (
    generate_otp,
    send_otp_sms,
    get_client_ip,
    create_login_attempt,
    check_rate_limit,
    clear_rate_limit,
)
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample,
    OpenApiResponse,
    inline_serializer,
)
from utils.decorators import log_api_call
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@extend_schema_view(
    post=extend_schema(
        summary="Register new user",
        description="""
        Register a new user account with phone number verification.
        
        **Process:**
        1. Submit registration details
        2. Receive OTP via SMS
        3. Verify OTP to activate account
        4. Get JWT tokens upon successful verification
        
        **Phone Number Format:**
        - Must be valid Bangladeshi number
        - Format: +8801XXXXXXXXX or 01XXXXXXXXX
        
        **Password Requirements:**
        - Minimum 8 characters
        - Must contain letters and numbers
        - Special characters recommended
        """,
        request=UserRegistrationSerializer,
        responses={
            201: OpenApiResponse(
                response=inline_serializer(
                    name="RegistrationResponse",
                    fields={
                        "success": serializers.BooleanField(default=True),
                        "message": serializers.CharField(
                            default="Registration successful. OTP sent to your phone."
                        ),
                        "phone_number": serializers.CharField(),
                    },
                ),
                description="Registration successful, OTP sent",
                examples=[
                    OpenApiExample(
                        "Success Response",
                        value={
                            "success": True,
                            "message": "Registration successful. OTP sent to your phone.",
                            "phone_number": "01712345678",
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Registration failed - validation errors",
                examples=[
                    OpenApiExample(
                        "Validation Error",
                        value={
                            "success": False,
                            "errors": {
                                "phone_number": [
                                    "User with this phone number already exists."
                                ],
                                "password": ["This password is too common."],
                            },
                        },
                    )
                ],
            ),
        },
        tags=["Authentication"],
    )
)
class UserRegistrationView(APIView):
    """
    User registration endpoint.
    """

    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="3/m", method="POST"))
    @log_api_call
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Registration successful. OTP sent to your phone.",
                    "phone_number": user.phone_number,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema_view(
    post=extend_schema(
        summary="Verify OTP",
        description="""
        Verify OTP code sent via SMS during registration or password reset.
        
        **OTP Types:**
        - `registration`: Verify new account registration
        - `login`: Verify login attempt
        - `password_reset`: Verify password reset request
        
        **OTP Validity:**
        - Valid for 5 minutes after generation
        - Maximum 5 attempts allowed
        - Case-sensitive 6-digit code
        """,
        request=OTPVerificationSerializer,
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="OTPVerificationResponse",
                    fields={
                        "success": serializers.BooleanField(default=True),
                        "message": serializers.CharField(),
                        "access_token": serializers.CharField(required=False),
                        "refresh_token": serializers.CharField(required=False),
                        "user": UserProfileSerializer(required=False),
                    },
                ),
                description="OTP verified successfully",
                examples=[
                    OpenApiExample(
                        "Registration OTP Success",
                        value={
                            "success": True,
                            "message": "OTP verified successfully.",
                            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                            "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                            "user": {
                                "id": "uuid-here",
                                "phone_number": "01712345678",
                                "full_name": "John Doe",
                            },
                        },
                    )
                ],
            )
        },
        tags=["Authentication"],
    )
)
class OTPVerificationView(APIView):
    """
    OTP verification endpoint.
    """

    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="10/m", method="POST"))
    @log_api_call
    def post(self, request):
        serializer = OTPVerificationSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data["phone_number"]
            otp_type = serializer.validated_data["otp_type"]

            # Clear rate limits on successful verification
            clear_rate_limit(phone_number, "otp")

            response_data = {"success": True, "message": "OTP verified successfully."}

            # If registration verification, generate tokens
            if otp_type == "registration":
                try:
                    user = User.objects.get(phone_number=phone_number)
                    refresh = RefreshToken.for_user(user)
                    response_data.update(
                        {
                            "access_token": str(refresh.access_token),
                            "refresh_token": str(refresh),
                            "user": UserProfileSerializer(user).data,
                        }
                    )
                except User.DoesNotExist:
                    pass

            return Response(response_data, status=status.HTTP_200_OK)

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class ResendOTPView(APIView):
    """
    Resend OTP endpoint.
    """

    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="2/m", method="POST"))
    @log_api_call
    def post(self, request):
        phone_number = request.data.get("phone_number")
        otp_type = request.data.get("otp_type", "registration")

        if not phone_number:
            return Response(
                {"success": False, "error": "Phone number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check rate limit
        if not check_rate_limit(phone_number, "otp", max_attempts=3, window_minutes=5):
            return Response(
                {"success": False, "error": "Too many OTP requests. Please wait."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # Generate new OTP
        otp_code = generate_otp()

        # Create OTP verification record
        OTPVerification.objects.create(
            phone_number=phone_number,
            otp_code=otp_code,
            otp_type=otp_type,
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        # Send OTP
        if send_otp_sms(phone_number, otp_code, otp_type):
            return Response(
                {"success": True, "message": "OTP sent successfully."},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"success": False, "error": "Failed to send OTP."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom login view with additional security features.
    """

    @method_decorator(ratelimit(key="ip", rate="5/m", method="POST"))
    @log_api_call
    def post(self, request, *args, **kwargs):
        phone_number = request.data.get("phone_number", "")
        ip_address = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        # Check rate limit
        if not check_rate_limit(
            phone_number, "login", max_attempts=5, window_minutes=15
        ):
            create_login_attempt(
                phone_number, ip_address, user_agent, False, "Rate limited"
            )
            return Response(
                {"success": False, "error": "Too many login attempts. Please wait."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]

            # Create tokens
            refresh = RefreshToken.for_user(user)

            # Update last login info
            user.last_login = timezone.now()
            user.last_login_ip = ip_address
            user.save(update_fields=["last_login", "last_login_ip"])

            # Log successful login
            create_login_attempt(phone_number, ip_address, user_agent, True)
            clear_rate_limit(phone_number, "login")

            return Response(
                {
                    "success": True,
                    "access_token": str(refresh.access_token),
                    "refresh_token": str(refresh),
                    "user": UserProfileSerializer(user).data,
                },
                status=status.HTTP_200_OK,
            )

        # Log failed login
        create_login_attempt(
            phone_number, ip_address, user_agent, False, "Invalid credentials"
        )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class UserProfileView(RetrieveUpdateAPIView):
    """
    User profile view.
    """

    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    @log_api_call
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @log_api_call
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @log_api_call
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)


class ChangePasswordView(APIView):
    """
    Change password endpoint.
    """

    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="3/h", method="POST"))
    @log_api_call
    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        if serializer.is_valid():
            user = request.user
            user.set_password(serializer.validated_data["new_password"])
            user.save()

            logger.info(f"Password changed for user: {user.phone_number}")

            return Response(
                {"success": True, "message": "Password changed successfully."},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class PasswordResetView(APIView):
    """
    Password reset request endpoint.
    """

    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="3/h", method="POST"))
    @log_api_call
    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data["phone_number"]

            # Generate OTP
            otp_code = generate_otp()

            # Create OTP verification record
            OTPVerification.objects.create(
                phone_number=phone_number,
                otp_code=otp_code,
                otp_type="password_reset",
                expires_at=timezone.now() + timedelta(minutes=5),
            )

            # Send OTP
            try:
                if send_otp_sms(phone_number, otp_code, "password_reset"):
                    return Response({"success": True})
            except User.DoesNotExist:
                return Response(
                    {"success": False, "error": "User not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class PasswordResetConfirmView(APIView):
    """
    Password reset confirmation endpoint.
    """

    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="5/h", method="POST"))
    @log_api_call
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data["phone_number"]
            new_password = serializer.validated_data["new_password"]

            try:
                user = User.objects.get(phone_number=phone_number, is_active=True)
                user.set_password(new_password)
                user.failed_login_attempts = 0
                user.account_locked_until = None
                user.save()

                logger.info(f"Password reset successful for user: {phone_number}")

                return Response(
                    {"success": True, "message": "Password reset successful."},
                    status=status.HTTP_200_OK,
                )
            except User.DoesNotExist:
                return Response


class LogoutView(APIView):
    """
    Logout endpoint that blacklists the refresh token.
    """

    permission_classes = [permissions.IsAuthenticated]

    @log_api_call
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh_token")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            logger.info(f"User logged out: {request.user.phone_number}")

            return Response(
                {"success": True, "message": "Logged out successfully."},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"success": False, "error": "Invalid token."},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserPermissionsView(APIView):
    """
    View user permissions.
    """

    permission_classes = [permissions.IsAuthenticated]

    @log_api_call
    def get(self, request):
        permissions = UserPermission.objects.filter(
            user=request.user, is_granted=True
        ).select_related("permission")

        serializer = UserPermissionSerializer(permissions, many=True)
        return Response(
            {"success": True, "permissions": serializer.data}, status=status.HTTP_200_OK
        )
