from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from apps.core.models import BaseModel
from apps.core.managers import SoftDeleteManager
from apps.subjects.models import Subject, Chapter
from apps.exams.models import Exam

User = get_user_model()


class LeaderboardType(BaseModel):
    """
    Different types of leaderboards available in the system.
    """

    LEADERBOARD_SCOPES = [
        ("global", "Global"),
        ("subject", "Subject-wise"),
        ("chapter", "Chapter-wise"),
        ("exam", "Exam-specific"),
    ]

    LEADERBOARD_PERIODS = [
        ("all_time", "All Time"),
        ("yearly", "Yearly"),
        ("monthly", "Monthly"),
        ("weekly", "Weekly"),
        ("daily", "Daily"),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    scope = models.CharField(max_length=20, choices=LEADERBOARD_SCOPES)
    period = models.CharField(max_length=20, choices=LEADERBOARD_PERIODS)

    # Leaderboard configuration
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    max_entries = models.PositiveIntegerField(default=100)

    # Scoring configuration
    score_calculation_method = models.CharField(
        max_length=20,
        choices=[
            ("average", "Average Score"),
            ("best", "Best Score"),
            ("total", "Total Points"),
            ("weighted", "Weighted Score"),
        ],
        default="average",
    )

    # Filtering criteria
    min_exams_required = models.PositiveIntegerField(default=1)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "leaderboard_types"
        unique_together = ["scope", "period", "name"]
        indexes = [
            models.Index(fields=["scope", "period"]),
            models.Index(fields=["is_active", "is_public"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_scope_display()} - {self.get_period_display()})"


class Leaderboard(BaseModel):
    """
    Actual leaderboard instances with calculated rankings.
    """

    leaderboard_type = models.ForeignKey(
        LeaderboardType, on_delete=models.CASCADE, related_name="leaderboards"
    )

    # Optional filters for specific leaderboards
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, null=True, blank=True
    )
    chapter = models.ForeignKey(
        Chapter, on_delete=models.CASCADE, null=True, blank=True
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, null=True, blank=True)

    # Time period for this leaderboard instance
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    # Leaderboard metadata
    total_participants = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    is_finalized = models.BooleanField(default=False)  # For completed periods

    # Cached leaderboard data for performance
    leaderboard_data = models.JSONField(default=list)  # Cached rankings

    objects = SoftDeleteManager()

    class Meta:
        db_table = "leaderboards"
        ordering = ["-period_end", "-total_participants"]
        indexes = [
            models.Index(fields=["leaderboard_type", "period_start", "period_end"]),
            models.Index(fields=["subject", "period_start"]),
            models.Index(fields=["chapter", "period_start"]),
            models.Index(fields=["exam"]),
        ]

    def __str__(self):
        filter_info = ""
        if self.subject:
            filter_info = f" - {self.subject.name}"
        elif self.chapter:
            filter_info = f" - {self.chapter.name}"
        elif self.exam:
            filter_info = f" - {self.exam.title}"

        return f"{self.leaderboard_type.name}{filter_info} ({self.period_start.date()} to {self.period_end.date()})"

    @property
    def is_current_period(self):
        """Check if this leaderboard is for the current time period."""
        now = timezone.now()
        return self.period_start <= now <= self.period_end

    def get_user_rank(self, user):
        """Get a specific user's rank in this leaderboard."""
        for idx, entry in enumerate(self.leaderboard_data, 1):
            if entry.get("user_id") == str(user.id):
                return idx
        return None


class LeaderboardEntry(BaseModel):
    """
    Individual entries in leaderboards with detailed user performance.
    """

    leaderboard = models.ForeignKey(
        Leaderboard, on_delete=models.CASCADE, related_name="entries"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="leaderboard_entries"
    )

    # Ranking information
    rank = models.PositiveIntegerField()
    previous_rank = models.PositiveIntegerField(null=True, blank=True)
    rank_change = models.IntegerField(
        default=0
    )  # Positive for improvement, negative for decline

    # Performance metrics
    score = models.FloatField()  # Calculated based on leaderboard type
    total_exams = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)

    # Additional metrics
    average_score = models.FloatField(default=0.0)
    best_score = models.FloatField(default=0.0)
    total_time_minutes = models.PositiveIntegerField(default=0)
    consistency_score = models.FloatField(default=0.0)  # Measure of consistency

    # Performance trends
    improvement_rate = models.FloatField(default=0.0)
    performance_trend = models.CharField(
        max_length=20,
        choices=[
            ("improving", "Improving"),
            ("declining", "Declining"),
            ("stable", "Stable"),
            ("new", "New User"),
        ],
        default="new",
    )

    # Achievements and badges (stored as JSON for flexibility)
    achievements = models.JSONField(default=list)
    badges = models.JSONField(default=list)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "leaderboard_entries"
        ordering = ["rank"]
        unique_together = ["leaderboard", "user"]
        indexes = [
            models.Index(fields=["leaderboard", "rank"]),
            models.Index(fields=["user", "rank"]),
            models.Index(fields=["score"]),
        ]

    def __str__(self):
        return f"#{self.rank} - {self.user.full_name} ({self.score})"

    @property
    def accuracy_rate(self):
        """Calculate accuracy rate."""
        if self.total_questions == 0:
            return 0.0
        return (self.correct_answers / self.total_questions) * 100


class LeaderboardSubscription(BaseModel):
    """
    User subscriptions to leaderboard notifications and updates.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="leaderboard_subscriptions"
    )
    leaderboard_type = models.ForeignKey(LeaderboardType, on_delete=models.CASCADE)

    # Optional filters
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, null=True, blank=True
    )
    chapter = models.ForeignKey(
        Chapter, on_delete=models.CASCADE, null=True, blank=True
    )

    # Notification preferences
    notify_on_rank_change = models.BooleanField(default=True)
    notify_on_new_achievements = models.BooleanField(default=True)
    notify_on_period_end = models.BooleanField(default=True)

    # Notification methods
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)

    is_active = models.BooleanField(default=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "leaderboard_subscriptions"
        unique_together = ["user", "leaderboard_type", "subject", "chapter"]

    def __str__(self):
        return f"{self.user.full_name} - {self.leaderboard_type.name}"
