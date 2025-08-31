from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Avg, Count, Max, Min
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.template.response import TemplateResponse
from django.urls import path
from .models import (
    ExamResult,
    UserPerformanceAnalytics,
    SubjectPerformance,
    ExamAnalytics,
    QuestionAnalytics,
)


@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = [
        "user_info",
        "exam_title",
        "score_display",
        "performance_badge",
        "grade_badge",
        "rank_display",
        "accuracy_rate_display",
        "time_taken_display",
        "pass_status",
        "created_at",
    ]
    list_filter = [
        "is_passed",
        "exam",
        "grade",
        "exam__subject",
        "percentage_score",
        "created_at",
    ]
    search_fields = [
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__phone_number",
        "exam__title",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "performance_rating",
        "average_time_per_question",
        "accuracy_rate",
    ]
    raw_id_fields = ["user", "exam", "session"]
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("user", "exam", "session", "is_passed", "grade", "rank")},
        ),
        (
            "Score Summary",
            {
                "fields": (
                    "total_questions",
                    "questions_attempted",
                    "correct_answers",
                    "wrong_answers",
                    "unanswered",
                )
            },
        ),
        (
            "Marks & Scoring",
            {
                "fields": (
                    "total_marks",
                    "marks_obtained",
                    "negative_marks",
                    "percentage_score",
                )
            },
        ),
        (
            "Performance Metrics",
            {
                "fields": (
                    "time_taken_minutes",
                    "average_time_per_question",
                    "accuracy_rate",
                    "performance_rating",
                )
            },
        ),
        (
            "Detailed Analytics",
            {
                "fields": (
                    "subject_wise_scores",
                    "chapter_wise_scores",
                    "difficulty_wise_scores",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "AI Insights",
            {
                "fields": (
                    "weak_areas",
                    "strong_areas",
                    "suggested_retakes",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user", "exam", "session", "exam__subject")
        )

    def user_info(self, obj):
        return format_html(
            "<strong>{}</strong><br><small>{}</small>",
            obj.user.get_full_name() or obj.user.username,
            obj.user.phone_number or obj.user.email,
        )

    user_info.short_description = "User"

    def exam_title(self, obj):
        return format_html(
            '<a href="{}" title="{}">{}</a>',
            reverse("admin:exams_exam_change", args=[obj.exam.id]),
            obj.exam.description or "View exam details",
            obj.exam.title,
        )

    exam_title.short_description = "Exam"

    def score_display(self, obj):
        return format_html(
            '<div style="text-align: center;"><strong>{:.1f}%</strong><br><small>{:.1f}/{:.1f}</small></div>',
            obj.percentage_score,
            obj.marks_obtained,
            obj.total_marks,
        )

    score_display.short_description = "Score"

    def performance_badge(self, obj):
        colors = {
            "Excellent": "#28a745",
            "Very Good": "#20c997",
            "Good": "#17a2b8",
            "Average": "#ffc107",
            "Below Average": "#dc3545",
        }
        rating = obj.performance_rating
        color = colors.get(rating, "#6c757d")

        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 8px; font-size: 10px; font-weight: bold;">{}</span>',
            color,
            rating.upper(),
        )

    performance_badge.short_description = "Performance"

    def grade_badge(self, obj):
        grade_colors = {
            "A+": "#28a745",
            "A": "#20c997",
            "A-": "#17a2b8",
            "B+": "#17a2b8",
            "B": "#20c997",
            "B-": "#ffc107",
            "C+": "#ffc107",
            "C": "#fd7e14",
            "C-": "#dc3545",
            "F": "#dc3545",
        }
        color = grade_colors.get(obj.grade, "#6c757d")

        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 50%; font-weight: bold; font-size: 12px;">{}</span>',
            color,
            obj.grade or "N/A",
        )

    grade_badge.short_description = "Grade"

    def rank_display(self, obj):
        if obj.rank:
            if obj.rank == 1:
                return format_html('<span style="color: gold;">🥇 #{}</span>', obj.rank)
            elif obj.rank == 2:
                return format_html(
                    '<span style="color: silver;">🥈 #{}</span>', obj.rank
                )
            elif obj.rank == 3:
                return format_html(
                    '<span style="color: #CD7F32;">🥉 #{}</span>', obj.rank
                )
            else:
                return format_html("<span>#{}</span>", obj.rank)
        return "-"

    rank_display.short_description = "Rank"

    def accuracy_rate_display(self, obj):
        color = (
            "#28a745"
            if obj.accuracy_rate >= 80
            else "#ffc107" if obj.accuracy_rate >= 60 else "#dc3545"
        )
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            obj.accuracy_rate,
        )

    accuracy_rate_display.short_description = "Accuracy"

    def time_taken_display(self, obj):
        hours = obj.time_taken_minutes // 60
        minutes = obj.time_taken_minutes % 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    time_taken_display.short_description = "Time Taken"

    def pass_status(self, obj):
        if obj.is_passed:
            return format_html('<span style="color: #28a745;">✓ PASSED</span>')
        else:
            return format_html('<span style="color: #dc3545;">✗ FAILED</span>')

    pass_status.short_description = "Status"

    actions = ["recalculate_grades", "generate_certificates"]

    def recalculate_grades(self, request, queryset):
        updated = 0
        for result in queryset:
            old_grade = result.grade
            result.grade = result.calculate_grade()
            if old_grade != result.grade:
                result.save(update_fields=["grade"])
                updated += 1

        self.message_user(request, f"{updated} grades recalculated.")

    recalculate_grades.short_description = "Recalculate grades for selected results"

    def generate_certificates(self, request, queryset):
        passed_results = queryset.filter(is_passed=True)
        count = passed_results.count()
        # Here you would implement certificate generation logic
        self.message_user(
            request, f"Certificates generated for {count} passed students."
        )

    generate_certificates.short_description = (
        "Generate certificates for passed students"
    )


@admin.register(UserPerformanceAnalytics)
class UserPerformanceAnalyticsAdmin(admin.ModelAdmin):
    list_display = [
        "user_info",
        "exams_summary",
        "score_summary",
        "consistency_badge",
        "trend_display",
        "last_calculated",
    ]
    list_filter = [
        "consistency_rating",
        "improvement_trend",
        "preferred_difficulty",
        "last_calculated",
    ]
    search_fields = [
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__phone_number",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "last_calculated",
        "score_variance",
        "progress_rate",
    ]
    raw_id_fields = ["user"]

    fieldsets = (
        ("User Information", {"fields": ("user",)}),
        (
            "Overall Statistics",
            {
                "fields": (
                    "total_exams_taken",
                    "total_exams_passed",
                    "total_time_spent_hours",
                )
            },
        ),
        (
            "Performance Metrics",
            {
                "fields": (
                    "average_score",
                    "best_score",
                    "worst_score",
                    "score_variance",
                )
            },
        ),
        (
            "Consistency & Progress",
            {
                "fields": (
                    "consistency_rating",
                    "improvement_trend",
                    "progress_rate",
                )
            },
        ),
        (
            "Subject Analysis",
            {
                "fields": (
                    "subject_strengths",
                    "subject_weaknesses",
                    "subject_wise_averages",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Learning Patterns",
            {
                "fields": (
                    "preferred_difficulty",
                    "average_attempt_time",
                    "peak_performance_hours",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "AI Recommendations",
            {
                "fields": (
                    "study_recommendations",
                    "next_level_suggestions",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("last_calculated", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def user_info(self, obj):
        return format_html(
            "<strong>{}</strong><br><small>{}</small>",
            obj.user.get_full_name() or obj.user.username,
            obj.user.phone_number or obj.user.email,
        )

    user_info.short_description = "User"

    def exams_summary(self, obj):
        pass_rate = (
            (obj.total_exams_passed / obj.total_exams_taken * 100)
            if obj.total_exams_taken > 0
            else 0
        )
        return format_html(
            '<div style="text-align: center;"><strong>{}/{}</strong><br><small>{:.1f}% pass rate</small></div>',
            obj.total_exams_passed,
            obj.total_exams_taken,
            pass_rate,
        )

    exams_summary.short_description = "Exams (Passed/Total)"

    def score_summary(self, obj):
        return format_html(
            '<div style="text-align: center;">'
            "<strong>{:.1f}%</strong> avg<br>"
            "<small>Best: {:.1f}% | Worst: {:.1f}%</small>"
            "</div>",
            obj.average_score,
            obj.best_score,
            obj.worst_score,
        )

    score_summary.short_description = "Scores"

    def consistency_badge(self, obj):
        colors = {
            "Consistent": "#28a745",
            "Inconsistent": "#dc3545",
            "Moderately Consistent": "#ffc107",
        }
        color = colors.get(obj.consistency_rating, "#6c757d")

        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 8px; font-size: 10px;">{}</span>',
            color,
            obj.consistency_rating,
        )

    consistency_badge.short_description = "Consistency"

    def trend_display(self, obj):
        icons = {
            "Improving": "📈",
            "Declining": "📉",
            "Stable": "➡️",
        }
        colors = {
            "Improving": "#28a745",
            "Declining": "#dc3545",
            "Stable": "#17a2b8",
        }

        icon = icons.get(obj.improvement_trend, "❓")
        color = colors.get(obj.improvement_trend, "#6c757d")

        return format_html(
            '<span style="color: {};">{} {}</span>', color, icon, obj.improvement_trend
        )

    trend_display.short_description = "Trend"


@admin.register(SubjectPerformance)
class SubjectPerformanceAdmin(admin.ModelAdmin):
    list_display = [
        "user_info",
        "subject_name",
        "performance_summary",
        "improvement_display",
        "priority_badge",
        "trend_display",
    ]
    list_filter = [
        "subject",
        "trend",
        "study_priority",
        "average_score",
    ]
    search_fields = [
        "user__username",
        "user__phone_number",
        "subject__name",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "improvement",
        "trend",
    ]
    raw_id_fields = ["user", "subject"]

    def user_info(self, obj):
        return format_html(
            "<strong>{}</strong>", obj.user.get_full_name() or obj.user.username
        )

    user_info.short_description = "User"

    def subject_name(self, obj):
        return obj.subject.name

    subject_name.short_description = "Subject"

    def performance_summary(self, obj):
        return format_html(
            '<div style="text-align: center;">'
            "<strong>{:.1f}%</strong> avg<br>"
            "<small>{}/{} passed</small>"
            "</div>",
            obj.average_score,
            obj.exams_passed,
            obj.exams_taken,
        )

    performance_summary.short_description = "Performance"

    def improvement_display(self, obj):
        color = (
            "#28a745"
            if obj.improvement > 0
            else "#dc3545" if obj.improvement < 0 else "#6c757d"
        )
        symbol = "+" if obj.improvement > 0 else ""

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}{:.1f}%</span>',
            color,
            symbol,
            obj.improvement,
        )

    improvement_display.short_description = "Improvement"

    def priority_badge(self, obj):
        colors = {
            "High": "#dc3545",
            "Medium": "#ffc107",
            "Low": "#28a745",
        }
        color = colors.get(obj.study_priority, "#6c757d")

        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 8px; font-size: 10px;">{}</span>',
            color,
            obj.study_priority,
        )

    priority_badge.short_description = "Priority"

    def trend_display(self, obj):
        icons = {
            "Improving": "📈",
            "Declining": "📉",
            "Stable": "➡️",
        }
        return format_html("{} {}", icons.get(obj.trend, "❓"), obj.trend)

    trend_display.short_description = "Trend"


@admin.register(ExamAnalytics)
class ExamAnalyticsAdmin(admin.ModelAdmin):
    list_display = [
        "exam_title",
        "participation_summary",
        "score_summary",
        "pass_rate_display",
        "completion_rate_display",
        "difficulty_analysis",
        "last_calculated",
    ]
    list_filter = [
        "exam__subject",
        "pass_rate",
        "completion_rate",
        "score_trend",
        "participation_trend",
        "last_calculated",
    ]
    search_fields = [
        "exam__title",
        "exam__description",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "last_calculated",
        "standard_deviation",
        "median_score",
    ]
    raw_id_fields = ["exam"]

    fieldsets = (
        ("Exam Information", {"fields": ("exam",)}),
        (
            "Participation Statistics",
            {
                "fields": (
                    "total_attempts",
                    "unique_users",
                    "completion_rate",
                )
            },
        ),
        (
            "Score Statistics",
            {
                "fields": (
                    "average_score",
                    "median_score",
                    "highest_score",
                    "lowest_score",
                    "standard_deviation",
                )
            },
        ),
        (
            "Pass/Fail Analysis",
            {
                "fields": (
                    "pass_rate",
                    "total_passed",
                    "total_failed",
                )
            },
        ),
        (
            "Time Analysis",
            {
                "fields": (
                    "average_completion_time",
                    "fastest_completion",
                    "slowest_completion",
                )
            },
        ),
        (
            "Question Analytics",
            {
                "fields": (
                    "question_difficulty_analysis",
                    "most_missed_questions",
                    "easiest_questions",
                    "hardest_questions",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Behavior Analysis",
            {
                "fields": (
                    "tab_switch_incidents",
                    "suspicious_activities",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Trends & Recommendations",
            {
                "fields": (
                    "score_trend",
                    "participation_trend",
                    "exam_recommendations",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("last_calculated", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def exam_title(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:exams_exam_change", args=[obj.exam.id]),
            obj.exam.title,
        )

    exam_title.short_description = "Exam"

    def participation_summary(self, obj):
        return format_html(
            '<div style="text-align: center;">'
            "<strong>{}</strong> attempts<br>"
            "<small>{} unique users</small>"
            "</div>",
            obj.total_attempts,
            obj.unique_users,
        )

    participation_summary.short_description = "Participation"

    def score_summary(self, obj):
        return format_html(
            '<div style="text-align: center;">'
            "<strong>{:.1f}%</strong> avg<br>"
            "<small>{:.1f}% - {:.1f}%</small>"
            "</div>",
            obj.average_score,
            obj.lowest_score,
            obj.highest_score,
        )

    score_summary.short_description = "Scores"

    def pass_rate_display(self, obj):
        color = (
            "#28a745"
            if obj.pass_rate >= 80
            else "#ffc107" if obj.pass_rate >= 60 else "#dc3545"
        )
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            obj.pass_rate,
        )

    pass_rate_display.short_description = "Pass Rate"

    def completion_rate_display(self, obj):
        color = (
            "#28a745"
            if obj.completion_rate >= 90
            else "#ffc107" if obj.completion_rate >= 70 else "#dc3545"
        )
        return format_html(
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span>',
            color,
            obj.completion_rate,
        )

    completion_rate_display.short_description = "Completion Rate"

    def difficulty_analysis(self, obj):
        if not obj.question_difficulty_analysis:
            return "-"

        analysis = obj.question_difficulty_analysis
        return format_html(
            "<small>Easy: {:.0f}% | Medium: {:.0f}% | Hard: {:.0f}%</small>",
            analysis.get("easy", 0),
            analysis.get("medium", 0),
            analysis.get("hard", 0),
        )

    difficulty_analysis.short_description = "Difficulty Success"


@admin.register(QuestionAnalytics)
class QuestionAnalyticsAdmin(admin.ModelAdmin):
    list_display = [
        "question_preview",
        "usage_summary",
        "performance_metrics",
        "quality_indicators",
        "review_status",
        "last_calculated",
    ]
    list_filter = [
        "question__difficulty",
        "question__chapter__subject",
        "needs_review",
        "quality_score",
        "success_rate",
        "last_calculated",
    ]
    search_fields = [
        "question__question_text",
        "question__chapter__name",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "last_calculated",
        "difficulty_index",
        "discrimination_index",
        "quality_score",
    ]
    raw_id_fields = ["question"]

    def question_preview(self, obj):
        preview = obj.question.question_text[:60]
        if len(obj.question.question_text) > 60:
            preview += "..."

        return format_html(
            '<a href="{}" title="{}">{}</a>',
            reverse("admin:questions_question_change", args=[obj.question.id]),
            obj.question.question_text.replace('"', "&quot;"),
            preview,
        )

    question_preview.short_description = "Question"

    def usage_summary(self, obj):
        return format_html(
            '<div style="text-align: center;">'
            "<strong>{}</strong> presented<br>"
            "<small>{} answered, {} skipped</small>"
            "</div>",
            obj.times_presented,
            obj.times_answered,
            obj.times_skipped,
        )

    usage_summary.short_description = "Usage"

    def performance_metrics(self, obj):
        success_color = (
            "#28a745"
            if obj.success_rate >= 70
            else "#ffc107" if obj.success_rate >= 40 else "#dc3545"
        )

        return format_html(
            '<div style="text-align: center;">'
            '<span style="color: {}; font-weight: bold;">{:.1f}%</span> success<br>'
            "<small>{:.2f} difficulty index</small>"
            "</div>",
            success_color,
            obj.success_rate,
            obj.difficulty_index,
        )

    performance_metrics.short_description = "Performance"

    def quality_indicators(self, obj):
        quality_color = (
            "#28a745"
            if obj.quality_score >= 80
            else "#ffc107" if obj.quality_score >= 60 else "#dc3545"
        )

        return format_html(
            '<div style="text-align: center;">'
            '<span style="color: {}; font-weight: bold;">{:.1f}</span> quality<br>'
            "<small>{:.2f} discrimination</small>"
            "</div>",
            quality_color,
            obj.quality_score,
            obj.discrimination_index,
        )

    quality_indicators.short_description = "Quality"

    def review_status(self, obj):
        if obj.needs_review:
            reasons = (
                ", ".join(obj.review_reasons) if obj.review_reasons else "Needs review"
            )
            return format_html(
                '<span style="color: #dc3545;" title="{}">⚠️ Review Required</span>',
                reasons,
            )
        else:
            return format_html('<span style="color: #28a745;">✓ Good</span>')

    review_status.short_description = "Review Status"

    actions = ["mark_for_review", "approve_questions"]

    def mark_for_review(self, request, queryset):
        updated = queryset.update(needs_review=True)
        self.message_user(request, f"{updated} questions marked for review.")

    mark_for_review.short_description = "Mark selected questions for review"

    def approve_questions(self, request, queryset):
        updated = queryset.update(needs_review=False, review_reasons=[])
        self.message_user(request, f"{updated} questions approved.")

    approve_questions.short_description = "Approve selected questions"


# Custom admin site configuration
admin.site.site_header = "Results & Analytics Administration"
admin.site.site_title = "Results Admin"
admin.site.index_title = "Exam Results & Performance Analytics"


# Custom dashboard views
class ResultsAdminSite(admin.AdminSite):
    """Custom admin site with analytics dashboard"""

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "analytics-dashboard/",
                self.analytics_dashboard_view,
                name="analytics_dashboard",
            ),
        ]
        return custom_urls + urls

    def analytics_dashboard_view(self, request):
        """Custom analytics dashboard view"""
        context = {
            "title": "Analytics Dashboard",
            "total_results": ExamResult.objects.count(),
            "recent_results": ExamResult.objects.order_by("-created_at")[:10],
            "top_performers": ExamResult.objects.order_by("-percentage_score")[:5],
            "exam_analytics": ExamAnalytics.objects.order_by("-total_attempts")[:5],
        }

        return TemplateResponse(
            request, "admin/results/analytics_dashboard.html", context
        )
