from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LeaderboardTypeViewSet,
    LeaderboardViewSet,
    LeaderboardSubscriptionViewSet,
    UserLeaderboardSummaryViewSet,
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

urlpatterns = [
    path("", include(router.urls)),
]
