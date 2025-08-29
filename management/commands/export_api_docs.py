from django.core.management.base import BaseCommand
from django.conf import settings
import json
import os


class Command(BaseCommand):
    help = "Export comprehensive API documentation"

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            type=str,
            choices=["openapi", "postman", "insomnia"],
            default="openapi",
            help="Export format",
        )
        parser.add_argument(
            "--output-dir", type=str, default="api_docs", help="Output directory"
        )

    def handle(self, *args, **options):
        output_dir = options["output_dir"]
        os.makedirs(output_dir, exist_ok=True)

        if options["format"] == "openapi":
            self.export_openapi_schema(output_dir)
        elif options["format"] == "postman":
            self.export_postman_collection(output_dir)
        elif options["format"] == "insomnia":
            self.export_insomnia_collection(output_dir)

    def export_openapi_schema(self, output_dir):
        """Export OpenAPI schema with examples."""
        from drf_spectacular.management.commands.spectacular import (
            Command as SpectacularCommand,
        )

        spectacular_command = SpectacularCommand()
        schema = spectacular_command.get_schema(None, public=True)

        # Enhanced schema with more examples
        self.enhance_schema_with_examples(schema)

        # Save main schema
        with open(f"{output_dir}/openapi_schema.json", "w") as f:
            json.dump(schema, f, indent=2)

        # Generate separate files for different sections
        self.generate_auth_docs(schema, output_dir)
        self.generate_websocket_docs(output_dir)
        self.generate_error_codes_docs(output_dir)

        self.stdout.write(
            self.style.SUCCESS(f"OpenAPI documentation exported to {output_dir}/")
        )

    def enhance_schema_with_examples(self, schema):
        """Add comprehensive examples to schema."""
        # Add examples for common request/response patterns
        examples = {
            "UserRegistration": {
                "phone_number": "01712345678",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
            },
            "ExamSession": {
                "id": "session-uuid-here",
                "status": "in_progress",
                "time_remaining_seconds": 1800,
                "total_questions": 50,
                "answers_submitted": 15,
            },
            "ExamResult": {
                "percentage_score": 85.5,
                "is_passed": True,
                "grade": "A",
                "total_questions": 50,
                "correct_answers": 42,
                "time_taken_minutes": 45,
            },
        }

        # Add examples to schema components
        if "components" in schema:
            schema["components"]["examples"] = examples

    def generate_auth_docs(self, schema, output_dir):
        """Generate authentication-specific documentation."""
        auth_doc = {
            "title": "Authentication Guide",
            "description": "Complete authentication flow documentation",
            "flows": [
                {
                    "name": "Registration Flow",
                    "steps": [
                        "Submit registration data to /auth/register/",
                        "Receive OTP via SMS",
                        "Verify OTP at /auth/verify-otp/",
                        "Receive JWT tokens",
                    ],
                },
                {
                    "name": "Login Flow",
                    "steps": [
                        "Submit credentials to /auth/login/",
                        "Receive JWT tokens",
                        "Use access token in Authorization header",
                    ],
                },
            ],
            "token_usage": {
                "header": "Authorization: Bearer <access_token>",
                "expiry": "60 minutes",
                "refresh": "Use refresh token to get new access token",
            },
        }

        with open(f"{output_dir}/authentication_guide.json", "w") as f:
            json.dump(auth_doc, f, indent=2)

    def generate_websocket_docs(self, output_dir):
        """Generate WebSocket API documentation."""
        websocket_doc = {
            "title": "WebSocket API Reference",
            "endpoints": [
                {
                    "url": "ws://localhost:8000/ws/exam/<session_id>/",
                    "description": "Real-time exam session management",
                    "messages": {
                        "client_to_server": [
                            {
                                "type": "heartbeat",
                                "description": "Keep connection alive",
                            },
                            {"type": "save_answer", "description": "Save exam answer"},
                            {
                                "type": "tab_switch",
                                "description": "Report tab switching",
                            },
                        ],
                        "server_to_client": [
                            {
                                "type": "session_update",
                                "description": "Session status update",
                            },
                            {"type": "time_update", "description": "Timer update"},
                            {"type": "warning", "description": "Security warning"},
                        ],
                    },
                }
            ],
        }

        with open(f"{output_dir}/websocket_api.json", "w") as f:
            json.dump(websocket_doc, f, indent=2)
