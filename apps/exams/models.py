from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import timedelta
from apps.core.models import BaseModel
from apps.core.managers import SoftDeleteManager
from apps.subjects.models import Chapter
from apps.questions.models import Question
import uuid
import json

User = get_user_model()


class Exam(BaseModel):
    """
    Exam model for both scheduled and self-paced exams.
    """

    EXAM_TYPES = [
        ("self_paced", "Self Paced"),
        ("scheduled", "Scheduled"),
        ("practice", "Practice"),
    ]

    DIFFICULTY_LEVELS = [
        ("mixed", "Mixed"),
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    # Basic Information
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_exams"
    )

    # Exam Configuration
    exam_type = models.CharField(
        max_length=20, choices=EXAM_TYPES, default="self_paced"
    )
    chapters = models.ManyToManyField(Chapter, related_name="exams")

    # Question Settings
    total_questions = models.PositiveIntegerField(default=50)
    # Cached summaries for admin/reporting
    questions_per_chapter = models.JSONField(
        default=dict, blank=True
    )  # {chapter_id: count}
    difficulty_distribution = models.JSONField(
        default=dict, blank=True
    )  # {difficulty: percentage}
    randomize_questions = models.BooleanField(default=True)
    randomize_options = models.BooleanField(default=True)

    # Time Settings
    duration_minutes = models.PositiveIntegerField(default=50)
    time_per_question = models.FloatField(default=1.0)  # minutes per question
    allow_custom_duration = models.BooleanField(default=True)
    max_duration_minutes = models.PositiveIntegerField(default=180)  # 3 hours max

    # Scheduling (for scheduled exams)
    scheduled_start = models.DateTimeField(null=True, blank=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)

    # Scoring Settings
    marks_per_question = models.FloatField(default=1.0)
    negative_marking_enabled = models.BooleanField(default=True)
    negative_marks = models.FloatField(default=0.25)
    passing_percentage = models.FloatField(
        default=60.0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    # Exam Settings
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    requires_subscription = models.BooleanField(default=True)
    allow_retakes = models.BooleanField(default=True)
    max_attempts = models.PositiveIntegerField(default=0)  # 0 means unlimited

    # Auto-submit settings
    auto_submit_on_time_up = models.BooleanField(default=True)
    grace_period_seconds = models.PositiveIntegerField(default=30)

    # Analytics
    total_attempts = models.PositiveIntegerField(default=0)
    average_score = models.FloatField(default=0.0)

    objects = SoftDeleteManager()

    # Question Selection Method
    QUESTION_SELECTION_CHOICES = [
        ("random", "Random Selection"),
        ("manual", "Manual Selection"),
        ("mixed", "Mixed (Random + Manual)"),
    ]

    question_selection_method = models.CharField(
        max_length=10, choices=QUESTION_SELECTION_CHOICES, default="random"
    )

    # For manual selection - store selected question IDs
    selected_questions = models.JSONField(
        default=list, blank=True, help_text="List of manually selected question IDs"
    )

    # For mixed selection - how many random vs manual
    random_questions_count = models.PositiveIntegerField(
        default=0, help_text="Number of random questions when using mixed selection"
    )

    class Meta:
        db_table = "exams"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["exam_type", "is_active"]),
            models.Index(fields=["scheduled_start", "scheduled_end"]),
            models.Index(fields=["created_by"]),
            models.Index(fields=["is_public", "is_active"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_scheduled_active(self):
        """Check if scheduled exam is currently active."""
        if self.exam_type != "scheduled":
            return False
        if not self.scheduled_start or not self.scheduled_end:
            return False
        now = timezone.now()
        return self.scheduled_start <= now <= self.scheduled_end

    @property
    def can_start_now(self):
        """Check if exam can be started now."""
        if not self.is_active:
            return False
        if self.exam_type == "scheduled":
            return self.is_scheduled_active
        return True

    # ---------- SINGLE canonical implementation ----------
    def get_questions(self, user=None):
        """
        Resolve the concrete list of questions this exam should use,
        honoring the selection method and randomization options.
        """
        # Manual -> strictly what the teacher picked
        if self.question_selection_method == "manual":
            qs = (
                Question.objects.filter(id__in=self.selected_questions, is_active=True)
                .select_related("chapter")
                .prefetch_related("options")
            )

            # maintain teacher's order, then optionally shuffle
            q_map = {str(q.id): q for q in qs}
            ordered = [q_map[qid] for qid in self.selected_questions if qid in q_map]

            if self.randomize_questions:
                import random

                random.shuffle(ordered)

            return ordered[: self.total_questions]

        # Mixed -> some manual, some random from the chosen chapters
        if self.question_selection_method == "mixed":
            manual = list(
                Question.objects.filter(id__in=self.selected_questions, is_active=True)
                .select_related("chapter")
                .prefetch_related("options")
            )

            random_needed = max(0, self.total_questions - len(manual))
            if self.random_questions_count:
                random_needed = self.random_questions_count

            random_pool = (
                Question.objects.filter(chapter__in=self.chapters.all(), is_active=True)
                .exclude(id__in=self.selected_questions)
                .order_by("?")[:random_needed]
                .select_related("chapter")
                .prefetch_related("options")
            )

            combined = manual + list(random_pool)
            if self.randomize_questions:
                import random

                random.shuffle(combined)

            return combined[: self.total_questions]

        # Random -> sample from chapters
        qs = (
            Question.objects.filter(chapter__in=self.chapters.all(), is_active=True)
            .select_related("chapter")
            .prefetch_related("options")
        )
        if self.randomize_questions:
            qs = qs.order_by("?")
        return list(qs[: self.total_questions])


class ExamSession(BaseModel):
    """
    Individual exam session for a user.
    """

    SESSION_STATUS = [
        ("not_started", "Not Started"),
        ("in_progress", "In Progress"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("auto_submitted", "Auto Submitted"),
        ("abandoned", "Abandoned"),
    ]

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sessions")
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="exam_sessions"
    )

    # Session Configuration
    session_questions = models.JSONField(default=list)  # List of question IDs in order
    duration_minutes = models.PositiveIntegerField()

    # Session State
    status = models.CharField(
        max_length=20, choices=SESSION_STATUS, default="not_started"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    # Progress Tracking
    current_question_index = models.PositiveIntegerField(default=0)
    answers_submitted = models.PositiveIntegerField(default=0)
    time_spent_seconds = models.PositiveIntegerField(default=0)

    # Session Security
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    tab_switches = models.PositiveIntegerField(default=0)
    suspicious_activity = models.JSONField(default=list)

    # Final Results
    total_score = models.FloatField(default=0.0)
    percentage_score = models.FloatField(default=0.0)
    is_passed = models.BooleanField(default=False)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "exam_sessions"
        ordering = ["-created_at"]
        unique_together = ["exam", "user", "created_at"]  # Prevent duplicate sessions
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["exam", "status"]),
            models.Index(fields=["started_at", "ended_at"]),
        ]

    def __str__(self):
        return f"{self.user.phone_number} - {self.exam.title}"

    @property
    def time_remaining_seconds(self):
        """Get remaining time in seconds."""
        if not self.started_at or self.status in ["completed", "auto_submitted"]:
            return 0

        elapsed = (timezone.now() - self.started_at).total_seconds()
        total_time = self.duration_minutes * 60
        return max(0, int(total_time - elapsed))

    @property
    def is_time_up(self):
        """Check if time is up."""
        return self.time_remaining_seconds <= 0

    def start_session(self):
        """Start the exam session."""
        if self.status != "not_started":
            return False

        self.status = "in_progress"
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])
        return True

    def submit_session(self, auto_submitted=False):
        """Submit the exam session."""
        if self.status not in ["in_progress", "paused"]:
            return False

        self.status = "auto_submitted" if auto_submitted else "completed"
        self.ended_at = timezone.now()
        self.submitted_at = timezone.now()

        if self.started_at:
            self.time_spent_seconds = int(
                (self.ended_at - self.started_at).total_seconds()
            )

        self.save(
            update_fields=["status", "ended_at", "submitted_at", "time_spent_seconds"]
        )

        # Trigger score calculation
        from .tasks import calculate_session_score

        calculate_session_score.delay(self.id)

        return True


class ExamAnswer(BaseModel):
    """
    User answers for exam questions.
    """

    session = models.ForeignKey(
        ExamSession, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.ForeignKey(
        "questions.QuestionOption", on_delete=models.CASCADE, null=True, blank=True
    )

    # Answer metadata
    is_correct = models.BooleanField(default=False)
    marks_awarded = models.FloatField(default=0.0)
    time_spent_seconds = models.PositiveIntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)

    # Answer tracking
    is_marked_for_review = models.BooleanField(default=False)
    answer_sequence = models.PositiveIntegerField(default=0)  # Order in which answered

    objects = SoftDeleteManager()

    class Meta:
        db_table = "exam_answers"
        ordering = ["session", "question"]
        unique_together = ["session", "question"]
        indexes = [
            models.Index(fields=["session", "question"]),
            models.Index(fields=["is_correct"]),
            models.Index(fields=["answered_at"]),
        ]

    def __str__(self):
        return f"{self.session.user.phone_number} - Q{self.question.id}"


class ExamQuestion(BaseModel):
    """
    Questions assigned to specific exam sessions (for tracking and analytics).
    """

    session = models.ForeignKey(
        ExamSession, on_delete=models.CASCADE, related_name="exam_questions"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE)

    # Question order and configuration
    question_number = models.PositiveIntegerField()
    options_order = models.JSONField(default=list)  # Randomized option order

    # Analytics
    time_spent_seconds = models.PositiveIntegerField(default=0)
    visited_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "exam_questions"
        ordering = ["session", "question_number"]
        unique_together = ["session", "question_number"]
        indexes = [
            models.Index(fields=["session", "question_number"]),
        ]

    def __str__(self):
        return f"Session {self.session.id} - Q{self.question_number}"


class QuestionSet(BaseModel):
    """
    Reusable question sets for exams.
    """
    name = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_question_sets"
    )
    
    # Store question references
    questions = models.JSONField(default=list)  # List of question IDs
    
    # Metadata
    total_questions = models.PositiveIntegerField(default=0)
    chapters = models.ManyToManyField(Chapter, related_name="question_sets")
    
    # Usage tracking
    usage_count = models.PositiveIntegerField(default=0)
    last_used_at = models.DateTimeField(null=True, blank=True)
    
    # Settings from original exam
    difficulty_distribution = models.JSONField(default=dict, blank=True)
    
    is_active = models.BooleanField(default=True)
    
    objects = SoftDeleteManager()
    
    class Meta:
        db_table = "question_sets"
        ordering = ["-usage_count", "-created_at"]
        indexes = [
            models.Index(fields=["created_by", "is_active"]),
            models.Index(fields=["usage_count"]),
            models.Index(fields=["-created_at"]),
        ]
    
    def __str__(self):
        return self.name or f"Question Set {self.id}"
    
    def increment_usage(self):
        """Increment usage count."""
        self.usage_count = models.F("usage_count") + 1
        self.last_used_at = timezone.now()
        self.save(update_fields=["usage_count", "last_used_at"])