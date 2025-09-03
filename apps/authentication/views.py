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
            500: OpenApiResponse(
                description="Internal server error - SMS sending failed",
                examples=[
                    OpenApiExample(
                        "SMS Error",
                        value={
                            "success": False,
                            "error": "Failed to send OTP: 400 Bad Request",
                        },
                    )
                ],
            ),
        },
        tags=["Authentication"],
    )
)
class UserRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="3/m", method="POST"))
    def post(self, request):
        logger.info(f"User registration attempt: {request.data}")
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            try:
                otp_code = generate_otp()
                OTPVerification.objects.filter(
                    phone_number=user.phone_number, otp_type="registration", is_verified=False
                ).delete()
                OTPVerification.objects.create(
                    phone_number=user.phone_number,
                    otp_code=otp_code,
                    otp_type="registration",
                    expires_at=timezone.now() + timedelta(minutes=5),
                )
                send_otp_sms(user.phone_number, otp_code, "registration")
                logger.info(f"Registration OTP created for {user.phone_number}: {otp_code}")
                return Response(
                    {
                        "success": True,
                        "message": "Registration successful. OTP sent to your phone.",
                        "phone_number": user.phone_number,
                    },
                    status=status.HTTP_201_CREATED,
                )
            except Exception as e:
                logger.error(f"Failed to send OTP during registration for {user.phone_number}: {str(e)}")
                user.delete()
                return Response(
                    {"success": False, "error": f"Failed to send OTP: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

class OTPVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="10/m", method="POST"))
    def post(self, request):
        logger.info(f"OTP verification attempt: {request.data}")
        serializer = OTPVerificationSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data["phone_number"]
            otp_type = serializer.validated_data["otp_type"]

            clear_rate_limit(phone_number, "otp")

            response_data = {"success": True, "message": "OTP verified successfully."}

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
    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="2/m", method="POST"))
    def post(self, request):
        logger.info(f"Resend OTP attempt: {request.data}")
        phone_number = request.data.get("phone_number")
        otp_type = request.data.get("otp_type", "registration")

        if not phone_number:
            return Response(
                {"success": False, "error": "Phone number is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not check_rate_limit(phone_number, "otp", max_attempts=3, window_minutes=5):
            return Response(
                {"success": False, "error": "Too many OTP requests. Please wait."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        try:
            otp_code = generate_otp()
            OTPVerification.objects.filter(
                phone_number=phone_number, otp_type=otp_type, is_verified=False
            ).delete()
            OTPVerification.objects.create(
                phone_number=phone_number,
                otp_code=otp_code,
                otp_type=otp_type,
                expires_at=timezone.now() + timedelta(minutes=5),
            )
            send_otp_sms(phone_number, otp_code, otp_type)
            logger.info(f"Resend OTP created for {phone_number}: {otp_code}")
            return Response(
                {"success": True, "message": "OTP sent successfully."},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"Failed to resend OTP to {phone_number}: {str(e)}")
            return Response(
                {"success": False, "error": f"Failed to send OTP: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class CustomTokenObtainPairView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @method_decorator(ratelimit(key="ip", rate="5/m", method="POST"))
    def post(self, request, *args, **kwargs):
        logger.info(f"Custom login attempt: {request.data}")
        phone_number = request.data.get("phone_number", "")
        ip_address = get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        logger.info(f"Login attempt for phone: {phone_number} from IP: {ip_address}")

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

            refresh = RefreshToken.for_user(user)

            user.last_login = timezone.now()
            user.last_login_ip = ip_address
            user.save(update_fields=["last_login", "last_login_ip"])

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

        create_login_attempt(
            phone_number, ip_address, user_agent, False, "Invalid credentials"
        )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

class UserProfileView(RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get(self, request, *args, **kwargs):
        logger.info(f"User profile GET: {request.user}")
        return super().get(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        logger.info(f"User profile PUT: {request.user}, data: {request.data}")
        return super().put(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        logger.info(f"User profile PATCH: {request.user}, data: {request.data}")
        return super().patch(request, *args, **kwargs)

class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="3/h", method="POST"))
    def post(self, request):
        logger.info(f"Change password attempt: {request.user}")
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
    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="3/h", method="POST"))
    def post(self, request):
        logger.info(f"Password reset request: {request.data}")
        serializer = PasswordResetSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data["phone_number"]
            try:
                otp_code = generate_otp()
                OTPVerification.objects.filter(
                    phone_number=phone_number, otp_type="password_reset", is_verified=False
                ).delete()
                OTPVerification.objects.create(
                    phone_number=phone_number,
                    otp_code=otp_code,
                    otp_type="password_reset",
                    expires_at=timezone.now() + timedelta(minutes=5),
                )
                send_otp_sms(phone_number, otp_code, "password_reset")
                logger.info(f"Password reset OTP created for {phone_number}: {otp_code}")
                return Response(
                    {"success": True, "message": "OTP sent for password reset."},
                    status=status.HTTP_200_OK,
                )
            except Exception as e:
                logger.error(f"Failed to send OTP for password reset to {phone_number}: {str(e)}")
                return Response(
                    {"success": False, "error": f"Failed to send OTP: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="5/h", method="POST"))
    def post(self, request):
        logger.info(f"Password reset confirm: {request.data}")
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
                return Response(
                    {"success": False, "error": "User not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @method_decorator(ratelimit(key="user", rate="10/h", method="POST"))
    def post(self, request):
        logger.info(f"Logout attempt: {request.user}")
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
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        logger.info(f"User permissions view: {request.user}")
        permissions = UserPermission.objects.filter(
            user=request.user, is_granted=True
        ).select_related("permission")

        serializer = UserPermissionSerializer(permissions, many=True)
        return Response(
            {"success": True, "permissions": serializer.data}, status=status.HTTP_200_OK
        )
