from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.plumbing import build_parameter_type
from rest_framework import serializers
from typing import Any, Dict


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "rest_framework_simplejwt.authentication.JWTAuthentication"
    name = "JWT Authentication"
    priority = 0

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token authentication. Format: `Bearer <token>`",
        }


def custom_preprocessing_hook(endpoints):
    """
    Custom preprocessing to modify OpenAPI schema before generation.
    """
    # Filter out admin and debug endpoints in production
    filtered = []
    for path, path_regex, method, callback in endpoints:
        # Skip admin and debug URLs
        if path.startswith("/admin/") or path.startswith("/__debug__/"):
            continue
        # Skip static and media URLs
        if path.startswith("/static/") or path.startswith("/media/"):
            continue
        filtered.append((path, path_regex, method, callback))

    return filtered


def custom_postprocessing_hook(result, generator, request, public):
    """
    Custom postprocessing to modify the final OpenAPI schema.
    """
    # Add custom headers to all responses
    for path_item in result["paths"].values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "responses" in operation:
                for response in operation["responses"].values():
                    if isinstance(response, dict):
                        response.setdefault("headers", {})
                        response["headers"]["X-API-Version"] = {
                            "description": "API version",
                            "schema": {"type": "string", "example": "1.0.0"},
                        }
                        response["headers"]["X-Request-ID"] = {
                            "description": "Request identifier",
                            "schema": {"type": "string", "format": "uuid"},
                        }

    # Add common error responses
    common_errors = {
        "400": {
            "description": "Bad Request",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "success": {"type": "boolean", "example": False},
                            "errors": {"type": "object"},
                            "message": {
                                "type": "string",
                                "example": "Invalid input data",
                            },
                        },
                    }
                }
            },
        },
        "401": {
            "description": "Unauthorized",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "success": {"type": "boolean", "example": False},
                            "error": {
                                "type": "string",
                                "example": "Authentication credentials were not provided",
                            },
                        },
                    }
                }
            },
        },
        "403": {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "success": {"type": "boolean", "example": False},
                            "error": {
                                "type": "string",
                                "example": "You do not have permission to perform this action",
                            },
                        },
                    }
                }
            },
        },
        "404": {
            "description": "Not Found",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "success": {"type": "boolean", "example": False},
                            "error": {
                                "type": "string",
                                "example": "Resource not found",
                            },
                        },
                    }
                }
            },
        },
        "429": {
            "description": "Rate Limited",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "success": {"type": "boolean", "example": False},
                            "error": {
                                "type": "string",
                                "example": "Request was throttled",
                            },
                        },
                    }
                }
            },
        },
    }

    # Add common error responses to all operations
    for path_item in result["paths"].values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "responses" in operation:
                # Add common errors if they don't already exist
                for status_code, error_response in common_errors.items():
                    if status_code not in operation["responses"]:
                        operation["responses"][status_code] = error_response

    return result


class CustomAutoSchema(AutoSchema):
    """
    Custom schema generator with enhanced documentation.
    """

    def get_operation_id(self):
        """Generate more descriptive operation IDs."""
        tokenized_path = self._tokenize_path()
        action = self.method.lower()

        if self.target_component == "request":
            action += "_request"
        elif self.target_component == "response":
            action += "_response"

        if hasattr(self.view, "action") and self.view.action:
            if self.view.action != action:
                action = self.view.action

        # Create readable operation ID
        resource = tokenized_path[0] if tokenized_path else "root"
        return f"{action}_{resource}".replace("-", "_")

    def get_tags(self):
        """Get tags for operation grouping."""
        tokenized_path = self._tokenize_path()

        if tokenized_path:
            # Map first path component to tag
            path_to_tag = {
                "auth": "Authentication",
                "subscriptions": "Subscriptions",
                "subjects": "Subjects",
                "questions": "Questions",
                "exams": "Exams",
                "sessions": "Exam Sessions",
                "results": "Results",
                "leaderboards": "Leaderboards",
                "notifications": "Notifications",
                "analytics": "Analytics",
            }

            main_resource = tokenized_path[0]
            return [path_to_tag.get(main_resource, main_resource.title())]

        return super().get_tags()

    def get_summary(self):
        """Generate descriptive summary for operations."""
        if hasattr(self.view, "action") and self.view.action:
            action = self.view.action

            # Custom summaries for common actions
            action_summaries = {
                "list": "List all items",
                "create": "Create new item",
                "retrieve": "Get item details",
                "update": "Update item",
                "partial_update": "Partially update item",
                "destroy": "Delete item",
            }

            summary = action_summaries.get(action, action.replace("_", " ").title())

            # Add resource name if available
            if hasattr(self.view, "queryset") and hasattr(self.view.queryset, "model"):
                model_name = self.view.queryset.model._meta.verbose_name
                summary = summary.replace("item", model_name)

            return summary

        return super().get_summary()
