# apps/results/management/commands/populate_analytics.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.exams.models import Exam
from apps.questions.models import Question
from apps.results.models import ExamResult
from apps.results.tasks import (
    calculate_exam_analytics,
    calculate_user_analytics,
    calculate_question_analytics,
    update_subject_performances,
)
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Populate analytics for existing exam results"

    def add_arguments(self, parser):
        parser.add_argument(
            "--exam-id",
            type=str,
            help="Calculate analytics for specific exam",
        )
        parser.add_argument(
            "--user-id",
            type=str,
            help="Calculate analytics for specific user",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force recalculation even if analytics exist",
        )

    def handle(self, *args, **options):
        if options["exam_id"]:
            # Calculate for specific exam
            self.calculate_exam_analytics(options["exam_id"], options["force"])
        elif options["user_id"]:
            # Calculate for specific user
            self.calculate_user_analytics(options["user_id"], options["force"])
        else:
            # Calculate for all
            self.calculate_all_analytics(options["force"])

    def calculate_exam_analytics(self, exam_id, force=False):
        """Calculate analytics for a specific exam."""
        try:
            exam = Exam.objects.get(id=exam_id)

            # Check if analytics already exist
            from apps.results.models import ExamAnalytics

            analytics_exist = ExamAnalytics.objects.filter(exam=exam).exists()

            if analytics_exist and not force:
                self.stdout.write(
                    self.style.WARNING(
                        f"Analytics already exist for exam {exam.title}. Use --force to recalculate."
                    )
                )
                return

            # Check if exam has results
            if not ExamResult.objects.filter(exam=exam).exists():
                self.stdout.write(
                    self.style.WARNING(f"No results found for exam {exam.title}")
                )
                return

            # Trigger calculation
            calculate_exam_analytics.delay(exam_id)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Analytics calculation triggered for exam: {exam.title}"
                )
            )

        except Exam.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Exam with ID {exam_id} not found"))

    def calculate_user_analytics(self, user_id, force=False):
        """Calculate analytics for a specific user."""
        try:
            user = User.objects.get(id=user_id)

            # Check if analytics already exist
            from apps.results.models import UserPerformanceAnalytics

            analytics_exist = UserPerformanceAnalytics.objects.filter(
                user=user
            ).exists()

            if analytics_exist and not force:
                self.stdout.write(
                    self.style.WARNING(
                        f"Analytics already exist for user {user.phone_number}. Use --force to recalculate."
                    )
                )
                return

            # Check if user has results
            if not ExamResult.objects.filter(user=user).exists():
                self.stdout.write(
                    self.style.WARNING(f"No results found for user {user.phone_number}")
                )
                return

            # Trigger calculation
            calculate_user_analytics.delay(user_id)
            update_subject_performances.delay(user_id)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Analytics calculation triggered for user: {user.phone_number}"
                )
            )

        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User with ID {user_id} not found"))

    def calculate_all_analytics(self, force=False):
        """Calculate analytics for all entities that have results."""
        self.stdout.write("Starting analytics calculation for all entities...")

        # 1. Calculate exam analytics
        self.stdout.write("Calculating exam analytics...")
        exams_with_results = Exam.objects.filter(results__isnull=False).distinct()

        for exam in exams_with_results:
            from apps.results.models import ExamAnalytics

            if not force and ExamAnalytics.objects.filter(exam=exam).exists():
                continue

            calculate_exam_analytics.delay(exam.id)
            self.stdout.write(f"  - Queued analytics for exam: {exam.title}")

        self.stdout.write(f"Queued analytics for {exams_with_results.count()} exams")

        # 2. Calculate user analytics
        self.stdout.write("Calculating user analytics...")
        users_with_results = User.objects.filter(exam_results__isnull=False).distinct()

        for user in users_with_results:
            from apps.results.models import UserPerformanceAnalytics

            if (
                not force
                and UserPerformanceAnalytics.objects.filter(user=user).exists()
            ):
                continue

            calculate_user_analytics.delay(user.id)
            update_subject_performances.delay(user.id)
            self.stdout.write(f"  - Queued analytics for user: {user.phone_number}")

        self.stdout.write(f"Queued analytics for {users_with_results.count()} users")

        # 3. Calculate question analytics
        self.stdout.write("Calculating question analytics...")
        from apps.exams.models import ExamAnswer

        questions_with_answers = Question.objects.filter(
            examanswer__isnull=False
        ).distinct()[
            :200
        ]  # Limit to avoid overload

        for question in questions_with_answers:
            from apps.results.models import QuestionAnalytics

            if (
                not force
                and QuestionAnalytics.objects.filter(question=question).exists()
            ):
                continue

            calculate_question_analytics.delay(question.id)

        self.stdout.write(
            f"Queued analytics for {questions_with_answers.count()} questions"
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Analytics calculation queued for all entities. "
                "Check Celery logs for progress."
            )
        )
