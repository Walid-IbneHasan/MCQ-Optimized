# apps/leaderboards/management/commands/create_default_leaderboards.py
from django.core.management.base import BaseCommand
from apps.leaderboards.models import LeaderboardType


class Command(BaseCommand):
    help = "Create default leaderboard types for scheduled and practice exams"

    def handle(self, *args, **options):
        # Default scheduled exam leaderboards
        scheduled_periods = [
            ("weekly", "Weekly", "Weekly rankings for scheduled exams"),
            ("biweekly", "Bi-weekly", "Bi-weekly rankings for scheduled exams"),
            ("monthly", "Monthly", "Monthly rankings for scheduled exams"),
            ("quarterly", "Quarterly", "Quarterly rankings for scheduled exams"),
        ]

        self.stdout.write("Creating scheduled exam leaderboards...")
        for period_key, period_name, description in scheduled_periods:
            leaderboard_type, created = LeaderboardType.objects.get_or_create(
                scope="exam",
                period=period_key,
                name=f"Scheduled Exam {period_name} Rankings",
                exam_type_filter="scheduled",
                defaults={
                    "description": description,
                    "score_calculation_method": "best",
                    "max_entries": 100,
                    "min_exams_required": 1,
                    "is_public": True,
                    "is_active": True,
                    "is_default": period_key == "weekly",  # Weekly is default
                },
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created: {leaderboard_type.name}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Already exists: {leaderboard_type.name}")
                )

        # Practice exam leaderboards
        self.stdout.write("\nCreating practice exam leaderboards...")
        for period_key, period_name, description in scheduled_periods:
            description = description.replace("scheduled", "practice")
            leaderboard_type, created = LeaderboardType.objects.get_or_create(
                scope="exam",
                period=period_key,
                name=f"Practice Exam {period_name} Rankings",
                exam_type_filter="practice",
                defaults={
                    "description": description,
                    "score_calculation_method": "best",
                    "max_entries": 50,
                    "min_exams_required": 1,
                    "is_public": True,
                    "is_active": True,
                    "is_default": False,
                },
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created: {leaderboard_type.name}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Already exists: {leaderboard_type.name}")
                )

        # Global leaderboards
        self.stdout.write("\nCreating global leaderboards...")
        for period_key, period_name, description in scheduled_periods:
            leaderboard_type, created = LeaderboardType.objects.get_or_create(
                scope="global",
                period=period_key,
                name=f"Global {period_name} Rankings",
                exam_type_filter="all",
                defaults={
                    "description": f"{period_name} global rankings across all exams",
                    "score_calculation_method": "average",
                    "max_entries": 100,
                    "min_exams_required": 3,
                    "is_public": True,
                    "is_active": True,
                    "is_default": False,
                },
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Created: {leaderboard_type.name}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Already exists: {leaderboard_type.name}")
                )

        self.stdout.write(
            self.style.SUCCESS("\nDefault leaderboard types created successfully!")
        )
