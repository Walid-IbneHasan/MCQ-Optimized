from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator, MaxValueValidator
from apps.core.models import BaseModel
from apps.core.managers import SoftDeleteManager
from apps.subjects.models import Chapter
import uuid

User = get_user_model()


class Question(BaseModel):
    """
    MCQ questions.
    """

    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    chapter = models.ForeignKey(
        Chapter, on_delete=models.CASCADE, related_name="questions"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_questions"
    )

    # Question content
    question_text = models.TextField()
    question_image = models.ImageField(upload_to="questions/", blank=True, null=True)
    explanation = models.TextField(
        blank=True, help_text="Explanation for the correct answer"
    )

    # Question metadata
    difficulty = models.CharField(
        max_length=10, choices=DIFFICULTY_CHOICES, default="medium"
    )
    marks = models.FloatField(
        default=1.0, validators=[MinValueValidator(0.1), MaxValueValidator(10.0)]
    )
    negative_marks = models.FloatField(
        default=0.25, validators=[MinValueValidator(0.0), MaxValueValidator(5.0)]
    )

    # Question settings
    is_active = models.BooleanField(default=True)
    allow_negative_marking = models.BooleanField(default=True)

    # Question statistics
    times_used = models.PositiveIntegerField(default=0)
    correct_attempts = models.PositiveIntegerField(default=0)
    total_attempts = models.PositiveIntegerField(default=0)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "questions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["chapter", "is_active"]),
            models.Index(fields=["difficulty"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["times_used"]),
        ]

    def __str__(self):
        return f"Q{self.chapter.chapter_number}.{self.id}: {self.question_text[:50]}..."

    @property
    def success_rate(self):
        """Calculate question success rate."""
        if self.total_attempts == 0:
            return 0
        return (self.correct_attempts / self.total_attempts) * 100

    @property
    def options_count(self):
        """Get number of options for this question."""
        return self.options.count()


class QuestionOption(BaseModel):
    """
    Options for MCQ questions.
    """

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="options"
    )

    # Option content
    option_text = models.TextField()
    option_image = models.ImageField(
        upload_to="question_options/", blank=True, null=True
    )

    # Option settings
    is_correct = models.BooleanField(default=False)
    option_order = models.PositiveIntegerField()

    objects = SoftDeleteManager()

    class Meta:
        db_table = "question_options"
        ordering = ["question", "option_order"]
        unique_together = ["question", "option_order"]
        indexes = [
            models.Index(fields=["question", "option_order"]),
            models.Index(fields=["is_correct"]),
        ]

    def __str__(self):
        return f"Option {self.option_order}: {self.option_text[:30]}..."


class QuestionTag(BaseModel):
    """
    Tags for questions to improve searchability.
    """

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default="#007bff")  # Hex color

    objects = SoftDeleteManager()

    class Meta:
        db_table = "question_tags"
        ordering = ["name"]

    def __str__(self):
        return self.name


class QuestionTagging(BaseModel):
    """
    Many-to-many relationship between questions and tags.
    """

    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    tag = models.ForeignKey(QuestionTag, on_delete=models.CASCADE)

    class Meta:
        db_table = "question_tagging"
        unique_together = ["question", "tag"]


# Add tags relationship to Question model
Question.add_to_class(
    "tags",
    models.ManyToManyField(
        QuestionTag, through=QuestionTagging, related_name="questions", blank=True
    ),
)
