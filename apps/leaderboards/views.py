from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from .models import (
    LeaderboardType,
    Leaderboard,
    LeaderboardEntry,
    LeaderboardSubscription,
)
from .serializers import (
    LeaderboardTypeSerializer,
    LeaderboardSerializer,
    LeaderboardDetailSerializer,
    LeaderboardEntrySerializer,
    LeaderboardSubscriptionSerializer,
    UserLeaderboardSummarySerializer,
)
from utils.permissions import IsTeacherOrAbove
from utils.decorators import log_api_call
from utils.redis_client import redis_client
from apps.core.views import BaseViewSet
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class LeaderboardTypeViewSet(BaseViewSet):
    """
    ViewSet for leaderboard types.
    """

    queryset = LeaderboardType.objects.filter(is_active=True)
    serializer_class = LeaderboardTypeSerializer

    def get_permissions(self):
        """Set permissions based on action."""
        if self.action in ["create", "update", "partial_update", "destroy"]:
            self.permission_classes = [IsTeacherOrAbove]
        else:
            self.permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in self.permission_classes]

    def get_queryset(self):
        """Filter leaderboard types based on visibility."""
        queryset = super().get_queryset()

        if not self.request.user.is_teacher_or_above:
            queryset = queryset.filter(is_public=True)

        return queryset

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List available leaderboard types."""
        return super().list(request, *args, **kwargs)


class LeaderboardViewSet(BaseViewSet):
    """
    ViewSet for leaderboards.
    """

    serializer_class = LeaderboardSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get leaderboards with filtering."""
        queryset = Leaderboard.objects.select_related(
            "leaderboard_type", "subject", "chapter", "exam"
        ).prefetch_related("entries__user")

        # Filter by leaderboard type
        leaderboard_type = self.request.query_params.get("type")
        if leaderboard_type:
            queryset = queryset.filter(leaderboard_type_id=leaderboard_type)

        # Filter by scope
        scope = self.request.query_params.get("scope")
        if scope:
            queryset = queryset.filter(leaderboard_type__scope=scope)

        # Filter by period
        period = self.request.query_params.get("period")
        if period:
            queryset = queryset.filter(leaderboard_type__period=period)

        # Filter by subject
        subject_id = self.request.query_params.get("subject")
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)

        # Filter by current period only
        current_only = (
            self.request.query_params.get("current", "false").lower() == "true"
        )
        if current_only:
            now = timezone.now()
            queryset = queryset.filter(period_start__lte=now, period_end__gte=now)

        # Filter by public visibility for non-staff users
        if not self.request.user.is_teacher_or_above:
            queryset = queryset.filter(leaderboard_type__is_public=True)

        return queryset.order_by("-period_end", "-total_participants")

    def get_serializer_class(self):
        """Return detailed serializer for retrieve action."""
        if self.action == "retrieve":
            return LeaderboardDetailSerializer
        return LeaderboardSerializer

    @log_api_call
    def list(self, request, *args, **kwargs):
        """List leaderboards with caching."""
        cache_key = (
            f"leaderboards:{request.user.id}:{hash(frozenset(request.GET.items()))}"
        )
        cached_data = redis_client.get(cache_key)

        if cached_data:
            return Response(
                {"success": True, "leaderboards": cached_data, "cached": True}
            )

        response = super().list(request, *args, **kwargs)

        if response.status_code == 200:
            # Cache for 5 minutes
            redis_client.set(cache_key, response.data.get("results", []), timeout=300)

        return response

    @log_api_call
    def retrieve(self, request, *args, **kwargs):
        """Get detailed leaderboard with user's position."""
        instance = self.get_object()
        serializer = self.get_serializer(instance, context={"request": request})

        return Response({"success": True, "leaderboard": serializer.data})

    @action(detail=False, methods=["get"])
    def global_rankings(self, request):
        """Get global rankings across all subjects."""
        cache_key = f"global_rankings:{request.user.id}"
        cached_data = redis_client.get(cache_key)

        if cached_data:
            return Response({"success": True, "rankings": cached_data, "cached": True})

        # Get current global leaderboards
        global_leaderboards = self.get_queryset().filter(
            leaderboard_type__scope="global"
        )

        rankings = []
        for leaderboard in global_leaderboards:
            serializer = LeaderboardSerializer(leaderboard)
            rankings.append(serializer.data)

        # Cache for 10 minutes
        redis_client.set(cache_key, rankings, timeout=600)

        return Response({"success": True, "rankings": rankings})

    @action(detail=False, methods=["get"])
    def subject_rankings(self, request):
        """Get subject-wise rankings."""
        subject_id = request.query_params.get("subject_id")
        if not subject_id:
            return Response(
                {"success": False, "error": "Subject ID is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subject_leaderboards = self.get_queryset().filter(
            leaderboard_type__scope="subject", subject_id=subject_id
        )

        serializer = LeaderboardSerializer(subject_leaderboards, many=True)

        return Response({"success": True, "subject_rankings": serializer.data})

    @action(detail=False, methods=["get"])
    def my_rankings(self, request):
        """Get current user's rankings across all leaderboards."""
        user = request.user

        # Get all leaderboard entries for the user
        user_entries = (
            LeaderboardEntry.objects.filter(user=user)
            .select_related(
                "leaderboard",
                "leaderboard__leaderboard_type",
                "leaderboard__subject",
                "leaderboard__chapter",
            )
            .order_by("rank")
        )

        # Group by leaderboard type
        rankings_by_type = {}
        for entry in user_entries:
            lb_type = entry.leaderboard.leaderboard_type.name

            if lb_type not in rankings_by_type:
                rankings_by_type[lb_type] = []

            rankings_by_type[lb_type].append(
                {
                    "leaderboard_id": entry.leaderboard.id,
                    "rank": entry.rank,
                    "score": entry.score,
                    "total_participants": entry.leaderboard.total_participants,
                    "subject": (
                        entry.leaderboard.subject.name
                        if entry.leaderboard.subject
                        else None
                    ),
                    "chapter": (
                        entry.leaderboard.chapter.name
                        if entry.leaderboard.chapter
                        else None
                    ),
                    "period": f"{entry.leaderboard.period_start.date()} to {entry.leaderboard.period_end.date()}",
                    "rank_change": entry.rank_change,
                    "performance_trend": entry.performance_trend,
                }
            )

        return Response({"success": True, "my_rankings": rankings_by_type})

    @action(detail=True, methods=["get"])
    def entries(self, request, pk=None):
        """Get all entries for a specific leaderboard."""
        leaderboard = self.get_object()

        # Get paginated entries
        entries = leaderboard.entries.select_related("user").order_by("rank")

        page = self.paginate_queryset(entries)
        if page is not None:
            serializer = LeaderboardEntrySerializer(page, many=True)
            return self.get_paginated_response(
                {"success": True, "entries": serializer.data}
            )

        serializer = LeaderboardEntrySerializer(entries, many=True)
        return Response({"success": True, "entries": serializer.data})


class LeaderboardSubscriptionViewSet(BaseViewSet):
    """
    ViewSet for leaderboard subscriptions.
    """

    serializer_class = LeaderboardSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Get user's leaderboard subscriptions."""
        return LeaderboardSubscription.objects.filter(
            user=self.request.user
        ).select_related("leaderboard_type", "subject", "chapter")

    @action(detail=False, methods=["post"])
    def subscribe(self, request):
        """Subscribe to a leaderboard."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user)
            return Response(
                {
                    "success": True,
                    "message": "Successfully subscribed to leaderboard",
                    "subscription": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"success": False, "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=["post"])
    def unsubscribe(self, request, pk=None):
        """Unsubscribe from a leaderboard."""
        subscription = self.get_object()
        subscription.is_active = False
        subscription.save()

        return Response(
            {"success": True, "message": "Successfully unsubscribed from leaderboard"}
        )


class UserLeaderboardSummaryViewSet(BaseViewSet):
    """
    ViewSet for user's leaderboard summary and dashboard.
    """

    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        """Get comprehensive leaderboard dashboard for user."""
        user = request.user

        # Fix: Use proper date filtering instead of is_current_period
        now = timezone.now()
        current_leaderboards = Leaderboard.objects.filter(
            entries__user=user, period_start__lte=now, period_end__gte=now
        ).distinct()

        dashboard_data = {
            "user": user,
            "leaderboards": current_leaderboards,
        }

        serializer = UserLeaderboardSummarySerializer(dashboard_data)

        return Response({"success": True, "dashboard": serializer.data})

    @action(detail=False, methods=["get"])
    def achievements(self, request):
        """Get user's achievements and badges."""
        user = request.user

        # Get all achievements from leaderboard entries
        entries_with_achievements = (
            LeaderboardEntry.objects.filter(user=user)
            .exclude(achievements=[])
            .order_by("-created_at")
        )

        all_achievements = []
        all_badges = []

        for entry in entries_with_achievements:
            for achievement in entry.achievements:
                all_achievements.append(
                    {
                        "title": achievement.get("title"),
                        "description": achievement.get("description"),
                        "icon": achievement.get("icon"),
                        "earned_at": entry.created_at,
                        "leaderboard": entry.leaderboard.leaderboard_type.name,
                    }
                )

            for badge in entry.badges:
                all_badges.append(
                    {
                        "name": badge.get("name"),
                        "description": badge.get("description"),
                        "color": badge.get("color"),
                        "earned_at": entry.created_at,
                        "leaderboard": entry.leaderboard.leaderboard_type.name,
                    }
                )

        return Response(
            {
                "success": True,
                "achievements": all_achievements,
                "badges": all_badges,
                "total_achievements": len(all_achievements),
                "total_badges": len(all_badges),
            }
        )
