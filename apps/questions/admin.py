from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Avg
from django.utils.safestring import mark_safe
from django.urls import reverse
from .models import Question, QuestionOption, QuestionTag, QuestionTagging


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 4  # Default 4 options for MCQ
    fields = ["option_order", "option_text", "option_image", "is_correct"]
    ordering = ["option_order"]

    def get_extra(self, request, obj=None, **kwargs):
        """Adjust extra options based on existing options"""
        if obj and obj.options.exists():
            return 0
        return 4


class QuestionTaggingInline(admin.TabularInline):
    model = QuestionTagging
    extra = 0
    verbose_name = "Tag"
    verbose_name_plural = "Tags"


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = [
        "question_preview",
        "chapter",
        "difficulty_badge",
        "marks",
        "options_count",
        "success_rate_display",
        "usage_stats",
        "is_active",
        "created_by",
        "created_at",
    ]
    list_filter = [
        "difficulty",
        "is_active",
        "allow_negative_marking",
        "chapter__subject",
        "chapter",
        "created_by",
        "marks",
        "created_at",
    ]
    search_fields = [
        "question_text",
        "explanation",
        "chapter__name",
        "chapter__subject__name",
        "tags__name",
    ]
    readonly_fields = [
        "created_at",
        "updated_at",
        "times_used",
        "correct_attempts",
        "total_attempts",
        "success_rate",
        "options_count",
    ]
    raw_id_fields = ["chapter", "created_by"]
    inlines = [QuestionOptionInline, QuestionTaggingInline]
    date_hierarchy = "created_at"

    fieldsets = (
        ("Question Information", {"fields": ("chapter", "created_by", "is_active")}),
        (
            "Question Content",
            {"fields": ("question_text", "question_image", "explanation")},
        ),
        (
            "Question Settings",
            {
                "fields": (
                    "difficulty",
                    "marks",
                    "negative_marks",
                    "allow_negative_marking",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "times_used",
                    "correct_attempts",
                    "total_attempts",
                    "success_rate",
                    "options_count",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    # Note: tags uses through model, so we use inline instead of filter_horizontal

    def get_queryset(self, request):
        """Optimize queryset with prefetch_related"""
        return (
            super()
            .get_queryset(request)
            .select_related("chapter", "chapter__subject", "created_by")
            .prefetch_related("options", "tags")
        )

    def question_preview(self, obj):
        """Show a preview of the question text"""
        preview = obj.question_text[:80]
        if len(obj.question_text) > 80:
            preview += "..."

        if obj.question_image:
            preview = f"📷 {preview}"

        return format_html(
            '<span title="{}">{}</span>',
            obj.question_text.replace('"', "&quot;"),
            preview,
        )

    question_preview.short_description = "Question Preview"

    def difficulty_badge(self, obj):
        colors = {
            "easy": "#28a745",
            "medium": "#ffc107",
            "hard": "#dc3545",
        }
        color = colors.get(obj.difficulty, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_difficulty_display().upper(),
        )

    difficulty_badge.short_description = "Difficulty"

    def success_rate_display(self, obj):
        rate = getattr(obj, "success_rate", None)

        # Coerce safely to a float
        try:
            rate_val = float(rate) if rate is not None else 0.0
        except (TypeError, ValueError):
            rate_val = 0.0

        if rate_val == 0:
            color = "#6c757d"
        elif rate_val < 30:
            color = "#dc3545"
        elif rate_val < 70:
            color = "#ffc107"
        else:
            color = "#28a745"

        rate_str = f"{rate_val:.1f}%"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', color, rate_str
        )

    success_rate_display.short_description = "Success Rate"

    def usage_stats(self, obj):
        if obj.total_attempts == 0:
            return format_html('<span style="color: #6c757d;">Not used</span>')

        return format_html(
            '<span title="Used {} times, {} correct out of {} attempts">{} / {}</span>',
            obj.times_used,
            obj.correct_attempts,
            obj.total_attempts,
            obj.correct_attempts,
            obj.total_attempts,
        )

    usage_stats.short_description = "Correct/Total"

    actions = [
        "activate_questions",
        "deactivate_questions",
        "reset_statistics",
        "duplicate_questions",
    ]

    def activate_questions(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} questions activated.")

    activate_questions.short_description = "Activate selected questions"

    def deactivate_questions(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} questions deactivated.")

    deactivate_questions.short_description = "Deactivate selected questions"

    def reset_statistics(self, request, queryset):
        updated = queryset.update(times_used=0, correct_attempts=0, total_attempts=0)
        self.message_user(request, f"Statistics reset for {updated} questions.")

    reset_statistics.short_description = "Reset statistics for selected questions"

    def duplicate_questions(self, request, queryset):
        count = 0
        for question in queryset:
            # Get original options and tags
            options = list(question.options.all())
            tags = list(question.tags.all())

            # Duplicate question
            question.pk = None
            question.question_text = f"Copy of {question.question_text}"
            question.times_used = 0
            question.correct_attempts = 0
            question.total_attempts = 0
            question.save()

            # Duplicate options
            for option in options:
                option.pk = None
                option.question = question
                option.save()

            # Add tags
            question.tags.set(tags)
            count += 1

        self.message_user(request, f"{count} questions duplicated.")

    duplicate_questions.short_description = "Duplicate selected questions"


@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):
    list_display = [
        "question_preview",
        "option_order",
        "option_preview",
        "is_correct_badge",
        "has_image",
        "created_at",
    ]
    list_filter = [
        "is_correct",
        "question__difficulty",
        "question__chapter",
        "created_at",
    ]
    search_fields = [
        "option_text",
        "question__question_text",
        "question__chapter__name",
    ]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["question"]
    ordering = ["question", "option_order"]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("question", "question__chapter")
        )

    def question_preview(self, obj):
        preview = obj.question.question_text[:50]
        if len(obj.question.question_text) > 50:
            preview += "..."
        return format_html(
            '<span title="{}">{}</span>',
            obj.question.question_text.replace('"', "&quot;"),
            preview,
        )

    question_preview.short_description = "Question"

    def option_preview(self, obj):
        preview = obj.option_text[:40]
        if len(obj.option_text) > 40:
            preview += "..."
        return format_html(
            '<span title="{}">{}</span>',
            obj.option_text.replace('"', "&quot;"),
            preview,
        )

    option_preview.short_description = "Option Text"

    def is_correct_badge(self, obj):
        if obj.is_correct:
            return format_html(
                '<span style="color: #28a745; font-weight: bold;">✓ Correct</span>'
            )
        else:
            return format_html('<span style="color: #6c757d;">○ Incorrect</span>')

    is_correct_badge.short_description = "Answer"

    def has_image(self, obj):
        return "📷" if obj.option_image else "📝"

    has_image.short_description = "Type"


@admin.register(QuestionTag)
class QuestionTagAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "color_preview",
        "questions_count",
        "description_preview",
        "created_at",
    ]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at", "questions_count"]

    fieldsets = (
        ("Tag Information", {"fields": ("name", "description", "color")}),
        ("Statistics", {"fields": ("questions_count",), "classes": ("collapse",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request).annotate(questions_count=Count("questions"))
        )

    def color_preview(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border: 1px solid #ccc; border-radius: 3px; display: inline-block;"></div> {}',
            obj.color,
            obj.color,
        )

    color_preview.short_description = "Color"

    def questions_count(self, obj):
        count = getattr(obj, "questions_count", 0)
        if count > 0:
            url = (
                reverse("admin:questions_question_changelist")
                + f"?tags__id__exact={obj.id}"
            )
            return format_html(
                '<a href="{}" style="text-decoration: none;">{} questions</a>',
                url,
                count,
            )
        return "0 questions"

    questions_count.short_description = "Usage"

    def description_preview(self, obj):
        if not obj.description:
            return "-"
        preview = obj.description[:50]
        if len(obj.description) > 50:
            preview += "..."
        return preview

    description_preview.short_description = "Description"


@admin.register(QuestionTagging)
class QuestionTaggingAdmin(admin.ModelAdmin):
    list_display = ["question_preview", "tag", "created_at"]
    list_filter = ["tag", "question__difficulty", "question__chapter"]
    search_fields = [
        "question__question_text",
        "tag__name",
        "question__chapter__name",
    ]
    raw_id_fields = ["question"]
    readonly_fields = ["created_at", "updated_at"]

    def question_preview(self, obj):
        preview = obj.question.question_text[:60]
        if len(obj.question.question_text) > 60:
            preview += "..."
        return format_html(
            '<span title="{}">{}</span>',
            obj.question.question_text.replace('"', "&quot;"),
            preview,
        )

    question_preview.short_description = "Question"


# Custom admin site configuration
admin.site.site_header = "Questions Administration"
admin.site.site_title = "Questions Admin"
admin.site.index_title = "Question Bank Management"


# Custom admin views for better organization
class QuestionAdminConfig(admin.ModelAdmin):
    """Custom configuration for question management"""

    def changelist_view(self, request, extra_context=None):
        # Add summary statistics to changelist
        extra_context = extra_context or {}

        # Get summary stats
        total_questions = Question.objects.count()
        active_questions = Question.objects.filter(is_active=True).count()

        # Difficulty distribution
        difficulty_stats = (
            Question.objects.values("difficulty")
            .annotate(count=Count("id"))
            .order_by("difficulty")
        )

        # Chapter distribution
        chapter_stats = (
            Question.objects.values("chapter__name", "chapter__subject__name")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        extra_context.update(
            {
                "total_questions": total_questions,
                "active_questions": active_questions,
                "difficulty_stats": difficulty_stats,
                "chapter_stats": chapter_stats,
            }
        )

        return super().changelist_view(request, extra_context)


# Apply custom config to QuestionAdmin
QuestionAdmin.__bases__ = (QuestionAdminConfig,) + QuestionAdmin.__bases__
