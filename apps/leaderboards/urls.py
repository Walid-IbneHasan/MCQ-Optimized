# apps/leaderboards/urls.py - Enhanced URLs
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LeaderboardTypeViewSet,
    LeaderboardViewSet,
    LeaderboardSubscriptionViewSet,
    UserLeaderboardSummaryViewSet,
)
from .api import (
    get_exam_leaderboards,
    get_leaderboard_detail,
    get_user_leaderboard_summary,
    get_available_periods,
)

router = DefaultRouter()
router.register(r"types", LeaderboardTypeViewSet, basename="leaderboard-types")
router.register(r"leaderboards", LeaderboardViewSet, basename="leaderboards")
router.register(
    r"subscriptions",
    LeaderboardSubscriptionViewSet,
    basename="leaderboard-subscriptions",
)
router.register(
    r"summary", UserLeaderboardSummaryViewSet, basename="leaderboard-summary"
)


app_name = "leaderboards"


urlpatterns = [
    
    # Enhanced API endpoints
    path("exam-leaderboards/", get_exam_leaderboards, name="exam-leaderboards"),
    path(
        "leaderboards/<uuid:leaderboard_id>/detail/",
        get_leaderboard_detail,
        name="leaderboard-detail",
    ),
    path("my-summary/", get_user_leaderboard_summary, name="user-leaderboard-summary"),
    path("available-periods/", get_available_periods, name="available-periods"),
    # Router URLs
    path("", include(router.urls)),
]
