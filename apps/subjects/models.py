from django.db import models
from django.contrib.auth import get_user_model
from apps.core.models import BaseModel
from apps.core.managers import SoftDeleteManager

User = get_user_model()

class Subject(BaseModel):
    """
    Academic subjects.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    code = models.CharField(max_length=20, unique=True)  # e.g., MATH101, PHY201
    
    # Subject metadata
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    
    # Subject image/icon
    image = models.ImageField(upload_to='subjects/', blank=True, null=True)
    
    objects = SoftDeleteManager()
    
    class Meta:
        db_table = 'subjects'
        ordering = ['sort_order', 'name']
        indexes = [
            models.Index(fields=['is_active', 'sort_order']),
            models.Index(fields=['code']),
        ]
    
    def __str__(self):
        return self.name
    
    @property
    def chapters_count(self):
        """Get total chapters count."""
        return self.chapters.filter(is_active=True).count()
    
    @property
    def questions_count(self):
        """Get total questions count."""
        from apps.questions.models import Question
        return Question.objects.filter(chapter__subject=self).count()

class Chapter(BaseModel):
    """
    Subject chapters.
    """
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='chapters')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    chapter_number = models.PositiveIntegerField()
    
    # Chapter settings
    is_active = models.BooleanField(default=True)
    difficulty_level = models.CharField(
        max_length=20,
        choices=[
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
        ],
        default='beginner'
    )
    
    # Chapter content
    content = models.TextField(blank=True, help_text="Chapter content/description")
    
    objects = SoftDeleteManager()
    
    class Meta:
        db_table = 'chapters'
        ordering = ['subject', 'chapter_number']
        unique_together = ['subject', 'chapter_number']
        indexes = [
            models.Index(fields=['subject', 'is_active']),
            models.Index(fields=['chapter_number']),
            models.Index(fields=['difficulty_level']),
        ]
    
    def __str__(self):
        return f"{self.subject.name} - Chapter {self.chapter_number}: {self.name}"
    
    @property
    def questions_count(self):
        """Get questions count for this chapter."""
        return self.questions.filter(is_active=True).count()
    
    @property
    def exams_count(self):
        """Get exams count for this chapter."""
        from apps.exams.models import Exam
        return Exam.objects.filter(chapters=self, is_active=True).count()