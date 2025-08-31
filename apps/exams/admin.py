from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Count, Avg, Q
from .models import Exam, ExamSession, ExamAnswer, ExamQuestion


class ChapterInline(admin.TabularInline):
    """Inline for exam chapters."""

    model = Exam.chapters.through
    extra = 1
    verbose_name = "Chapter"
    verbose_name_plural = "Chapters"


class ExamSessionInline(admin.TabularInline):
    """Inline for exam sessions."""

    model = ExamSession
    extra = 0
    readonly_fields = ("user", "status", "started_at", "percentage_score")
    fields = ("user", "status", "started_at", "percentage_score", "is_passed")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    """Admin for Exam model."""

    list_display = [
        "title",
        "exam_type",
        "total_questions",
        "duration_minutes",
        "is_active",
        "is_public",
        "requires_subscription",
        "total_attempts",
        "average_score_display",
        "created_by",
        "created_at",
    ]

    list_filter = [
        "exam_type",
        "is_active",
        "is_public",
        "requires_subscription",
        "negative_marking_enabled",
        "created_at",
        "created_by__role",
    ]

    search_fields = [
        "title",
        "description",
        "created_by__phone_number",
        "created_by__first_name",
        "created_by__last_name",
    ]

    readonly_fields = [
        "id",
        "total_attempts",
        "average_score",
        "created_at",
        "updated_at",
        "exam_status_display",
        "can_start_now",
        "is_scheduled_active",
    ]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("id", "title", "description", "created_by", "exam_type")},
        ),
        (
            "Exam Configuration",
            {
                "fields": (
                    "total_questions",
                    "questions_per_chapter",
                    "difficulty_distribution",
                    "randomize_questions",
                    "randomize_options",
                )
            },
        ),
        (
            "Time Settings",
            {
                "fields": (
                    "duration_minutes",
                    "time_per_question",
                    "allow_custom_duration",
                    "max_duration_minutes",
                    "auto_submit_on_time_up",
                    "grace_period_seconds",
                )
            },
        ),
        (
            "Scheduling",
            {
                "fields": ("scheduled_start", "scheduled_end", "exam_status_display"),
                "classes": ("collapse",),
                "description": "Only for scheduled exams",
            },
        ),
        (
            "Scoring Settings",
            {
                "fields": (
                    "marks_per_question",
                    "negative_marking_enabled",
                    "negative_marks",
                    "passing_percentage",
                )
            },
        ),
        (
            "Access Settings",
            {
                "fields": (
                    "is_active",
                    "is_public",
                    "requires_subscription",
                    "allow_retakes",
                    "max_attempts",
                )
            },
        ),
        (
            "Analytics",
            {
                "fields": (
                    "total_attempts",
                    "average_score",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    filter_horizontal = ("chapters",)

    date_hierarchy = "created_at"

    actions = [
        "activate_exams",
        "deactivate_exams",
        "make_public",
        "make_private",
        "export_exam_data",
    ]

    def average_score_display(self, obj):
        """Display average score with color coding."""
        if obj.average_score >= 80:
            color = "green"
        elif obj.average_score >= 60:
            color = "orange"
        else:
            color = "red"
        return format_html(
            '<span style="color: {};">{:.2f}%</span>', color, obj.average_score
        )

    average_score_display.short_description = "Avg Score"

    def exam_status_display(self, obj):
        """Display exam status."""
        if obj.exam_type == "scheduled":
            if obj.is_scheduled_active:
                return format_html('<span style="color: green;">🟢 Active</span>')
            elif obj.scheduled_start and obj.scheduled_start > timezone.now():
                return format_html('<span style="color: orange;">⏰ Upcoming</span>')
            else:
                return format_html('<span style="color: red;">🔴 Ended</span>')
        else:
            if obj.is_active:
                return format_html('<span style="color: green;">✓ Active</span>')
            else:
                return format_html('<span style="color: red;">✗ Inactive</span>')

    exam_status_display.short_description = "Status"

    def activate_exams(self, request, queryset):
        """Activate selected exams."""
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} exams activated.")

    activate_exams.short_description = "Activate selected exams"

    def deactivate_exams(self, request, queryset):
        """Deactivate selected exams."""
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} exams deactivated.")

    deactivate_exams.short_description = "Deactivate selected exams"

    def make_public(self, request, queryset):
        """Make exams public."""
        updated = queryset.update(is_public=True)
        self.message_user(request, f"{updated} exams made public.")

    make_public.short_description = "Make public"

    def make_private(self, request, queryset):
        """Make exams private."""
        updated = queryset.update(is_public=False)
        self.message_user(request, f"{updated} exams made private.")

    make_private.short_description = "Make private"

    def export_exam_data(self, request, queryset):
        """Export exam data to CSV."""
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="exams.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Title",
                "Type",
                "Questions",
                "Duration",
                "Attempts",
                "Avg Score",
                "Pass Rate",
                "Created By",
                "Created At",
            ]
        )

        for exam in queryset:
            sessions = ExamSession.objects.filter(exam=exam)
            pass_rate = 0
            if sessions.exists():
                passed = sessions.filter(is_passed=True).count()
                pass_rate = (passed / sessions.count()) * 100

            writer.writerow(
                [
                    exam.title,
                    exam.exam_type,
                    exam.total_questions,
                    exam.duration_minutes,
                    exam.total_attempts,
                    f"{exam.average_score:.2f}",
                    f"{pass_rate:.2f}",
                    exam.created_by.phone_number,
                    exam.created_at.strftime("%Y-%m-%d %H:%M"),
                ]
            )

        return response

    export_exam_data.short_description = "Export to CSV"

    def get_queryset(self, request):
        """Override queryset to add annotations."""
        qs = super().get_queryset(request)
        qs = qs.annotate(session_count=Count("sessions", distinct=True))
        return qs


@admin.register(ExamSession)
class ExamSessionAdmin(admin.ModelAdmin):
    """Admin for ExamSession model."""

    list_display = [
        "session_id_display",
        "exam",
        "user_display",
        "status_badge",
        "duration_minutes",
        "time_spent_display",
        "percentage_score_display",
        "is_passed_display",
        "started_at",
        "submitted_at",
    ]

    list_filter = [
        "status",
        "is_passed",
        "exam__exam_type",
        "started_at",
        "submitted_at",
    ]

    search_fields = [
        "exam__title",
        "user__phone_number",
        "user__first_name",
        "user__last_name",
        "ip_address",
    ]

    readonly_fields = [
        "id",
        "time_remaining_seconds",
        "is_time_up",
        "session_details",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (
            "Session Information",
            {"fields": ("id", "exam", "user", "status", "duration_minutes")},
        ),
        (
            "Session Timeline",
            {
                "fields": (
                    "started_at",
                    "ended_at",
                    "submitted_at",
                    "time_spent_seconds",
                    "time_remaining_seconds",
                    "is_time_up",
                )
            },
        ),
        (
            "Progress & Results",
            {
                "fields": (
                    "current_question_index",
                    "answers_submitted",
                    "total_score",
                    "percentage_score",
                    "is_passed",
                )
            },
        ),
        (
            "Security Information",
            {
                "fields": (
                    "ip_address",
                    "user_agent",
                    "tab_switches",
                    "suspicious_activity",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Session Data",
            {
                "fields": ("session_questions", "session_details"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    actions = ["force_submit", "reset_session", "export_results"]

    def session_id_display(self, obj):
        """Display session ID."""
        return format_html("<code>{}</code>", str(obj.id)[:8])

    session_id_display.short_description = "Session ID"

    def user_display(self, obj):
        """Display user with link."""
        url = reverse("admin:authentication_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.phone_number)

    user_display.short_description = "User"

    def status_badge(self, obj):
        """Display status as badge."""
        colors = {
            "not_started": "gray",
            "in_progress": "blue",
            "paused": "orange",
            "completed": "green",
            "auto_submitted": "purple",
            "abandoned": "red",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def time_spent_display(self, obj):
        """Display time spent in minutes."""
        if obj.time_spent_seconds:
            minutes = obj.time_spent_seconds // 60
            seconds = obj.time_spent_seconds % 60
            return f"{minutes}m {seconds}s"
        return "-"

    time_spent_display.short_description = "Time Spent"

    def percentage_score_display(self, obj):
        """Display percentage score with color."""
        if obj.percentage_score is not None:
            if obj.percentage_score >= 80:
                color = "green"
            elif obj.percentage_score >= 60:
                color = "orange"
            else:
                color = "red"
            return format_html(
                '<span style="color: {};">{:.2f}%</span>', color, obj.percentage_score
            )
        return "-"

    percentage_score_display.short_description = "Score"

    def is_passed_display(self, obj):
        """Display pass/fail status."""
        if obj.status in ["completed", "auto_submitted"]:
            if obj.is_passed:
                return format_html('<span style="color: green;">✓ Passed</span>')
            else:
                return format_html('<span style="color: red;">✗ Failed</span>')
        return "-"

    is_passed_display.short_description = "Result"

    def session_details(self, obj):
        """Display session details."""
        details = []
        details.append(
            f"Questions: {len(obj.session_questions) if obj.session_questions else 0}"
        )
        details.append(f"Answered: {obj.answers_submitted}")

        if obj.tab_switches > 0:
            details.append(f"Tab Switches: {obj.tab_switches}")

        if obj.suspicious_activity:
            details.append(f"Suspicious Activities: {len(obj.suspicious_activity)}")

        return format_html("<br>".join(details))

    session_details.short_description = "Session Details"

    def force_submit(self, request, queryset):
        """Force submit sessions."""
        for session in queryset.filter(status="in_progress"):
            session.submit_session(auto_submitted=True)
        self.message_user(request, f"Sessions force submitted.")

    force_submit.short_description = "Force submit sessions"

    def reset_session(self, request, queryset):
        """Reset sessions to not started."""
        queryset.update(
            status="not_started",
            started_at=None,
            ended_at=None,
            submitted_at=None,
            time_spent_seconds=0,
            answers_submitted=0,
            current_question_index=0,
        )
        self.message_user(request, f"Sessions reset.")

    reset_session.short_description = "Reset sessions"


@admin.register(ExamAnswer)
class ExamAnswerAdmin(admin.ModelAdmin):
    """Admin for ExamAnswer model."""

    list_display = [
        "id_short",
        "session_display",
        "question_display",
        "selected_option_display",
        "is_correct_display",
        "marks_awarded",
        "time_spent_seconds",
        "is_marked_for_review",
        "answered_at",
    ]

    list_filter = ["is_correct", "is_marked_for_review", "answered_at", "session__exam"]

    search_fields = [
        "session__user__phone_number",
        "question__question_text",
        "session__exam__title",
    ]

    readonly_fields = ["id", "created_at", "updated_at"]

    def id_short(self, obj):
        """Display short ID."""
        return str(obj.id)[:8]

    id_short.short_description = "ID"

    def session_display(self, obj):
        """Display session info."""
        return f"{obj.session.user.phone_number} - {obj.session.exam.title[:20]}"

    session_display.short_description = "Session"

    def question_display(self, obj):
        """Display question text truncated."""
        return obj.question.question_text[:50]

    question_display.short_description = "Question"

    def selected_option_display(self, obj):
        """Display selected option."""
        if obj.selected_option:
            return obj.selected_option.option_text[:30]
        return format_html('<span style="color: gray;">Not answered</span>')

    selected_option_display.short_description = "Selected Option"

    def is_correct_display(self, obj):
        """Display correct/incorrect status."""
        if obj.selected_option:
            if obj.is_correct:
                return format_html('<span style="color: green;">✓</span>')
            else:
                return format_html('<span style="color: red;">✗</span>')
        return "-"

    is_correct_display.short_description = "Correct"


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    """Admin for ExamQuestion model."""

    list_display = [
        "session_display",
        "question_number",
        "question_display",
        "time_spent_seconds",
        "visited_count",
    ]

    list_filter = ["session__exam", "visited_count"]

    search_fields = [
        "session__user__phone_number",
        "question__question_text",
        "session__exam__title",
    ]

    readonly_fields = ["id", "created_at", "updated_at"]

    def session_display(self, obj):
        """Display session info."""
        return f"{obj.session.user.phone_number} - {obj.session.exam.title[:30]}"

    session_display.short_description = "Session"

    def question_display(self, obj):
        """Display question text."""
        return obj.question.question_text[:50]

    question_display.short_description = "Question"
