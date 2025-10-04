from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    UserRegistrationView,
    OTPVerificationView,
    ResendOTPView,
    CustomTokenObtainPairView,
    UserProfileView,
    ChangePasswordView,
    PasswordResetView,
    PasswordResetConfirmView,
    LogoutView,
    UserPermissionsView,
    UserManagementView,
    UserDetailManagementView,
)

urlpatterns = [
    # Authentication
    path("register/", UserRegistrationView.as_view(), name="user-register"),
    path("verify-otp/", OTPVerificationView.as_view(), name="verify-otp"),
    path("resend-otp/", ResendOTPView.as_view(), name="resend-otp"),
    path("login/", CustomTokenObtainPairView.as_view(), name="token-obtain-pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # Profile management
    path("profile/", UserProfileView.as_view(), name="user-profile"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("password-reset/", PasswordResetView.as_view(), name="password-reset"),
    path(
        "password-reset-confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    
    # Permissions
    path("permissions/", UserPermissionsView.as_view(), name="user-permissions"),
    
    # User Management (Admin only)
    path('users/', UserManagementView.as_view(), name='user-management'),
    path('users/<uuid:user_id>/', UserDetailManagementView.as_view(), name='user-detail-management'),
]
