# apps/leaderboards/serializers.py - Complete implementation
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
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


class LeaderboardTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for leaderboard types.
    """

    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    period_display = serializers.CharField(source="get_period_display", read_only=True)
    exam_type_filter_display = serializers.CharField(
        source="get_exam_type_filter_display", read_only=True
    )

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
            "exam_type_filter",
            "exam_type_filter_display",
            "is_active",
            "is_public",
            "is_default",
            "max_entries",
            "score_calculation_method",
            "min_exams_required",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class LeaderboardEntrySerializer(serializers.ModelSerializer):
    """
    Serializer for leaderboard entries.
    """

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    user_phone = serializers.CharField(source="user.phone_number", read_only=True)
    user_role = serializers.CharField(source="user.role", read_only=True)
    accuracy_rate = serializers.ReadOnlyField()
    performance_trend_display = serializers.CharField(
        source="get_performance_trend_display", read_only=True
    )

    class Meta:
        model = LeaderboardEntry
        fields = [
            "id",
            "rank",
            "previous_rank",
            "rank_change",
            "user_name",
            "user_phone",
            "user_role",
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
            "performance_trend_display",
            "achievements",
            "badges",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "rank",
            "rank_change",
            "accuracy_rate",
            "created_at",
            "updated_at",
        ]


class LeaderboardEntryDetailSerializer(LeaderboardEntrySerializer):
    """
    Detailed serializer for leaderboard entries with additional user information.
    """

    user_details = serializers.SerializerMethodField()
    rank_history = serializers.SerializerMethodField()
    recent_performance = serializers.SerializerMethodField()

    class Meta(LeaderboardEntrySerializer.Meta):
        fields = LeaderboardEntrySerializer.Meta.fields + [
            "user_details",
            "rank_history",
            "recent_performance",
        ]

    def get_user_details(self, obj):
        """Get additional user details."""
        user = obj.user
        return {
            "id": str(user.id),
            "full_name": user.get_full_name(),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone_number,
            "role": user.role,
            "is_verified": user.is_verified,
            "date_joined": user.created_at,
        }

    def get_rank_history(self, obj):
        """Get user's rank history in similar leaderboards."""
        # Get previous entries for this user in same leaderboard type
        previous_entries = (
            LeaderboardEntry.objects.filter(
                user=obj.user,
                leaderboard__leaderboard_type=obj.leaderboard.leaderboard_type,
            )
            .exclude(id=obj.id)
            .order_by("-leaderboard__period_end")[:5]
        )

        return [
            {
                "period_start": entry.leaderboard.period_start.date(),
                "period_end": entry.leaderboard.period_end.date(),
                "rank": entry.rank,
                "score": entry.score,
                "total_participants": entry.leaderboard.total_participants,
            }
            for entry in previous_entries
        ]

    def get_recent_performance(self, obj):
        """Get user's recent exam performance."""
        # Get recent exam results for this user
        from apps.results.models import ExamResult

        recent_results = ExamResult.objects.filter(
            user=obj.user, created_at__gte=timezone.now() - timedelta(days=30)
        ).order_by("-created_at")[:10]

        return [
            {
                "exam_title": result.exam.title,
                "exam_type": result.exam.exam_type,
                "score_percentage": result.percentage_score,
                "is_passed": result.is_passed,
                "time_taken_minutes": result.time_taken_minutes,
                "completed_at": result.created_at,
            }
            for result in recent_results
        ]


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
    user_rank = serializers.SerializerMethodField()

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
            "user_rank",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "total_participants",
            "last_updated",
            "created_at",
            "updated_at",
        ]

    def get_top_entries(self, obj):
        """Get top entries from cached leaderboard data."""
        # Return top 10 entries from cached data
        return obj.leaderboard_data[:10]

    def get_user_rank(self, obj):
        """Get current user's rank in this leaderboard."""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.get_user_rank(request.user)
        return None


class LeaderboardDetailSerializer(LeaderboardSerializer):
    """
    Detailed serializer for leaderboards with all entries.
    """

    entries = LeaderboardEntrySerializer(many=True, read_only=True)
    user_entry = serializers.SerializerMethodField()
    statistics = serializers.SerializerMethodField()
    participation_stats = serializers.SerializerMethodField()

    class Meta(LeaderboardSerializer.Meta):
        fields = LeaderboardSerializer.Meta.fields + [
            "entries",
            "user_entry",
            "statistics",
            "participation_stats",
        ]

    def get_user_entry(self, obj):
        """Get current user's entry in this leaderboard."""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            try:
                user_entry = obj.entries.get(user=request.user)
                return LeaderboardEntrySerializer(user_entry).data
            except LeaderboardEntry.DoesNotExist:
                return None
        return None

    def get_statistics(self, obj):
        """Get leaderboard statistics."""
        entries = obj.entries.all()
        if not entries.exists():
            return {
                "total_participants": 0,
                "average_score": 0,
                "highest_score": 0,
                "lowest_score": 0,
                "total_exams_taken": 0,
                "average_time_per_exam": 0,
            }

        scores = [entry.score for entry in entries]
        total_exams = sum(entry.total_exams for entry in entries)
        total_time = sum(entry.total_time_minutes for entry in entries)

        return {
            "total_participants": entries.count(),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "highest_score": max(scores) if scores else 0,
            "lowest_score": min(scores) if scores else 0,
            "total_exams_taken": total_exams,
            "average_time_per_exam": total_time / total_exams if total_exams > 0 else 0,
        }

    def get_participation_stats(self, obj):
        """Get participation statistics."""
        entries = obj.entries.all()

        # Performance distribution
        performance_ranges = {
            "excellent": entries.filter(score__gte=90).count(),
            "good": entries.filter(score__gte=70, score__lt=90).count(),
            "average": entries.filter(score__gte=50, score__lt=70).count(),
            "below_average": entries.filter(score__lt=50).count(),
        }

        # Trend analysis
        improving_count = entries.filter(performance_trend="improving").count()
        declining_count = entries.filter(performance_trend="declining").count()
        stable_count = entries.filter(performance_trend="stable").count()
        new_count = entries.filter(performance_trend="new").count()

        return {
            "performance_distribution": performance_ranges,
            "trend_analysis": {
                "improving": improving_count,
                "declining": declining_count,
                "stable": stable_count,
                "new": new_count,
            },
            "total_achievements": sum(len(entry.achievements) for entry in entries),
            "total_badges": sum(len(entry.badges) for entry in entries),
        }


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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        """Validate subscription data."""
        user = self.context["request"].user
        leaderboard_type = attrs.get("leaderboard_type")
        subject = attrs.get("subject")
        chapter = attrs.get("chapter")

        # Check if subscription already exists
        if self.instance is None:  # Creating new subscription
            existing = LeaderboardSubscription.objects.filter(
                user=user,
                leaderboard_type=leaderboard_type,
                subject=subject,
                chapter=chapter,
            ).first()

            if existing:
                raise serializers.ValidationError(
                    "You are already subscribed to this leaderboard."
                )

        return attrs


class UserLeaderboardSummarySerializer(serializers.Serializer):
    """
    Serializer for user's leaderboard summary across different boards.
    """

    global_rank = serializers.SerializerMethodField()
    subject_ranks = serializers.SerializerMethodField()
    exam_type_ranks = serializers.SerializerMethodField()
    recent_achievements = serializers.SerializerMethodField()
    performance_trends = serializers.SerializerMethodField()
    active_subscriptions = serializers.SerializerMethodField()

    def get_global_rank(self, obj):
        """Get user's global ranking."""
        user = obj["user"]

        try:
            now = timezone.now()
            global_leaderboard = Leaderboard.objects.filter(
                leaderboard_type__scope="global",
                leaderboard_type__period="monthly",
                period_start__lte=now,
                period_end__gte=now,
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
                    "leaderboard_name": global_leaderboard.leaderboard_type.name,
                }
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting global rank for user {user.id}: {str(e)}")

        return None

    def get_subject_ranks(self, obj):
        """Get user's ranking in different subjects."""
        user = obj["user"]
        subject_ranks = []

        try:
            now = timezone.now()
            subject_leaderboards = Leaderboard.objects.filter(
                leaderboard_type__scope="subject",
                period_start__lte=now,
                period_end__gte=now,
                entries__user=user,
            ).select_related("subject", "leaderboard_type")

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
                            "subject_id": (
                                str(leaderboard.subject.id)
                                if leaderboard.subject
                                else None
                            ),
                            "leaderboard_id": str(leaderboard.id),
                            "leaderboard_name": leaderboard.leaderboard_type.name,
                            "rank": entry.rank,
                            "score": entry.score,
                            "total_participants": leaderboard.total_participants,
                            "rank_change": entry.rank_change,
                            "period": leaderboard.leaderboard_type.period,
                        }
                    )
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting subject ranks for user {user.id}: {str(e)}")

        return subject_ranks

    def get_exam_type_ranks(self, obj):
        """Get user's ranking in different exam types."""
        user = obj["user"]
        exam_type_ranks = {
            "scheduled": [],
            "practice": [],
            "self_paced": [],
        }

        try:
            now = timezone.now()
            exam_leaderboards = Leaderboard.objects.filter(
                leaderboard_type__scope="exam",
                period_start__lte=now,
                period_end__gte=now,
                entries__user=user,
            ).select_related("leaderboard_type", "exam")

            for leaderboard in exam_leaderboards:
                entry = leaderboard.entries.filter(user=user).first()
                if entry:
                    exam_type = leaderboard.leaderboard_type.exam_type_filter
                    if exam_type in exam_type_ranks:
                        exam_type_ranks[exam_type].append(
                            {
                                "leaderboard_id": str(leaderboard.id),
                                "leaderboard_name": leaderboard.leaderboard_type.name,
                                "exam_title": (
                                    leaderboard.exam.title
                                    if leaderboard.exam
                                    else "All Exams"
                                ),
                                "rank": entry.rank,
                                "score": entry.score,
                                "total_participants": leaderboard.total_participants,
                                "rank_change": entry.rank_change,
                                "period": leaderboard.leaderboard_type.period,
                                "badges": entry.badges[:3],  # Top 3 badges
                            }
                        )
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error getting exam type ranks for user {user.id}: {str(e)}")

        return exam_type_ranks

    def get_recent_achievements(self, obj):
        """Get user's recent achievements."""
        user = obj["user"]

        try:
            recent_entries = (
                LeaderboardEntry.objects.filter(
                    user=user, created_at__gte=timezone.now() - timedelta(days=30)
                )
                .exclude(achievements=[])
                .select_related("leaderboard__leaderboard_type")
            )

            achievements = []
            for entry in recent_entries:
                for achievement in entry.achievements:
                    achievements.append(
                        {
                            "title": achievement.get("title"),
                            "description": achievement.get("description"),
                            "icon": achievement.get("icon"),
                            "type": achievement.get("type"),
                            "earned_at": entry.created_at,
                            "leaderboard": entry.leaderboard.leaderboard_type.name,
                            "leaderboard_id": str(entry.leaderboard.id),
                        }
                    )

            # Sort by date and return latest 10
            achievements.sort(key=lambda x: x["earned_at"], reverse=True)
            return achievements[:10]
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
            recent_entries = (
                LeaderboardEntry.objects.filter(
                    user=user,
                    leaderboard__leaderboard_type__exam_type_filter="scheduled",  # Focus on scheduled exams
                )
                .select_related("leaderboard__leaderboard_type")
                .order_by("-created_at")[:10]
            )

            trends = []
            for entry in recent_entries:
                trends.append(
                    {
                        "leaderboard_id": str(entry.leaderboard.id),
                        "leaderboard_name": entry.leaderboard.leaderboard_type.name,
                        "period": f"{entry.leaderboard.period_start.date()} to {entry.leaderboard.period_end.date()}",
                        "rank": entry.rank,
                        "previous_rank": entry.previous_rank,
                        "rank_change": entry.rank_change,
                        "score": entry.score,
                        "trend": entry.performance_trend,
                        "improvement_rate": entry.improvement_rate,
                        "total_participants": entry.leaderboard.total_participants,
                        "period_start": entry.leaderboard.period_start,
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

    def get_active_subscriptions(self, obj):
        """Get user's active leaderboard subscriptions."""
        user = obj["user"]

        try:
            subscriptions = LeaderboardSubscription.objects.filter(
                user=user,
                is_active=True,
            ).select_related("leaderboard_type", "subject", "chapter")

            return [
                {
                    "id": str(sub.id),
                    "leaderboard_type": sub.leaderboard_type.name,
                    "scope": sub.leaderboard_type.scope,
                    "period": sub.leaderboard_type.period,
                    "subject": sub.subject.name if sub.subject else None,
                    "chapter": sub.chapter.name if sub.chapter else None,
                    "notify_on_rank_change": sub.notify_on_rank_change,
                    "notify_on_new_achievements": sub.notify_on_new_achievements,
                    "email_notifications": sub.email_notifications,
                }
                for sub in subscriptions
            ]
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Error getting active subscriptions for user {user.id}: {str(e)}"
            )
            return []


class LeaderboardCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating custom leaderboards (admin/teacher use).
    """

    class Meta:
        model = Leaderboard
        fields = [
            "leaderboard_type",
            "subject",
            "chapter",
            "exam",
            "period_start",
            "period_end",
        ]

    def validate(self, attrs):
        """Validate leaderboard creation data."""
        period_start = attrs.get("period_start")
        period_end = attrs.get("period_end")

        if period_start and period_end:
            if period_start >= period_end:
                raise serializers.ValidationError(
                    "Period start must be before period end."
                )

            # Check for overlapping periods
            leaderboard_type = attrs.get("leaderboard_type")
            subject = attrs.get("subject")
            chapter = attrs.get("chapter")
            exam = attrs.get("exam")

            existing = Leaderboard.objects.filter(
                leaderboard_type=leaderboard_type,
                subject=subject,
                chapter=chapter,
                exam=exam,
                period_start__lt=period_end,
                period_end__gt=period_start,
            )

            if self.instance:
                existing = existing.exclude(id=self.instance.id)

            if existing.exists():
                raise serializers.ValidationError(
                    "A leaderboard with overlapping period already exists."
                )

        return attrs


class LeaderboardBulkUpdateSerializer(serializers.Serializer):
    """
    Serializer for bulk updating leaderboards.
    """

    leaderboard_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of leaderboard IDs to update",
    )
    action = serializers.ChoiceField(
        choices=[
            ("recalculate", "Recalculate Rankings"),
            ("finalize", "Mark as Finalized"),
            ("activate", "Activate"),
            ("deactivate", "Deactivate"),
        ]
    )

    def validate_leaderboard_ids(self, value):
        """Validate that all leaderboard IDs exist."""
        existing_ids = set(
            Leaderboard.objects.filter(id__in=value).values_list("id", flat=True)
        )
        provided_ids = set(value)

        missing_ids = provided_ids - existing_ids
        if missing_ids:
            raise serializers.ValidationError(
                f"Leaderboards not found: {list(missing_ids)}"
            )

        return value
