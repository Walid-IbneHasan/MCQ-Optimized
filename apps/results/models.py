from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.core.models import BaseModel
from apps.core.managers import SoftDeleteManager
from apps.exams.models import Exam, ExamSession
from apps.subjects.models import Subject, Chapter
from apps.questions.models import Question

User = get_user_model()


class ExamResult(BaseModel):
    """
    Consolidated exam results for easy querying and analytics.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="exam_results"
    )
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="results")
    session = models.OneToOneField(
        ExamSession, on_delete=models.CASCADE, related_name="result"
    )

    # Score Information
    total_questions = models.PositiveIntegerField()
    questions_attempted = models.PositiveIntegerField()
    correct_answers = models.PositiveIntegerField()
    wrong_answers = models.PositiveIntegerField()
    unanswered = models.PositiveIntegerField()

    # Scoring
    total_marks = models.FloatField()
    marks_obtained = models.FloatField()
    negative_marks = models.FloatField(default=0.0)
    percentage_score = models.FloatField()

    # Result Status
    is_passed = models.BooleanField()
    grade = models.CharField(max_length=5, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)

    # Performance Metrics
    time_taken_minutes = models.PositiveIntegerField()
    average_time_per_question = models.FloatField()
    accuracy_rate = (
        models.FloatField()
    )  # Percentage of attempted questions answered correctly

    # Subject-wise Performance (JSON field for flexibility)
    subject_wise_scores = models.JSONField(default=dict)
    chapter_wise_scores = models.JSONField(default=dict)
    difficulty_wise_scores = models.JSONField(default=dict)

    # Suggestions and Analytics
    weak_areas = models.JSONField(
        default=list
    )  # List of subjects/chapters where performance was poor
    strong_areas = models.JSONField(
        default=list
    )  # List of subjects/chapters where performance was good
    suggested_retakes = models.JSONField(default=list)  # Suggested chapters for retake

    objects = SoftDeleteManager()

    class Meta:
        db_table = "exam_results"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "exam"]),
            models.Index(fields=["exam", "percentage_score"]),
            models.Index(fields=["user", "percentage_score"]),
            models.Index(fields=["is_passed"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return (
            f"{self.user.phone_number} - {self.exam.title} ({self.percentage_score}%)"
        )

    @property
    def performance_rating(self):
        """Get performance rating based on percentage."""
        if self.percentage_score >= 90:
            return "Excellent"
        elif self.percentage_score >= 80:
            return "Very Good"
        elif self.percentage_score >= 70:
            return "Good"
        elif self.percentage_score >= 60:
            return "Average"
        else:
            return "Below Average"

    def calculate_grade(self):
        """Calculate grade based on percentage score."""
        if self.percentage_score >= 90:
            return "A+"
        elif self.percentage_score >= 85:
            return "A"
        elif self.percentage_score >= 80:
            return "A-"
        elif self.percentage_score >= 75:
            return "B+"
        elif self.percentage_score >= 70:
            return "B"
        elif self.percentage_score >= 65:
            return "B-"
        elif self.percentage_score >= 60:
            return "C+"
        elif self.percentage_score >= 55:
            return "C"
        elif self.percentage_score >= 50:
            return "C-"
        else:
            return "F"


class UserPerformanceAnalytics(BaseModel):
    """
    User performance analytics and insights.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="performance_analytics"
    )

    # Overall Statistics
    total_exams_taken = models.PositiveIntegerField(default=0)
    total_exams_passed = models.PositiveIntegerField(default=0)
    total_time_spent_hours = models.FloatField(default=0.0)

    # Average Performance
    average_score = models.FloatField(default=0.0)
    best_score = models.FloatField(default=0.0)
    worst_score = models.FloatField(default=0.0)

    # Consistency Metrics
    score_variance = models.FloatField(default=0.0)
    consistency_rating = models.CharField(
        max_length=20, default="Unknown"
    )  # Consistent, Inconsistent, etc.

    # Subject Performance
    subject_strengths = models.JSONField(default=list)  # Top performing subjects
    subject_weaknesses = models.JSONField(default=list)  # Poor performing subjects
    subject_wise_averages = models.JSONField(default=dict)  # Average scores per subject

    # Progress Tracking
    improvement_trend = models.CharField(
        max_length=20, default="Unknown"
    )  # Improving, Declining, Stable
    progress_rate = models.FloatField(default=0.0)  # Rate of improvement/decline

    # Learning Patterns
    preferred_difficulty = models.CharField(max_length=10, default="medium")
    average_attempt_time = models.FloatField(default=0.0)
    peak_performance_hours = models.JSONField(
        default=list
    )  # Hours when user performs best

    # Recommendations
    study_recommendations = models.JSONField(default=list)
    next_level_suggestions = models.JSONField(default=list)

    # Last updated
    last_calculated = models.DateTimeField(auto_now=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "user_performance_analytics"

    def __str__(self):
        return f"{self.user.phone_number} - Analytics"


class SubjectPerformance(BaseModel):
    """
    User performance in specific subjects.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="subject_performances"
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="user_performances"
    )

    # Performance Metrics
    exams_taken = models.PositiveIntegerField(default=0)
    exams_passed = models.PositiveIntegerField(default=0)
    average_score = models.FloatField(default=0.0)
    best_score = models.FloatField(default=0.0)
    latest_score = models.FloatField(default=0.0)

    # Progress Tracking
    first_attempt_score = models.FloatField(default=0.0)
    improvement = models.FloatField(default=0.0)  # Improvement from first to latest
    trend = models.CharField(
        max_length=20, default="Unknown"
    )  # Improving, Declining, Stable

    # Chapter Performance
    chapter_scores = models.JSONField(default=dict)  # {chapter_id: average_score}
    weak_chapters = models.JSONField(default=list)
    strong_chapters = models.JSONField(default=list)

    # Difficulty Analysis
    difficulty_performance = models.JSONField(
        default=dict
    )  # {difficulty: average_score}

    # Time Analysis
    average_time_per_exam = models.FloatField(default=0.0)
    total_time_spent = models.FloatField(default=0.0)

    # Recommendations
    recommended_chapters = models.JSONField(default=list)
    study_priority = models.CharField(
        max_length=20, default="Medium"
    )  # High, Medium, Low

    objects = SoftDeleteManager()

    class Meta:
        db_table = "subject_performances"
        unique_together = ["user", "subject"]
        indexes = [
            models.Index(fields=["user", "average_score"]),
            models.Index(fields=["subject", "average_score"]),
        ]

    def __str__(self):
        return f"{self.user.phone_number} - {self.subject.name} ({self.average_score}%)"


class ExamAnalytics(BaseModel):
    """
    Analytics for individual exams.
    """

    exam = models.OneToOneField(
        Exam, on_delete=models.CASCADE, related_name="analytics"
    )

    # Participation Statistics
    total_attempts = models.PositiveIntegerField(default=0)
    unique_users = models.PositiveIntegerField(default=0)
    completion_rate = models.FloatField(
        default=0.0
    )  # Percentage of started exams completed

    # Score Statistics
    average_score = models.FloatField(default=0.0)
    median_score = models.FloatField(default=0.0)
    highest_score = models.FloatField(default=0.0)
    lowest_score = models.FloatField(default=0.0)
    standard_deviation = models.FloatField(default=0.0)

    # Pass/Fail Statistics
    pass_rate = models.FloatField(default=0.0)
    total_passed = models.PositiveIntegerField(default=0)
    total_failed = models.PositiveIntegerField(default=0)

    # Time Statistics
    average_completion_time = models.FloatField(default=0.0)  # in minutes
    fastest_completion = models.FloatField(default=0.0)
    slowest_completion = models.FloatField(default=0.0)

    # Question Analysis
    question_difficulty_analysis = models.JSONField(default=dict)
    most_missed_questions = models.JSONField(default=list)
    easiest_questions = models.JSONField(
        default=list
    )  # Questions with highest success rate
    hardest_questions = models.JSONField(
        default=list
    )  # Questions with lowest success rate

    # User Behavior
    tab_switch_incidents = models.PositiveIntegerField(default=0)
    suspicious_activities = models.PositiveIntegerField(default=0)

    # Trends
    score_trend = models.CharField(
        max_length=20, default="Stable"
    )  # Improving, Declining, Stable
    participation_trend = models.CharField(max_length=20, default="Stable")

    # Recommendations for Improvement
    exam_recommendations = models.JSONField(default=list)

    # Last updated
    last_calculated = models.DateTimeField(auto_now=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "exam_analytics"

    def __str__(self):
        return f"Analytics: {self.exam.title}"


class QuestionAnalytics(BaseModel):
    """
    Analytics for individual questions.
    """

    question = models.OneToOneField(
        Question, on_delete=models.CASCADE, related_name="analytics"
    )

    # Usage Statistics
    times_presented = models.PositiveIntegerField(default=0)
    times_answered = models.PositiveIntegerField(default=0)
    times_correct = models.PositiveIntegerField(default=0)
    times_skipped = models.PositiveIntegerField(default=0)

    # Performance Metrics
    success_rate = models.FloatField(default=0.0)  # Percentage of correct answers
    difficulty_index = models.FloatField(
        default=0.0
    )  # Calculated difficulty based on performance
    discrimination_index = models.FloatField(
        default=0.0
    )  # How well question discriminates ability levels

    # Time Analysis
    average_time_spent = models.FloatField(default=0.0)  # seconds
    fastest_correct_time = models.FloatField(default=0.0)
    slowest_correct_time = models.FloatField(default=0.0)

    # Option Analysis
    option_selection_stats = models.JSONField(
        default=dict
    )  # How often each option is selected
    distractor_effectiveness = models.JSONField(
        default=dict
    )  # How effective wrong options are

    # User Performance Distribution
    performance_by_ability = models.JSONField(
        default=dict
    )  # Performance by user ability levels

    # Quality Metrics
    quality_score = models.FloatField(default=0.0)  # Overall question quality score
    needs_review = models.BooleanField(default=False)
    review_reasons = models.JSONField(default=list)

    # Last updated
    last_calculated = models.DateTimeField(auto_now=True)

    objects = SoftDeleteManager()

    class Meta:
        db_table = "question_analytics"

    def __str__(self):
        return f"Analytics: Q{self.question.id} ({self.success_rate}%)"
