# apps/exams/management/commands/fix_missing_results.py
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.exams.models import ExamSession
from apps.results.models import ExamResult
from apps.exams.tasks import calculate_session_score
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix missing ExamResult records for completed sessions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--exam-id",
            type=str,
            help="Process only a specific exam ID",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be processed without making changes",
        )

    def handle(self, *args, **options):
        # Find completed sessions without results
        sessions_query = (
            ExamSession.objects.filter(status__in=["completed", "auto_submitted"])
            .exclude(id__in=ExamResult.objects.values_list("session_id", flat=True))
            .select_related("exam", "user")
        )

        if options["exam_id"]:
            sessions_query = sessions_query.filter(exam_id=options["exam_id"])

        missing_sessions = list(sessions_query)

        self.stdout.write(
            self.style.WARNING(
                f"Found {len(missing_sessions)} completed sessions without ExamResult records"
            )
        )

        if options["dry_run"]:
            for session in missing_sessions:
                self.stdout.write(
                    f"Would process: Session {session.id} - User {session.user.phone_number} - Exam {session.exam.title}"
                )
            return

        # Process each missing session
        success_count = 0
        error_count = 0

        for session in missing_sessions:
            try:
                self.stdout.write(f"Processing session {session.id}...")

                # Calculate score and create result
                result = calculate_session_score(session.id)

                if result and result.get("success"):
                    success_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'✓ Created result for session {session.id} - Score: {result.get("score", 0):.1f}%'
                        )
                    )
                else:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ Failed to create result for session {session.id}"
                        )
                    )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"✗ Error processing session {session.id}: {str(e)}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nCompleted: {success_count} successful, {error_count} errors"
            )
        )
