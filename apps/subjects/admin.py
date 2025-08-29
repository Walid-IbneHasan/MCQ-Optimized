from django.contrib import admin
from .models import Subject, Chapter


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    """
    Admin for subjects.
    """

    list_display = [
        "name",
        "code",
        "is_active",
        "sort_order",
        "chapters_count",
        "created_at",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "code", "description"]
    ordering = ["sort_order", "name"]
    prepopulated_fields = {"code": ("name",)}

    fieldsets = (
        ("Basic Information", {"fields": ("name", "code", "description", "image")}),
        ("Settings", {"fields": ("is_active", "sort_order")}),
    )


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    """
    Admin for chapters.
    """

    list_display = [
        "name",
        "subject",
        "chapter_number",
        "difficulty_level",
        "is_active",
        "questions_count",
        "created_at",
    ]
    list_filter = ["subject", "difficulty_level", "is_active", "created_at"]
    search_fields = ["name", "description", "subject__name"]
    ordering = ["subject", "chapter_number"]
    raw_id_fields = ["subject"]

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("subject", "name", "chapter_number", "description")},
        ),
        ("Settings", {"fields": ("is_active", "difficulty_level")}),
        ("Content", {"fields": ("content",)}),
    )
