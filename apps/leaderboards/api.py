# apps/leaderboards/api.py - Enhanced Leaderboard API
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import permissions
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from .models import LeaderboardType, Leaderboard, LeaderboardEntry
from .serializers import (
    LeaderboardTypeSerializer,
    LeaderboardSerializer,
    LeaderboardDetailSerializer,
    LeaderboardEntrySerializer,
)
from utils.redis_client import redis_client
import json

User = get_user_model()


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_exam_leaderboards(request):
    """
    Get exam leaderboards with filtering options.
    Default shows scheduled exam leaderboards.
    """
    # Get parameters
    exam_type = request.GET.get("exam_type", "scheduled")
    period = request.GET.get("period", "weekly")
    limit = int(request.GET.get("limit", "20"))

    # Cache key
    cache_key = f"exam_leaderboards:{exam_type}:{period}:{limit}:{request.user.id}"
    cached_data = redis_client.get(cache_key)

    if cached_data:
        return Response(
            # {"success": True, "leaderboards": json.loads(cached_data), "cached": True}
            {"success": True, "leaderboards": json.loads(cached_data), "cached": True}
        )

    try:
        # Get current time
        now = timezone.now()

        # Find the leaderboard type
        leaderboard_type = LeaderboardType.objects.filter(
            scope="exam",
            period=period,
            exam_type_filter=exam_type,
            is_active=True,
        ).first()

        if not leaderboard_type:
            return Response(
                {
                    "success": False,
                    "error": f"No leaderboard type found for {exam_type} exams with {period} period",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get current leaderboards for this type
        leaderboards = (
            Leaderboard.objects.filter(
                leaderboard_type=leaderboard_type,
                period_start__lte=now,
                period_end__gte=now,
            )
            .select_related("exam")
            .order_by("-total_participants")[:10]
        )

        response_data = []
        for leaderboard in leaderboards:
            # Get top entries
            top_entries = leaderboard.leaderboard_data[:limit]

            # Get user's rank if they're in this leaderboard
            user_rank = leaderboard.get_user_rank(request.user)
            user_entry = None

            if user_rank:
                try:
                    user_entry_obj = LeaderboardEntry.objects.get(
                        leaderboard=leaderboard, user=request.user
                    )
                    user_entry = {
                        "rank": user_rank,
                        "score": user_entry_obj.score,
                        "total_exams": user_entry_obj.total_exams,
                        "rank_change": user_entry_obj.rank_change,
                    }
                except LeaderboardEntry.DoesNotExist:
                    pass

            response_data.append(
                {
                    "id": str(leaderboard.id),
                    "exam_title": (
                        leaderboard.exam.title if leaderboard.exam else "All Exams"
                    ),
                    "exam_type": exam_type,
                    "period": period,
                    "period_start": leaderboard.period_start.isoformat(),
                    "period_end": leaderboard.period_end.isoformat(),
                    "total_participants": leaderboard.total_participants,
                    "top_entries": top_entries,
                    "user_entry": user_entry,
                    "last_updated": leaderboard.last_updated.isoformat(),
                }
            )

        # Cache for 5 minutes
        # redis_client.set(cache_key, json.dumps(response_data), ex=300)
        redis_client.set(cache_key, response_data, timeout=300)

        return Response(
            {
                "success": True,
                "leaderboards": response_data,
                "period_options": [
                    {"value": "weekly", "label": "Weekly"},
                    {"value": "biweekly", "label": "Bi-weekly"},
                    {"value": "monthly", "label": "Monthly"},
                    {"value": "quarterly", "label": "Quarterly"},
                ],
                "exam_type_options": [
                    {"value": "scheduled", "label": "Scheduled Exams"},
                    {"value": "practice", "label": "Practice Exams"},
                    {"value": "self_paced", "label": "Self-Paced Exams"},
                ],
            }
        )

    except Exception as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_leaderboard_detail(request, leaderboard_id):
    """
    Get detailed leaderboard with full entries list.
    """
    try:
        leaderboard = Leaderboard.objects.select_related(
            "leaderboard_type", "exam", "subject", "chapter"
        ).get(id=leaderboard_id)

        # Get all entries
        entries = (
            LeaderboardEntry.objects.filter(leaderboard=leaderboard)
            .select_related("user")
            .order_by("rank")
        )

        # Get user's entry
        user_entry = None
        try:
            user_entry_obj = entries.get(user=request.user)
            user_entry = LeaderboardEntrySerializer(user_entry_obj).data
        except LeaderboardEntry.DoesNotExist:
            pass

        # Serialize entries
        entries_data = LeaderboardEntrySerializer(entries, many=True).data

        return Response(
            {
                "success": True,
                "leaderboard": {
                    "id": str(leaderboard.id),
                    "name": leaderboard.leaderboard_type.name,
                    "description": leaderboard.leaderboard_type.description,
                    "exam_title": leaderboard.exam.title if leaderboard.exam else None,
                    "exam_type": leaderboard.leaderboard_type.exam_type_filter,
                    "period": leaderboard.leaderboard_type.period,
                    "period_start": leaderboard.period_start.isoformat(),
                    "period_end": leaderboard.period_end.isoformat(),
                    "total_participants": leaderboard.total_participants,
                    "is_current": leaderboard.is_current_period,
                    "score_method": leaderboard.leaderboard_type.score_calculation_method,
                    "last_updated": leaderboard.last_updated.isoformat(),
                },
                "entries": entries_data,
                "user_entry": user_entry,
                "statistics": {
                    "avg_score": (
                        sum(e["score"] for e in entries_data) / len(entries_data)
                        if entries_data
                        else 0
                    ),
                    "top_score": entries_data[0]["score"] if entries_data else 0,
                    "total_exams_played": sum(e["total_exams"] for e in entries_data),
                },
            }
        )

    except Leaderboard.DoesNotExist:
        return Response(
            {"success": False, "error": "Leaderboard not found"},
            status=status.HTTP_404_NOT_FOUND,
        )
    except Exception as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_user_leaderboard_summary(request):
    """
    Get user's leaderboard summary across different types.
    """
    try:
        user = request.user
        now = timezone.now()

        # Get user's current entries across different leaderboards
        current_entries = (
            LeaderboardEntry.objects.filter(
                user=user,
                leaderboard__period_start__lte=now,
                leaderboard__period_end__gte=now,
            )
            .select_related(
                "leaderboard", "leaderboard__leaderboard_type", "leaderboard__exam"
            )
            .order_by("rank")
        )

        summary = {
            "scheduled_exams": [],
            "practice_exams": [],
            "global_rankings": [],
            "recent_achievements": [],
            "performance_trends": [],
        }

        for entry in current_entries:
            leaderboard = entry.leaderboard
            exam_type = leaderboard.leaderboard_type.exam_type_filter

            entry_data = {
                "leaderboard_id": str(leaderboard.id),
                "leaderboard_name": leaderboard.leaderboard_type.name,
                "exam_title": leaderboard.exam.title if leaderboard.exam else "Global",
                "period": leaderboard.leaderboard_type.period,
                "rank": entry.rank,
                "score": entry.score,
                "total_participants": leaderboard.total_participants,
                "rank_change": entry.rank_change,
                "performance_trend": entry.performance_trend,
                "badges": entry.badges[:3],  # Top 3 badges
            }

            if exam_type == "scheduled":
                summary["scheduled_exams"].append(entry_data)
            elif exam_type == "practice":
                summary["practice_exams"].append(entry_data)
            elif leaderboard.leaderboard_type.scope == "global":
                summary["global_rankings"].append(entry_data)

            # Collect recent achievements
            for achievement in entry.achievements:
                summary["recent_achievements"].append(
                    {
                        "title": achievement.get("title"),
                        "description": achievement.get("description"),
                        "icon": achievement.get("icon"),
                        "earned_from": leaderboard.leaderboard_type.name,
                        "earned_at": entry.created_at.isoformat(),
                    }
                )

        # Get performance trends from recent entries
        recent_entries = (
            LeaderboardEntry.objects.filter(
                user=user,
                leaderboard__leaderboard_type__exam_type_filter="scheduled",
            )
            .select_related("leaderboard__leaderboard_type")
            .order_by("-created_at")[:5]
        )

        for entry in recent_entries:
            summary["performance_trends"].append(
                {
                    "period": f"{entry.leaderboard.period_start.strftime('%b %d')} - {entry.leaderboard.period_end.strftime('%b %d')}",
                    "rank": entry.rank,
                    "score": entry.score,
                    "trend": entry.performance_trend,
                    "total_participants": entry.leaderboard.total_participants,
                }
            )

        # Sort achievements by date
        summary["recent_achievements"].sort(key=lambda x: x["earned_at"], reverse=True)
        summary["recent_achievements"] = summary["recent_achievements"][:5]

        return Response(
            {
                "success": True,
                "summary": summary,
                "overall_stats": {
                    "total_leaderboards": len(current_entries),
                    "best_rank": (
                        min([e.rank for e in current_entries])
                        if current_entries
                        else None
                    ),
                    "total_achievements": sum(
                        len(e.achievements) for e in current_entries
                    ),
                    "total_badges": sum(len(e.badges) for e in current_entries),
                },
            }
        )

    except Exception as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_available_periods(request):
    """
    Get available leaderboard periods and types.
    """
    try:
        # Get active leaderboard types
        leaderboard_types = (
            LeaderboardType.objects.filter(
                is_active=True,
                is_public=True,
            )
            .values(
                "scope",
                "period",
                "exam_type_filter",
                "name",
                "description",
                "is_default",
            )
            .distinct()
        )

        periods = {}
        exam_types = {}

        for lb_type in leaderboard_types:
            period = lb_type["period"]
            exam_type = lb_type["exam_type_filter"]
            scope = lb_type["scope"]

            if period not in periods:
                periods[period] = {
                    "value": period,
                    "label": period.replace("_", " ").title(),
                    "description": f"{period.replace('_', ' ').title()} rankings",
                }

            if exam_type not in exam_types and scope == "exam":
                exam_types[exam_type] = {
                    "value": exam_type,
                    "label": exam_type.replace("_", " ").title(),
                    "is_default": lb_type["is_default"],
                }

        return Response(
            {
                "success": True,
                "periods": list(periods.values()),
                "exam_types": list(exam_types.values()),
                "scopes": [
                    {"value": "exam", "label": "Exam-specific"},
                    {"value": "subject", "label": "Subject-wise"},
                    {"value": "global", "label": "Global"},
                ],
            }
        )

    except Exception as e:
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
