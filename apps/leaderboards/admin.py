from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Avg, Sum, Q
from datetime import datetime, timedelta
from .models import (
    LeaderboardType,
    Leaderboard,
    LeaderboardEntry,
    LeaderboardSubscription,
)


class LeaderboardInline(admin.TabularInline):
    """Inline for leaderboards under leaderboard type."""

    model = Leaderboard
    extra = 0
    fields = (
        "subject",
        "chapter",
        "exam",
        "period_start",
        "period_end",
        "total_participants",
        "is_finalized",
    )
    readonly_fields = ("total_participants", "last_updated")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LeaderboardType)
class LeaderboardTypeAdmin(admin.ModelAdmin):
    """Admin for LeaderboardType model."""

    list_display = [
        "name",
        "scope_badge",
        "period_badge",
        "score_method",
        "is_active_display",
        "is_public_display",
        "max_entries",
        "min_exams_required",
        "leaderboard_count",
    ]

    list_filter = [
        "scope",
        "period",
        "score_calculation_method",
        "is_active",
        "is_public",
        "created_at",
    ]

    search_fields = ["name", "description"]

    readonly_fields = ["id", "created_at", "updated_at", "active_leaderboards_count"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("id", "name", "description", "scope", "period")},
        ),
        (
            "Configuration",
            {
                "fields": (
                    "is_active",
                    "is_public",
                    "max_entries",
                    "score_calculation_method",
                    "min_exams_required",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": ("active_leaderboards_count", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = [
        "activate_types",
        "deactivate_types",
        "make_public",
        "make_private",
        "generate_current_period_leaderboards",
    ]

    def scope_badge(self, obj):
        """Display scope as badge."""
        colors = {
            "global": "#007bff",
            "subject": "#28a745",
            "chapter": "#ffc107",
            "exam": "#dc3545",
        }
        color = colors.get(obj.scope, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_scope_display(),
        )

    scope_badge.short_description = "Scope"

    def period_badge(self, obj):
        """Display period as badge."""
        colors = {
            "all_time": "#6f42c1",
            "yearly": "#20c997",
            "monthly": "#fd7e14",
            "weekly": "#e83e8c",
            "daily": "#17a2b8",
        }
        color = colors.get(obj.period, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_period_display(),
        )

    period_badge.short_description = "Period"

    def score_method(self, obj):
        """Display score calculation method."""
        return obj.get_score_calculation_method_display()

    score_method.short_description = "Scoring"

    def is_active_display(self, obj):
        """Display active status."""
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Active</span>')
        return format_html('<span style="color: red;">✗ Inactive</span>')

    is_active_display.short_description = "Active"

    def is_public_display(self, obj):
        """Display public status."""
        if obj.is_public:
            return format_html('<span style="color: green;">🌐 Public</span>')
        return format_html('<span style="color: orange;">🔒 Private</span>')

    is_public_display.short_description = "Visibility"

    def leaderboard_count(self, obj):
        """Count of leaderboards."""
        count = obj.leaderboards.count()
        return format_html("<strong>{}</strong>", count)

    leaderboard_count.short_description = "Leaderboards"

    def active_leaderboards_count(self, obj):
        """Count of active leaderboards."""
        now = timezone.now()
        count = obj.leaderboards.filter(
            period_start__lte=now, period_end__gte=now
        ).count()
        return f"{count} active leaderboards"

    active_leaderboards_count.short_description = "Active Leaderboards"

    def activate_types(self, request, queryset):
        """Activate selected types."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} leaderboard types activated.")

    activate_types.short_description = "Activate selected types"

    def deactivate_types(self, request, queryset):
        """Deactivate selected types."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} leaderboard types deactivated.")

    deactivate_types.short_description = "Deactivate selected types"

    def make_public(self, request, queryset):
        """Make types public."""
        updated = queryset.update(is_public=True)
        self.message_user(request, f"{updated} types made public.")

    make_public.short_description = "Make public"

    def make_private(self, request, queryset):
        """Make types private."""
        updated = queryset.update(is_public=False)
        self.message_user(request, f"{updated} types made private.")

    make_private.short_description = "Make private"

    def generate_current_period_leaderboards(self, request, queryset):
        """Generate leaderboards for current period."""
        from .tasks import generate_leaderboards

        for lb_type in queryset:
            generate_leaderboards.delay(lb_type.id)
        self.message_user(
            request, f"Leaderboard generation initiated for {queryset.count()} types."
        )

    generate_current_period_leaderboards.short_description = (
        "Generate current leaderboards"
    )


class LeaderboardEntryInline(admin.TabularInline):
    """Inline for top leaderboard entries."""

    model = LeaderboardEntry
    extra = 0
    fields = (
        "rank",
        "user",
        "score",
        "total_exams",
        "average_score",
        "rank_change_display",
    )
    readonly_fields = (
        "rank",
        "user",
        "score",
        "total_exams",
        "average_score",
        "rank_change_display",
    )
    can_delete = False
    max_num = 10  # Show only top 10

    def rank_change_display(self, obj):
        """Display rank change."""
        if obj.rank_change > 0:
            return format_html(
                '<span style="color: green;">↑ {}</span>', obj.rank_change
            )
        elif obj.rank_change < 0:
            return format_html(
                '<span style="color: red;">↓ {}</span>', abs(obj.rank_change)
            )
        return format_html('<span style="color: gray;">—</span>')

    rank_change_display.short_description = "Change"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Leaderboard)
class LeaderboardAdmin(admin.ModelAdmin):
    """Admin for Leaderboard model."""

    list_display = [
        "display_name",
        "leaderboard_type",
        "scope_filter",
        "period_display",
        "total_participants",
        "status_display",
        "last_updated",
    ]

    list_filter = [
        "leaderboard_type__scope",
        "leaderboard_type__period",
        "is_finalized",
        ("subject", admin.RelatedOnlyFieldListFilter),
        ("exam", admin.RelatedOnlyFieldListFilter),
        "period_start",
    ]

    search_fields = [
        "leaderboard_type__name",
        "subject__name",
        "chapter__name",
        "exam__title",
    ]

    readonly_fields = [
        "id",
        "total_participants",
        "last_updated",
        "is_current_period",
        "leaderboard_preview",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (
            "Leaderboard Information",
            {"fields": ("id", "leaderboard_type", "subject", "chapter", "exam")},
        ),
        (
            "Period Settings",
            {
                "fields": (
                    "period_start",
                    "period_end",
                    "is_current_period",
                    "is_finalized",
                )
            },
        ),
        (
            "Statistics",
            {"fields": ("total_participants", "last_updated", "leaderboard_preview")},
        ),
        ("Cached Data", {"fields": ("leaderboard_data",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    inlines = [LeaderboardEntryInline]

    actions = [
        "update_leaderboard",
        "finalize_leaderboard",
        "export_to_csv",
        "reset_leaderboard",
    ]

    def display_name(self, obj):
        """Display formatted name."""
        return str(obj)[:50]

    display_name.short_description = "Leaderboard"

    def scope_filter(self, obj):
        """Display scope filter."""
        if obj.subject:
            return format_html(
                '<span style="color: #28a745;">📚 {}</span>', obj.subject.name
            )
        elif obj.chapter:
            return format_html(
                '<span style="color: #ffc107;">📖 {}</span>', obj.chapter.name
            )
        elif obj.exam:
            return format_html(
                '<span style="color: #dc3545;">📝 {}</span>', obj.exam.title[:30]
            )
        return format_html('<span style="color: #007bff;">🌍 Global</span>')

    scope_filter.short_description = "Filter"

    def period_display(self, obj):
        """Display period."""
        return format_html(
            "{} → {}",
            obj.period_start.strftime("%Y-%m-%d"),
            obj.period_end.strftime("%Y-%m-%d"),
        )

    period_display.short_description = "Period"

    def status_display(self, obj):
        """Display status."""
        if obj.is_finalized:
            return format_html('<span style="color: gray;">🔒 Finalized</span>')
        elif obj.is_current_period:
            return format_html('<span style="color: green;">🟢 Active</span>')
        else:
            return format_html('<span style="color: orange;">⏸ Inactive</span>')

    status_display.short_description = "Status"

    def leaderboard_preview(self, obj):
        """Preview top entries."""
        if obj.leaderboard_data:
            preview = '<table style="width: 100%;">'
            preview += "<tr><th>Rank</th><th>User</th><th>Score</th></tr>"

            for entry in obj.leaderboard_data[:5]:
                preview += f'<tr><td>#{entry.get("rank", "-")}</td>'
                preview += f'<td>{entry.get("user_name", "Unknown")}</td>'
                preview += f'<td>{entry.get("score", 0):.2f}</td></tr>'

            preview += "</table>"
            if len(obj.leaderboard_data) > 5:
                preview += (
                    f"<p>... and {len(obj.leaderboard_data) - 5} more entries</p>"
                )

            return format_html(preview)
        return "No data available"

    leaderboard_preview.short_description = "Top 5 Preview"

    def update_leaderboard(self, request, queryset):
        """Update leaderboard data."""
        from .tasks import update_leaderboard_entries

        for leaderboard in queryset:
            update_leaderboard_entries.delay(leaderboard.id)
        self.message_user(
            request, f"Update initiated for {queryset.count()} leaderboards."
        )

    update_leaderboard.short_description = "Update leaderboard data"

    def finalize_leaderboard(self, request, queryset):
        """Finalize leaderboards."""
        updated = queryset.update(is_finalized=True)
        self.message_user(request, f"{updated} leaderboards finalized.")

    finalize_leaderboard.short_description = "Finalize selected leaderboards"

    def export_to_csv(self, request, queryset):
        """Export leaderboard to CSV."""
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="leaderboard.csv"'

        writer = csv.writer(response)
        writer.writerow(
            ["Rank", "User", "Score", "Exams", "Avg Score", "Best Score", "Trend"]
        )

        for leaderboard in queryset:
            writer.writerow([f"--- {leaderboard} ---"])
            for entry in leaderboard.entries.all()[:100]:
                writer.writerow(
                    [
                        entry.rank,
                        entry.user.phone_number,
                        f"{entry.score:.2f}",
                        entry.total_exams,
                        f"{entry.average_score:.2f}",
                        f"{entry.best_score:.2f}",
                        entry.performance_trend,
                    ]
                )
            writer.writerow([])  # Empty row between leaderboards

        return response

    export_to_csv.short_description = "Export to CSV"

    def reset_leaderboard(self, request, queryset):
        """Reset leaderboard data."""
        for leaderboard in queryset:
            leaderboard.entries.all().delete()
            leaderboard.leaderboard_data = []
            leaderboard.total_participants = 0
            leaderboard.save()
        self.message_user(request, f"{queryset.count()} leaderboards reset.")

    reset_leaderboard.short_description = "Reset leaderboard data"


@admin.register(LeaderboardEntry)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    """Admin for LeaderboardEntry model."""

    list_display = [
        "rank_display",
        "user_display",
        "leaderboard_info",
        "score_display",
        "performance_metrics",
        "trend_display",
        "achievements_count",
    ]

    list_filter = [
        "performance_trend",
        "leaderboard__leaderboard_type__scope",
        "leaderboard__leaderboard_type__period",
        "rank",
        "created_at",
    ]

    search_fields = [
        "user__phone_number",
        "user__first_name",
        "user__last_name",
        "leaderboard__leaderboard_type__name",
    ]

    readonly_fields = [
        "id",
        "accuracy_rate",
        "rank_change_visualization",
        "performance_chart",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (
            "Entry Information",
            {
                "fields": (
                    "id",
                    "leaderboard",
                    "user",
                    "rank",
                    "previous_rank",
                    "rank_change",
                    "rank_change_visualization",
                )
            },
        ),
        (
            "Performance Metrics",
            {
                "fields": (
                    "score",
                    "total_exams",
                    "total_questions",
                    "correct_answers",
                    "accuracy_rate",
                    "average_score",
                    "best_score",
                    "total_time_minutes",
                    "consistency_score",
                )
            },
        ),
        (
            "Trends & Analysis",
            {"fields": ("improvement_rate", "performance_trend", "performance_chart")},
        ),
        (
            "Achievements",
            {"fields": ("achievements", "badges"), "classes": ("collapse",)},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def rank_display(self, obj):
        """Display rank with medal for top 3."""
        if obj.rank == 1:
            return format_html('<span style="font-size: 20px;">🥇</span> #1')
        elif obj.rank == 2:
            return format_html('<span style="font-size: 20px;">🥈</span> #2')
        elif obj.rank == 3:
            return format_html('<span style="font-size: 20px;">🥉</span> #3')
        else:
            return f"#{obj.rank}"

    rank_display.short_description = "Rank"

    def user_display(self, obj):
        """Display user with link."""
        url = reverse("admin:authentication_user_change", args=[obj.user.id])
        return format_html(
            '<a href="{}">{}</a>', url, obj.user.full_name or obj.user.phone_number
        )

    user_display.short_description = "User"

    def leaderboard_info(self, obj):
        """Display leaderboard info."""
        return format_html(
            "<small>{}<br/>{}</small>",
            obj.leaderboard.leaderboard_type.name,
            (
                obj.leaderboard.get_period_display()
                if hasattr(obj.leaderboard, "get_period_display")
                else ""
            ),
        )

    leaderboard_info.short_description = "Leaderboard"

    def score_display(self, obj):
        """Display score with color."""
        if obj.score >= 90:
            color = "green"
        elif obj.score >= 70:
            color = "orange"
        else:
            color = "red"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.2f}</span>',
            color,
            obj.score,
        )

    score_display.short_description = "Score"

    def performance_metrics(self, obj):
        """Display key performance metrics."""
        return format_html(
            "Exams: <strong>{}</strong><br/>"
            "Accuracy: <strong>{:.1f}%</strong><br/>"
            "Avg: <strong>{:.1f}</strong>",
            obj.total_exams,
            obj.accuracy_rate,
            obj.average_score,
        )

    performance_metrics.short_description = "Metrics"

    def trend_display(self, obj):
        """Display performance trend."""
        icons = {"improving": "📈", "declining": "📉", "stable": "➡️", "new": "🆕"}
        colors = {
            "improving": "green",
            "declining": "red",
            "stable": "blue",
            "new": "gray",
        }
        return format_html(
            '<span style="color: {};">{} {}</span>',
            colors.get(obj.performance_trend, "gray"),
            icons.get(obj.performance_trend, ""),
            obj.get_performance_trend_display(),
        )

    trend_display.short_description = "Trend"

    def achievements_count(self, obj):
        """Display achievements count."""
        achievements = len(obj.achievements) if obj.achievements else 0
        badges = len(obj.badges) if obj.badges else 0
        return format_html("🏆 {} | 🎖️ {}", achievements, badges)

    achievements_count.short_description = "Awards"

    def rank_change_visualization(self, obj):
        """Visualize rank change."""
        if obj.previous_rank and obj.rank_change != 0:
            if obj.rank_change > 0:
                arrow = "↑" * min(abs(obj.rank_change), 5)
                color = "green"
                change_text = f"Improved by {obj.rank_change} positions"
            else:
                arrow = "↓" * min(abs(obj.rank_change), 5)
                color = "red"
                change_text = f"Dropped by {abs(obj.rank_change)} positions"

            return format_html(
                '<span style="color: {}; font-size: 20px;">{}</span><br/>'
                "<small>Previous: #{} → Current: #{}<br/>{}</small>",
                color,
                arrow,
                obj.previous_rank,
                obj.rank,
                change_text,
            )
        return "No change"

    rank_change_visualization.short_description = "Rank Change"

    def performance_chart(self, obj):
        """Simple performance visualization."""
        bar_length = int(obj.average_score / 10)
        bar = "█" * bar_length + "░" * (10 - bar_length)
        return format_html(
            "Average: {} {:.1f}%<br/>" "Best: {} {:.1f}%",
            bar,
            obj.average_score,
            "█" * int(obj.best_score / 10),
            obj.best_score,
        )

    performance_chart.short_description = "Performance"


@admin.register(LeaderboardSubscription)
class LeaderboardSubscriptionAdmin(admin.ModelAdmin):
    """Admin for LeaderboardSubscription model."""

    list_display = [
        "user_display",
        "leaderboard_type",
        "scope_filter",
        "notification_settings",
        "is_active_display",
    ]

    list_filter = [
        "is_active",
        "notify_on_rank_change",
        "notify_on_new_achievements",
        "notify_on_period_end",
        "email_notifications",
        "sms_notifications",
        "leaderboard_type__scope",
    ]

    search_fields = [
        "user__phone_number",
        "user__first_name",
        "user__last_name",
        "leaderboard_type__name",
    ]

    fieldsets = (
        (
            "Subscription Details",
            {"fields": ("user", "leaderboard_type", "subject", "chapter", "is_active")},
        ),
        (
            "Notification Preferences",
            {
                "fields": (
                    "notify_on_rank_change",
                    "notify_on_new_achievements",
                    "notify_on_period_end",
                )
            },
        ),
        (
            "Notification Methods",
            {"fields": ("email_notifications", "sms_notifications")},
        ),
    )

    def user_display(self, obj):
        """Display user info."""
        return f"{obj.user.full_name or obj.user.phone_number}"

    user_display.short_description = "User"

    def scope_filter(self, obj):
        """Display scope filter."""
        if obj.subject:
            return f"Subject: {obj.subject.name}"
        elif obj.chapter:
            return f"Chapter: {obj.chapter.name}"
        return "All"

    scope_filter.short_description = "Filter"

    def notification_settings(self, obj):
        """Display notification settings."""
        settings = []
        if obj.notify_on_rank_change:
            settings.append("📊 Rank")
        if obj.notify_on_new_achievements:
            settings.append("🏆 Achievements")
        if obj.notify_on_period_end:
            settings.append("📅 Period End")

        methods = []
        if obj.email_notifications:
            methods.append("📧")
        if obj.sms_notifications:
            methods.append("💬")

        return format_html(
            "{}<br/><small>via {}</small>",
            " ".join(settings) if settings else "None",
            " ".join(methods) if methods else "None",
        )

    notification_settings.short_description = "Notifications"

    def is_active_display(self, obj):
        """Display active status."""
        if obj.is_active:
            return format_html('<span style="color: green;">✓ Active</span>')
        return format_html('<span style="color: red;">✗ Inactive</span>')

    is_active_display.short_description = "Status"
