from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# API Router
router = DefaultRouter()

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # API Routes
    path("api/auth/", include("apps.authentication.urls")),
    path("api/subscriptions/", include("apps.subscriptions.urls")),
    path("api/subjects/", include("apps.subjects.urls")),
    path("api/questions/", include("apps.questions.urls")),
    path("api/exams/", include("apps.exams.urls")),
    path("api/results/", include("apps.results.urls")),
    path("api/leaderboards/", include("apps.leaderboards.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    # Router URLs
    path("api/", include(router.urls)),
]

# Development settings
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Debug toolbar
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
