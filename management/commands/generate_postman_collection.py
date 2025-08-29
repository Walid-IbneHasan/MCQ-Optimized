from django.core.management.base import BaseCommand
from django.urls import get_resolver
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.management.commands.spectacular import (
    Command as SpectacularCommand,
)
import json
import uuid
from datetime import datetime


class Command(BaseCommand):
    help = "Generate Postman collection from OpenAPI schema"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="postman_collection.json",
            help="Output file path",
        )
        parser.add_argument(
            "--environment",
            type=str,
            default="postman_environment.json",
            help="Environment file path",
        )

    def handle(self, *args, **options):
        self.stdout.write("Generating Postman collection...")

        # Generate OpenAPI schema
        spectacular_command = SpectacularCommand()
        schema = spectacular_command.get_schema(None, public=True)

        # Convert to Postman format
        collection = self.convert_to_postman(schema)

        # Save collection
        with open(options["output"], "w") as f:
            json.dump(collection, f, indent=2)

        # Generate environment
        environment = self.generate_environment()
        with open(options["environment"], "w") as f:
            json.dump(environment, f, indent=2)

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully generated Postman collection: {options["output"]}'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully generated Postman environment: {options["environment"]}'
            )
        )

    def convert_to_postman(self, schema):
        """Convert OpenAPI schema to Postman collection format."""
        collection = {
            "info": {
                "name": "MCQ Platform API",
                "description": schema.get("info", {}).get("description", ""),
                "version": schema.get("info", {}).get("version", "1.0.0"),
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "auth": {
                "type": "bearer",
                "bearer": [
                    {"key": "token", "value": "{{jwt_token}}", "type": "string"}
                ],
            },
            "event": [
                {
                    "listen": "prerequest",
                    "script": {
                        "type": "text/javascript",
                        "exec": [
                            "// Set common variables",
                            "pm.collectionVariables.set('timestamp', new Date().getTime());",
                        ],
                    },
                }
            ],
            "item": [],
            "variable": [
                {"key": "base_url", "value": "{{base_url}}", "type": "string"}
            ],
        }

        # Group endpoints by tags
        grouped_paths = {}
        for path, path_item in schema.get("paths", {}).items():
            for method, operation in path_item.items():
                if method.upper() in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                    tags = operation.get("tags", ["Untagged"])
                    tag = tags[0] if tags else "Untagged"

                    if tag not in grouped_paths:
                        grouped_paths[tag] = []

                    grouped_paths[tag].append(
                        {"path": path, "method": method.upper(), "operation": operation}
                    )

        # Convert to Postman items
        for tag, endpoints in grouped_paths.items():
            folder = {"name": tag, "item": []}

            for endpoint in endpoints:
                item = self.create_postman_item(endpoint)
                folder["item"].append(item)

            collection["item"].append(folder)

        return collection

    def create_postman_item(self, endpoint):
        """Create a Postman request item from endpoint data."""
        operation = endpoint["operation"]

        # Base request structure
        request = {
            "name": operation.get(
                "summary", f"{endpoint['method']} {endpoint['path']}"
            ),
            "request": {
                "method": endpoint["method"],
                "header": [
                    {
                        "key": "Content-Type",
                        "value": "application/json",
                        "type": "text",
                    },
                    {"key": "Accept", "value": "application/json", "type": "text"},
                ],
                "url": {
                    "raw": "{{base_url}}" + endpoint["path"],
                    "host": ["{{base_url}}"],
                    "path": endpoint["path"].strip("/").split("/"),
                    "query": [],
                },
            },
        }

        # Add description
        if operation.get("description"):
            request["request"]["description"] = operation["description"]

        # Add authentication for protected endpoints
        if "security" in operation:
            request["request"]["auth"] = {
                "type": "bearer",
                "bearer": [
                    {"key": "token", "value": "{{jwt_token}}", "type": "string"}
                ],
            }

        # Add request body for POST/PUT/PATCH
        if endpoint["method"] in ["POST", "PUT", "PATCH"]:
            request_body = operation.get("requestBody", {})
            if request_body:
                content = request_body.get("content", {})
                json_content = content.get("application/json", {})

                if json_content:
                    example = self.get_example_from_schema(
                        json_content.get("schema", {})
                    )
                    request["request"]["body"] = {
                        "mode": "raw",
                        "raw": json.dumps(example, indent=2),
                        "options": {"raw": {"language": "json"}},
                    }

        # Add query parameters
        parameters = operation.get("parameters", [])
        for param in parameters:
            if param.get("in") == "query":
                request["request"]["url"]["query"].append(
                    {
                        "key": param["name"],
                        "value": self.get_example_value(param.get("schema", {})),
                        "description": param.get("description", ""),
                        "disabled": not param.get("required", False),
                    }
                )

        # Add path variables
        path_params = [p for p in parameters if p.get("in") == "path"]
        if path_params:
            request["request"]["url"]["variable"] = []
            for param in path_params:
                request["request"]["url"]["variable"].append(
                    {
                        "key": param["name"],
                        "value": self.get_example_value(param.get("schema", {})),
                        "description": param.get("description", ""),
                    }
                )

        # Add response examples
        responses = operation.get("responses", {})
        if responses:
            request["response"] = []
            for status_code, response in responses.items():
                if status_code.startswith("2"):  # Success responses
                    example_response = {
                        "name": f"Success ({status_code})",
                        "originalRequest": request["request"].copy(),
                        "status": response.get("description", "OK"),
                        "code": int(status_code),
                        "header": [
                            {"key": "Content-Type", "value": "application/json"}
                        ],
                    }

                    # Add response body
                    content = response.get("content", {})
                    json_content = content.get("application/json", {})
                    if json_content:
                        example_body = self.get_example_from_schema(
                            json_content.get("schema", {})
                        )
                        example_response["body"] = json.dumps(example_body, indent=2)

                    request["response"].append(example_response)

        return request

    def get_example_from_schema(self, schema):
        """Generate example data from JSON schema."""
        if "example" in schema:
            return schema["example"]

        schema_type = schema.get("type", "object")

        if schema_type == "object":
            example = {}
            properties = schema.get("properties", {})
            for prop_name, prop_schema in properties.items():
                example[prop_name] = self.get_example_value(prop_schema)
            return example

        elif schema_type == "array":
            items_schema = schema.get("items", {})
            return [self.get_example_value(items_schema)]

        else:
            return self.get_example_value(schema)

    def get_example_value(self, schema):
        """Get example value for a schema type."""
        if "example" in schema:
            return schema["example"]

        schema_type = schema.get("type", "string")
        schema_format = schema.get("format")

        examples = {
            "string": {
                "email": "user@example.com",
                "uuid": str(uuid.uuid4()),
                "date": "2024-01-15",
                "date-time": "2024-01-15T10:30:00Z",
                "phone": "+8801712345678",
                "default": "example string",
            },
            "integer": 42,
            "number": 42.0,
            "boolean": True,
            "array": [],
            "object": {},
        }

        if schema_type == "string" and schema_format:
            return examples["string"].get(schema_format, examples["string"]["default"])

        return examples.get(schema_type, "example")

    def generate_environment(self):
        """Generate Postman environment file."""
        return {
            "id": str(uuid.uuid4()),
            "name": "MCQ Platform Environment",
            "values": [
                {
                    "key": "base_url",
                    "value": "http://localhost:8000/api",
                    "enabled": True,
                    "type": "text",
                },
                {"key": "jwt_token", "value": "", "enabled": True, "type": "secret"},
                {
                    "key": "refresh_token",
                    "value": "",
                    "enabled": True,
                    "type": "secret",
                },
                {"key": "user_id", "value": "", "enabled": True, "type": "text"},
                {
                    "key": "phone_number",
                    "value": "01712345678",
                    "enabled": True,
                    "type": "text",
                },
                {"key": "test_exam_id", "value": "", "enabled": True, "type": "text"},
                {
                    "key": "test_session_id",
                    "value": "",
                    "enabled": True,
                    "type": "text",
                },
            ],
            "_postman_variable_scope": "environment",
        }
