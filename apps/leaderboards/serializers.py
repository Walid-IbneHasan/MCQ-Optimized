from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    LeaderboardType,
    Leaderboard,
    LeaderboardEntry,
    LeaderboardSubscription,
)
from apps.subjects.serializers import SubjectSerializer, ChapterSerializer
from apps.exams.serializers import ExamListSerializer
from datetime import timedelta, timezone

User = get_user_model()


class LeaderboardTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for leaderboard types.
    """

    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    period_display = serializers.CharField(source="get_period_display", read_only=True)

    class Meta:
        model = LeaderboardType
        fields = [
            "id",
            "name",
            "description",
            "scope",
            "scope_display",
            "period",
            "period_display",
            "is_active",
            "is_public",
            "max_entries",
            "score_calculation_method",
            "min_exams_required",
        ]
        read_only_fields = ["id"]


class LeaderboardEntrySerializer(serializers.ModelSerializer):
    """
    Serializer for leaderboard entries.
    """

    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_phone = serializers.CharField(source="user.phone_number", read_only=True)
    accuracy_rate = serializers.ReadOnlyField()

    class Meta:
        model = LeaderboardEntry
        fields = [
            "rank",
            "previous_rank",
            "rank_change",
            "user_name",
            "user_phone",
            "score",
            "total_exams",
            "total_questions",
            "correct_answers",
            "average_score",
            "best_score",
            "total_time_minutes",
            "consistency_score",
            "accuracy_rate",
            "improvement_rate",
            "performance_trend",
            "achievements",
            "badges",
        ]
        read_only_fields = ["rank", "rank_change", "accuracy_rate"]


class LeaderboardSerializer(serializers.ModelSerializer):
    """
    Serializer for leaderboards.
    """

    leaderboard_type_detail = LeaderboardTypeSerializer(
        source="leaderboard_type", read_only=True
    )
    subject_detail = SubjectSerializer(source="subject", read_only=True)
    chapter_detail = ChapterSerializer(source="chapter", read_only=True)
    exam_detail = ExamListSerializer(source="exam", read_only=True)
    is_current_period = serializers.ReadOnlyField()
    top_entries = serializers.SerializerMethodField()

    class Meta:
        model = Leaderboard
        fields = [
            "id",
            "leaderboard_type_detail",
            "subject_detail",
            "chapter_detail",
            "exam_detail",
            "period_start",
            "period_end",
            "total_participants",
            "last_updated",
            "is_finalized",
            "is_current_period",
            "top_entries",
        ]
        read_only_fields = ["id", "total_participants", "last_updated"]

    def get_top_entries(self, obj):
        """Get top entries from cached leaderboard data."""
        # Return top 10 entries from cached data
        return obj.leaderboard_data[:10]


class LeaderboardDetailSerializer(LeaderboardSerializer):
    """
    Detailed serializer for leaderboards with all entries.
    """

    entries = LeaderboardEntrySerializer(many=True, read_only=True)
    user_rank = serializers.SerializerMethodField()

    class Meta(LeaderboardSerializer.Meta):
        fields = LeaderboardSerializer.Meta.fields + ["entries", "user_rank"]

    def get_user_rank(self, obj):
        """Get current user's rank in this leaderboard."""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.get_user_rank(request.user)
        return None


class LeaderboardSubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for leaderboard subscriptions.
    """

    leaderboard_type_detail = LeaderboardTypeSerializer(
        source="leaderboard_type", read_only=True
    )
    subject_detail = SubjectSerializer(source="subject", read_only=True)
    chapter_detail = ChapterSerializer(source="chapter", read_only=True)

    class Meta:
        model = LeaderboardSubscription
        fields = [
            "id",
            "leaderboard_type",
            "leaderboard_type_detail",
            "subject",
            "subject_detail",
            "chapter",
            "chapter_detail",
            "notify_on_rank_change",
            "notify_on_new_achievements",
            "notify_on_period_end",
            "email_notifications",
            "sms_notifications",
            "is_active",
        ]
        read_only_fields = ["id"]


class UserLeaderboardSummarySerializer(serializers.Serializer):
    """
    Serializer for user's leaderboard summary across different boards.
    """

    global_rank = serializers.SerializerMethodField()
    subject_ranks = serializers.SerializerMethodField()
    recent_achievements = serializers.SerializerMethodField()
    performance_trends = serializers.SerializerMethodField()

    def get_global_rank(self, obj):
        """Get user's global ranking."""
        user = obj["user"]

        # Get current global leaderboard - fix the filter to use proper date comparison
        try:
            now = timezone.now()
            global_leaderboard = Leaderboard.objects.filter(
                leaderboard_type__scope="global",
                leaderboard_type__period="monthly",
                period_start__lte=now,
                period_end__gte=now,  # Use date comparison instead of is_current_period
            ).first()

            if global_leaderboard:
                rank = global_leaderboard.get_user_rank(user)
                entry = global_leaderboard.entries.filter(user=user).first()

                return {
                    "rank": rank,
                    "score": entry.score if entry else 0,
                    "total_participants": global_leaderboard.total_participants,
                    "percentile": (
                        round(
                            (1 - (rank / global_leaderboard.total_participants)) * 100,
                            1,
                        )
                        if rank and global_leaderboard.total_participants > 0
                        else 0
                    ),
                }
        except Exception as e:
            # Log the error but don't break the response
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting global rank for user {user.id}: {str(e)}")

        return None

    def get_subject_ranks(self, obj):
        """Get user's ranking in different subjects."""
        user = obj["user"]
        subject_ranks = []

        try:
            # Get subject-wise rankings - fix the filter
            now = timezone.now()
            subject_leaderboards = Leaderboard.objects.filter(
                leaderboard_type__scope="subject",
                period_start__lte=now,
                period_end__gte=now,  # Use date comparison instead of is_current_period
                entries__user=user,
            ).select_related("subject")

            for leaderboard in subject_leaderboards:
                entry = leaderboard.entries.filter(user=user).first()
                if entry:
                    subject_ranks.append(
                        {
                            "subject": (
                                leaderboard.subject.name
                                if leaderboard.subject
                                else "Unknown"
                            ),
                            "rank": entry.rank,
                            "score": entry.score,
                            "total_participants": leaderboard.total_participants,
                        }
                    )
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting subject ranks for user {user.id}: {str(e)}")

        return subject_ranks

    def get_recent_achievements(self, obj):
        """Get user's recent achievements."""
        user = obj["user"]

        try:
            # Get recent achievements from leaderboard entries
            recent_entries = LeaderboardEntry.objects.filter(
                user=user, created_at__gte=timezone.now() - timedelta(days=30)
            ).exclude(achievements=[])

            achievements = []
            for entry in recent_entries:
                for achievement in entry.achievements:
                    achievements.append(
                        {
                            "title": achievement.get("title"),
                            "description": achievement.get("description"),
                            "earned_at": entry.created_at,
                            "leaderboard": entry.leaderboard.leaderboard_type.name,
                        }
                    )

            return achievements[:5]  # Return latest 5 achievements
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Error getting recent achievements for user {user.id}: {str(e)}"
            )
            return []

    def get_performance_trends(self, obj):
        """Get user's performance trends."""
        user = obj["user"]

        try:
            # Get performance trends from recent entries
            recent_entries = LeaderboardEntry.objects.filter(user=user).order_by(
                "-created_at"
            )[:5]

            trends = []
            for entry in recent_entries:
                trends.append(
                    {
                        "period": f"{entry.leaderboard.period_start.date()} to {entry.leaderboard.period_end.date()}",
                        "rank": entry.rank,
                        "score": entry.score,
                        "trend": entry.performance_trend,
                        "improvement_rate": entry.improvement_rate,
                    }
                )

            return trends
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Error getting performance trends for user {user.id}: {str(e)}"
            )
            return []
