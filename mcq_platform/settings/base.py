import os
from pathlib import Path
from decouple import config
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Security
SECRET_KEY = config(
    "SECRET_KEY",
    default="django-insecure-wauyj-(v8m&a47=k(tj2yb(h(x!r3_mrp(f)y1d^i(6n3rl&(%",
)
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1",
    cast=lambda v: [s.strip() for s in v.split(",")],
)

# Application definition
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_ratelimit",
    "channels",
    "django_cleanup.apps.CleanupConfig",
]

LOCAL_APPS = [
    "apps.core",
    "apps.authentication",
    "apps.subscriptions",
    "apps.subjects",
    "apps.questions",
    "apps.exams",
    "apps.results",
    "apps.leaderboards",
    "apps.notifications",
    "apps.analytics",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

INSTALLED_APPS += [
    "drf_spectacular",
    "drf_spectacular_sidecar",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_ratelimit.middleware.RatelimitMiddleware",
]

ROOT_URLCONF = "mcq_platform.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "mcq_platform.wsgi.application"
ASGI_APPLICATION = "mcq_platform.asgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="mcq_platform"),
        "USER": config("DB_USER", default="mcq_user"),
        "PASSWORD": config("DB_PASSWORD", default="mcq_password"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "OPTIONS": {
            "MAX_CONNS": 20,
        },
    }
}

# Cache Configuration
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [config("REDIS_URL", default="redis://localhost:6379/1")],
        },
    },
}

# Celery Configuration
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/2")
CELERY_RESULT_BACKEND = config(
    "CELERY_RESULT_BACKEND", default="redis://localhost:6379/2"
)
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Dhaka"

# Celery Beat Schedule
CELERY_BEAT_SCHEDULE = {
    "check-expired-subscriptions": {
        "task": "apps.subscriptions.tasks.check_expired_subscriptions",
        "schedule": timedelta(hours=1),
    },
    "send-subscription-reminders": {
        "task": "apps.subscriptions.tasks.send_subscription_reminders",
        "schedule": timedelta(hours=24),
    },
    "cleanup-expired-exam-sessions": {
        "task": "apps.exams.tasks.cleanup_expired_exam_sessions",
        "schedule": timedelta(minutes=30),
    },
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom User Model
AUTH_USER_MODEL = "authentication.User"

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "login": "5/min",
        "register": "3/min",
    },
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
}
REST_FRAMEWORK.update(
    {
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    }
)

# JWT Settings
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": None,
    "AUDIENCE": None,
    "ISSUER": None,
    "JWK_URL": None,
    "LEEWAY": 0,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
}

# CORS Settings
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

# Security Settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "SAMEORIGIN"
SECURE_REFERRER_POLICY = "same-origin"

# Session Settings
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# CSRF Settings
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

# Email Settings
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@mcqplatform.com")

# SMS Settings
SMS_API_URL = "https://api.mimsms.com/api/SmsSending/SMS"
SMS_API_KEY = config("SMS_API_KEY", default="V0VDKBSI84ECAWL")
SMS_USERNAME = config("SMS_USERNAME", default="rajuhosseng@gmail.com")
SMS_SENDER_ID = config("SMS_SENDER_ID", default="8809601010352")

# OTP Settings
OTP_EXPIRY_TIME = 300  # 5 minutes
OTP_REQUEST_COOLDOWN = 60  # 1 minute

# SSL Commerz Settings
SSLCOMMERZ_STORE_ID = config("SSLCOMMERZ_STORE_ID", default="")
SSLCOMMERZ_STORE_PASSWORD = config("SSLCOMMERZ_STORE_PASSWORD", default="")
SSLCOMMERZ_IS_SANDBOX = config("SSLCOMMERZ_IS_SANDBOX", default=True, cast=bool)

# Redis Keys
REDIS_KEY_PATTERNS = {
    "exam_session": "exam_session:{user_id}:{exam_id}",
    "exam_answers": "exam_answers:{session_id}",
    "exam_timer": "exam_timer:{session_id}",
    "user_active_exams": "user_active_exams:{user_id}",
    "leaderboard_cache": "leaderboard:{type}:{id}",
    "question_cache": "questions:{exam_id}",
}

# File Upload Settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_PERMISSIONS = 0o644


SPECTACULAR_SETTINGS = {
    "TITLE": "MCQ Platform API",
    "DESCRIPTION": """
    ## MCQ Platform API Documentation
    
    A comprehensive educational MCQ platform with real-time exam sessions, performance analytics, 
    leaderboards, and subscription management.
    
    ### Key Features:
    - **Authentication**: JWT-based authentication with OTP verification
    - **Real-time Exams**: WebSocket-powered exam sessions with anti-cheat measures
    - **Performance Analytics**: Comprehensive user and system analytics
    - **Leaderboards**: Multi-level ranking system with achievements
    - **Subscriptions**: Payment integration with SSLCommerz
    - **Notifications**: Multi-channel notification system
    
    ### Base URL
    - **Development**: `http://localhost:8000`
    - **Production**: `https://your-domain.com`
    
    ### Authentication
    Most endpoints require authentication. Include the JWT token in the Authorization header:
    ```
    Authorization: Bearer <your-jwt-token>
    ```
    
    ### Rate Limiting
    - Anonymous users: 100 requests/hour
    - Authenticated users: 1000 requests/hour
    - Login attempts: 5 requests/minute
    
    ### Response Format
    All API responses follow this structure:
    ```json
    {
        "success": true,
        "data": {...},
        "message": "Success message",
        "errors": {...}
    }
    ```
    
    ### Error Codes
    - `400`: Bad Request - Invalid input data
    - `401`: Unauthorized - Authentication required
    - `403`: Forbidden - Insufficient permissions
    - `404`: Not Found - Resource not found
    - `429`: Too Many Requests - Rate limit exceeded
    - `500`: Internal Server Error - Server error
    
    ### Pagination
    List endpoints support pagination:
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 20, max: 100)
    
    ### Filtering & Search
    Many list endpoints support filtering and search:
    - `search`: Search query
    - `ordering`: Field to order by (prefix with `-` for descending)
    - Additional filters specific to each endpoint
    
    ### WebSocket Endpoints
    Real-time features use WebSocket connections:
    - Exam Timer: `ws://localhost:8000/ws/exam-timer/<session_id>/`
    - Exam Updates: `ws://localhost:8000/ws/exam/<session_id>/`
    
    ### Support
    For API support, contact: support@mcqplatform.com
    """,
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {
        "name": "MCQ Platform API Support",
        "email": "support@mcqplatform.com",
    },
    "LICENSE": {
        "name": "Proprietary License",
    },
    # UI configuration
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 2,
        "displayRequestDuration": True,
        "docExpansion": "none",
        "filter": True,
        "operationsSorter": "alpha",
        "showExtensions": True,
        "tagsSorter": "alpha",
        "tryItOutEnabled": True,
    },
    "REDOC_UI_SETTINGS": {
        "hideDownloadButton": False,
        "hideHostname": False,
        "hideLoading": False,
        "hideSchemaPattern": True,
        "hideRequestPayloadSample": False,
        "hideResponsePayloadSample": False,
        "noAutoAuth": False,
        "pathInMiddlePanel": False,
        "requiredPropsFirst": True,
        "scrollYOffset": 0,
        "showObjectSchemaExamples": True,
        "suppressWarnings": False,
        "theme": {"colors": {"primary": {"main": "#667eea"}}},
    },
    # Schema generation settings
    "COMPONENT_SPLIT_REQUEST": True,
    "COMPONENT_NO_READ_ONLY_REQUIRED": True,
    "SCHEMA_PATH_PREFIX": r"/api/",
    "SCHEMA_PATH_PREFIX_TRIM": True,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SWAGGER_UI_FAVICON_HREF": "/static/favicon.ico",
    "REDOC_FAVICON_HREF": "/static/favicon.ico",
    # Authentication schemes
    "AUTHENTICATION_WHITELIST": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # Custom schema extensions
    "EXTENSIONS_INFO": {
        "x-logo": {"url": "/static/logo.png", "altText": "MCQ Platform Logo"}
    },
    # Tags for organizing endpoints
    "TAGS": [
        {
            "name": "Authentication",
            "description": "User authentication and authorization",
        },
        {"name": "Users", "description": "User management and profiles"},
        {"name": "Subscriptions", "description": "Subscription plans and payments"},
        {"name": "Subjects", "description": "Academic subjects and chapters"},
        {"name": "Questions", "description": "MCQ questions and question banks"},
        {"name": "Exams", "description": "Exam creation and management"},
        {"name": "Exam Sessions", "description": "Real-time exam sessions"},
        {"name": "Results", "description": "Exam results and performance analytics"},
        {"name": "Leaderboards", "description": "Rankings and achievements"},
        {"name": "Notifications", "description": "Notification management"},
        {"name": "Analytics", "description": "System analytics and reporting"},
    ],
    # Custom preprocessing
    "PREPROCESSING_HOOKS": [
        "apps.core.schema.custom_preprocessing_hook",
    ],
    # Custom postprocessing
    "POSTPROCESSING_HOOKS": [
        "apps.core.schema.custom_postprocessing_hook",
    ],
}
