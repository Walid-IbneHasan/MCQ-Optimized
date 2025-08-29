"""
# MCQ Platform API Documentation

## Overview
This directory contains comprehensive API documentation for the MCQ Platform, including OpenAPI specifications, Postman collections, and testing tools.

## Quick Start

### 1. Generate Documentation
```bash
# Generate OpenAPI schema
python manage.py spectacular --file api_docs/schema.yaml

# Generate Postman collection
python manage.py generate_postman_collection --output api_docs/postman_collection.json

# Generate comprehensive docs
python manage.py export_api_docs --format openapi --output-dir api_docs
```

### 2. View Documentation
- **Swagger UI**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/
- **Schema**: http://localhost# requirements.txt additions for API documentation
"""
Add these to your existing requirements.txt:

drf-spectacular==0.27.0
drf-spectacular-sidecar==2023.10.1
"""

---

# mcq_platform/settings/base.py - Add documentation settings

# Add to INSTALLED_APPS
INSTALLED_APPS += [
    'drf_spectacular',
    'drf_spectacular_sidecar',
]

# Add to REST_FRAMEWORK settings
REST_FRAMEWORK.update({
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
})

# DRF Spectacular settings for OpenAPI documentation
SPECTACULAR_SETTINGS = {
    'TITLE': 'MCQ Platform API',
    'DESCRIPTION': '''
    ## MCQ Platform API Documentation
    
    A comprehensive educational MCQ platform with real-time exam sessions, performance analytics, 
    leaderboards, and subscription management.
    
    ### Key Features:
    - **Authentication**: JWT-based authentication with OTP verification
    - **Real-time Exams**: WebSocket-powered exam sessions with anti-cheat measures
    - **Performance Analytics**: Comprehensive user and system analytics
    - **Leaderboards**: Multi-level ranking system with achievements
    - **Subscriptions**: Payment integration with SSLCommerz
    - **Notifications**: Multi-channel notification system
    
    ### Base URL
    - **Development**: `http://localhost:8000`
    - **Production**: `https://your-domain.com`
    
    ### Authentication
    Most endpoints require authentication. Include the JWT token in the Authorization header:
    ```
    Authorization: Bearer <your-jwt-token>
    ```
    
    ### Rate Limiting
    - Anonymous users: 100 requests/hour
    - Authenticated users: 1000 requests/hour
    - Login attempts: 5 requests/minute
    
    ### Response Format
    All API responses follow this structure:
    ```json
    {
        "success": true,
        "data": {...},
        "message": "Success message",
        "errors": {...}
    }
    ```
    
    ### Error Codes
    - `400`: Bad Request - Invalid input data
    - `401`: Unauthorized - Authentication required
    - `403`: Forbidden - Insufficient permissions
    - `404`: Not Found - Resource not found
    - `429`: Too Many Requests - Rate limit exceeded
    - `500`: Internal Server Error - Server error
    
    ### Pagination
    List endpoints support pagination:
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 20, max: 100)
    
    ### Filtering & Search
    Many list endpoints support filtering and search:
    - `search`: Search query
    - `ordering`: Field to order by (prefix with `-` for descending)
    - Additional filters specific to each endpoint
    
    ### WebSocket Endpoints
    Real-time features use WebSocket connections:
    - Exam Timer: `ws://localhost:8000/ws/exam-timer/<session_id>/`
    - Exam Updates: `ws://localhost:8000/ws/exam/<session_id>/`
    
    ### Support
    For API support, contact: support@mcqplatform.com
    ''',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'CONTACT': {
        'name': 'MCQ Platform API Support',
        'email': 'support@mcqplatform.com',
    },
    'LICENSE': {
        'name': 'Proprietary License',
    },
    # UI configuration
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
        'defaultModelsExpandDepth': 2,
        'defaultModelExpandDepth': 2,
        'displayRequestDuration': True,
        'docExpansion': 'none',
        'filter': True,
        'operationsSorter': 'alpha',
        'showExtensions': True,
        'tagsSorter': 'alpha',
        'tryItOutEnabled': True,
    },
    'REDOC_UI_SETTINGS': {
        'hideDownloadButton': False,
        'hideHostname': False,
        'hideLoading': False,
        'hideSchemaPattern': True,
        'hideRequestPayloadSample': False,
        'hideResponsePayloadSample': False,
        'noAutoAuth': False,
        'pathInMiddlePanel': False,
        'requiredPropsFirst': True,
        'scrollYOffset': 0,
        'showObjectSchemaExamples': True,
        'suppressWarnings': False,
        'theme': {
            'colors': {
                'primary': {
                    'main': '#667eea'
                }
            }
        }
    },
    # Schema generation settings
    'COMPONENT_SPLIT_REQUEST': True,
    'COMPONENT_NO_READ_ONLY_REQUIRED': True,
    'SCHEMA_PATH_PREFIX': r'/api/',
    'SCHEMA_PATH_PREFIX_TRIM': True,
    'SERVE_PERMISSIONS': ['rest_framework.permissions.AllowAny'],
    'SWAGGER_UI_FAVICON_HREF': '/static/favicon.ico',
    'REDOC_FAVICON_HREF': '/static/favicon.ico',
    # Authentication schemes
    'AUTHENTICATION_WHITELIST': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    # Custom schema extensions
    'EXTENSIONS_INFO': {
        'x-logo': {
            'url': '/static/logo.png',
            'altText': 'MCQ Platform Logo'
        }
    },
    # Tags for organizing endpoints
    'TAGS': [
        {'name': 'Authentication', 'description': 'User authentication and authorization'},
        {'name': 'Users', 'description': 'User management and profiles'},
        {'name': 'Subscriptions', 'description': 'Subscription plans and payments'},
        {'name': 'Subjects', 'description': 'Academic subjects and chapters'},
        {'name': 'Questions', 'description': 'MCQ questions and question banks'},
        {'name': 'Exams', 'description': 'Exam creation and management'},
        {'name': 'Exam Sessions', 'description': 'Real-time exam sessions'},
        {'name': 'Results', 'description': 'Exam results and performance analytics'},
        {'name': 'Leaderboards', 'description': 'Rankings and achievements'},
        {'name': 'Notifications', 'description': 'Notification management'},
        {'name': 'Analytics', 'description': 'System analytics and reporting'},
    ],
    # Custom preprocessing
    'PREPROCESSING_HOOKS': [
        'apps.core.schema.custom_preprocessing_hook',
    ],
    # Custom postprocessing
    'POSTPROCESSING_HOOKS': [
        'apps.core.schema.custom_postprocessing_hook',
    ],
}

---

# apps/core/schema.py - Custom schema processing

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.plumbing import build_parameter_type
from rest_framework import serializers
from typing import Any, Dict

class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'rest_framework_simplejwt.authentication.JWTAuthentication'
    name = 'JWT Authentication'
    priority = 0

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': 'JWT token authentication. Format: `Bearer <token>`'
        }

def custom_preprocessing_hook(endpoints):
    """
    Custom preprocessing to modify OpenAPI schema before generation.
    """
    # Filter out admin and debug endpoints in production
    filtered = []
    for (path, path_regex, method, callback) in endpoints:
        # Skip admin and debug URLs
        if path.startswith('/admin/') or path.startswith('/__debug__/'):
            continue
        # Skip static and media URLs
        if path.startswith('/static/') or path.startswith('/media/'):
            continue
        filtered.append((path, path_regex, method, callback))
    
    return filtered

def custom_postprocessing_hook(result, generator, request, public):
    """
    Custom postprocessing to modify the final OpenAPI schema.
    """
    # Add custom headers to all responses
    for path_item in result['paths'].values():
        for operation in path_item.values():
            if isinstance(operation, dict) and 'responses' in operation:
                for response in operation['responses'].values():
                    if isinstance(response, dict):
                        response.setdefault('headers', {})
                        response['headers']['X-API-Version'] = {
                            'description': 'API version',
                            'schema': {'type': 'string', 'example': '1.0.0'}
                        }
                        response['headers']['X-Request-ID'] = {
                            'description': 'Request identifier',
                            'schema': {'type': 'string', 'format': 'uuid'}
                        }
    
    # Add common error responses
    common_errors = {
        '400': {
            'description': 'Bad Request',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'success': {'type': 'boolean', 'example': False},
                            'errors': {'type': 'object'},
                            'message': {'type': 'string', 'example': 'Invalid input data'}
                        }
                    }
                }
            }
        },
        '401': {
            'description': 'Unauthorized',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'success': {'type': 'boolean', 'example': False},
                            'error': {'type': 'string', 'example': 'Authentication credentials were not provided'}
                        }
                    }
                }
            }
        },
        '403': {
            'description': 'Forbidden',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'success': {'type': 'boolean', 'example': False},
                            'error': {'type': 'string', 'example': 'You do not have permission to perform this action'}
                        }
                    }
                }
            }
        },
        '404': {
            'description': 'Not Found',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'success': {'type': 'boolean', 'example': False},
                            'error': {'type': 'string', 'example': 'Resource not found'}
                        }
                    }
                }
            }
        },
        '429': {
            'description': 'Rate Limited',
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'success': {'type': 'boolean', 'example': False},
                            'error': {'type': 'string', 'example': 'Request was throttled'}
                        }
                    }
                }
            }
        }
    }
    
    # Add common error responses to all operations
    for path_item in result['paths'].values():
        for operation in path_item.values():
            if isinstance(operation, dict) and 'responses' in operation:
                # Add common errors if they don't already exist
                for status_code, error_response in common_errors.items():
                    if status_code not in operation['responses']:
                        operation['responses'][status_code] = error_response
    
    return result

class CustomAutoSchema(AutoSchema):
    """
    Custom schema generator with enhanced documentation.
    """
    
    def get_operation_id(self):
        """Generate more descriptive operation IDs."""
        tokenized_path = self._tokenize_path()
        action = self.method.lower()
        
        if self.target_component == 'request':
            action += '_request'
        elif self.target_component == 'response':
            action += '_response'
        
        if hasattr(self.view, 'action') and self.view.action:
            if self.view.action != action:
                action = self.view.action
        
        # Create readable operation ID
        resource = tokenized_path[0] if tokenized_path else 'root'
        return f"{action}_{resource}".replace('-', '_')
    
    def get_tags(self):
        """Get tags for operation grouping."""
        tokenized_path = self._tokenize_path()
        
        if tokenized_path:
            # Map first path component to tag
            path_to_tag = {
                'auth': 'Authentication',
                'subscriptions': 'Subscriptions',
                'subjects': 'Subjects',
                'questions': 'Questions',
                'exams': 'Exams',
                'sessions': 'Exam Sessions',
                'results': 'Results',
                'leaderboards': 'Leaderboards',
                'notifications': 'Notifications',
                'analytics': 'Analytics',
            }
            
            main_resource = tokenized_path[0]
            return [path_to_tag.get(main_resource, main_resource.title())]
        
        return super().get_tags()
    
    def get_summary(self):
        """Generate descriptive summary for operations."""
        if hasattr(self.view, 'action') and self.view.action:
            action = self.view.action
            
            # Custom summaries for common actions
            action_summaries = {
                'list': 'List all items',
                'create': 'Create new item',
                'retrieve': 'Get item details',
                'update': 'Update item',
                'partial_update': 'Partially update item',
                'destroy': 'Delete item',
            }
            
            summary = action_summaries.get(action, action.replace('_', ' ').title())
            
            # Add resource name if available
            if hasattr(self.view, 'queryset') and hasattr(self.view.queryset, 'model'):
                model_name = self.view.queryset.model._meta.verbose_name
                summary = summary.replace('item', model_name)
            
            return summary
        
        return super().get_summary()

---

# Enhanced serializers with better documentation

# apps/authentication/serializers.py - Add documentation examples
from drf_spectacular.utils import extend_schema_serializer, OpenApiExample

@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Registration Example',
            summary='User registration with all fields',
            description='Example of user registration with complete information',
            value={
                'phone_number': '01712345678',
                'password': 'SecurePass123!',
                'confirm_password': 'SecurePass123!',
                'first_name': 'John',
                'last_name': 'Doe',
                'email': 'john.doe@example.com'
            },
            request_only=True,
        ),
    ]
)
class UserRegistrationSerializer(serializers.ModelSerializer):
    # ... existing code ...
    pass

@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'OTP Verification Example',
            summary='Verify OTP for registration',
            value={
                'phone_number': '01712345678',
                'otp_code': '123456',
                'otp_type': 'registration'
            },
            request_only=True,
        ),
    ]
)
class OTPVerificationSerializer(serializers.Serializer):
    # ... existing code ...
    pass

@extend_schema_serializer(
    examples=[
        OpenApiExample(
            'Login Example',
            summary='User login credentials',
            value={
                'phone_number': '01712345678',
                'password': 'SecurePass123!'
            },
            request_only=True,
        ),
    ]
)
class UserLoginSerializer(serializers.Serializer):
    # ... existing code ...
    pass

---

# Enhanced views with detailed documentation

# apps/authentication/views.py - Add comprehensive documentation
from drf_spectacular.utils import (
    extend_schema, extend_schema_view, OpenApiParameter, OpenApiExample,
    OpenApiResponse, inline_serializer
)

@extend_schema_view(
    post=extend_schema(
        summary='Register new user',
        description='''
        Register a new user account with phone number verification.
        
        **Process:**
        1. Submit registration details
        2. Receive OTP via SMS
        3. Verify OTP to activate account
        4. Get JWT tokens upon successful verification
        
        **Phone Number Format:**
        - Must be valid Bangladeshi number
        - Format: +8801XXXXXXXXX or 01XXXXXXXXX
        
        **Password Requirements:**
        - Minimum 8 characters
        - Must contain letters and numbers
        - Special characters recommended
        ''',
        request=UserRegistrationSerializer,
        responses={
            201: OpenApiResponse(
                response=inline_serializer(
                    name='RegistrationResponse',
                    fields={
                        'success': serializers.BooleanField(default=True),
                        'message': serializers.CharField(default='Registration successful. OTP sent to your phone.'),
                        'phone_number': serializers.CharField(),
                    }
                ),
                description='Registration successful, OTP sent',
                examples=[
                    OpenApiExample(
                        'Success Response',
                        value={
                            'success': True,
                            'message': 'Registration successful. OTP sent to your phone.',
                            'phone_number': '01712345678'
                        }
                    )
                ]
            ),
            400: OpenApiResponse(
                description='Registration failed - validation errors',
                examples=[
                    OpenApiExample(
                        'Validation Error',
                        value={
                            'success': False,
                            'errors': {
                                'phone_number': ['User with this phone number already exists.'],
                                'password': ['This password is too common.']
                            }
                        }
                    )
                ]
            )
        },
        tags=['Authentication'],
    )
)
class UserRegistrationView(APIView):
    # ... existing code ...
    pass

@extend_schema_view(
    post=extend_schema(
        summary='Verify OTP',
        description='''
        Verify OTP code sent via SMS during registration or password reset.
        
        **OTP Types:**
        - `registration`: Verify new account registration
        - `login`: Verify login attempt
        - `password_reset`: Verify password reset request
        
        **OTP Validity:**
        - Valid for 5 minutes after generation
        - Maximum 5 attempts allowed
        - Case-sensitive 6-digit code
        ''',
        request=OTPVerificationSerializer,
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name='OTPVerificationResponse',
                    fields={
                        'success': serializers.BooleanField(default=True),
                        'message': serializers.CharField(),
                        'access_token': serializers.CharField(required=False),
                        'refresh_token': serializers.CharField(required=False),
                        'user': UserProfileSerializer(required=False),
                    }
                ),
                description='OTP verified successfully',
                examples=[
                    OpenApiExample(
                        'Registration OTP Success',
                        value={
                            'success': True,
                            'message': 'OTP verified successfully.',
                            'access_token': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
                            'refresh_token': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...',
                            'user': {
                                'id': 'uuid-here',
                                'phone_number': '01712345678',
                                'full_name': 'John Doe'
                            }
                        }
                    )
                ]
            )
        },
        tags=['Authentication'],
    )
)
class OTPVerificationView(APIView):
    # ... existing code ...
    pass

---

# Management command to generate Postman collection

# management/commands/generate_postman_collection.py
from django.core.management.base import BaseCommand
from django.urls import get_resolver
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.management.commands.spectacular import Command as SpectacularCommand
import json
import uuid
from datetime import datetime

class Command(BaseCommand):
    help = 'Generate Postman collection from OpenAPI schema'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='postman_collection.json',
            help='Output file path'
        )
        parser.add_argument(
            '--environment',
            type=str,
            default='postman_environment.json',
            help='Environment file path'
        )

    def handle(self, *args, **options):
        self.stdout.write('Generating Postman collection...')
        
        # Generate OpenAPI schema
        spectacular_command = SpectacularCommand()
        schema = spectacular_command.get_schema(None, public=True)
        
        # Convert to Postman format
        collection = self.convert_to_postman(schema)
        
        # Save collection
        with open(options['output'], 'w') as f:
            json.dump(collection, f, indent=2)
        
        # Generate environment
        environment = self.generate_environment()
        with open(options['environment'], 'w') as f:
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
                "description": schema.get('info', {}).get('description', ''),
                "version": schema.get('info', {}).get('version', '1.0.0'),
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "auth": {
                "type": "bearer",
                "bearer": [
                    {
                        "key": "token",
                        "value": "{{jwt_token}}",
                        "type": "string"
                    }
                ]
            },
            "event": [
                {
                    "listen": "prerequest",
                    "script": {
                        "type": "text/javascript",
                        "exec": [
                            "// Set common variables",
                            "pm.collectionVariables.set('timestamp', new Date().getTime());"
                        ]
                    }
                }
            ],
            "item": [],
            "variable": [
                {
                    "key": "base_url",
                    "value": "{{base_url}}",
                    "type": "string"
                }
            ]
        }
        
        # Group endpoints by tags
        grouped_paths = {}
        for path, path_item in schema.get('paths', {}).items():
            for method, operation in path_item.items():
                if method.upper() in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
                    tags = operation.get('tags', ['Untagged'])
                    tag = tags[0] if tags else 'Untagged'
                    
                    if tag not in grouped_paths:
                        grouped_paths[tag] = []
                    
                    grouped_paths[tag].append({
                        'path': path,
                        'method': method.upper(),
                        'operation': operation
                    })
        
        # Convert to Postman items
        for tag, endpoints in grouped_paths.items():
            folder = {
                "name": tag,
                "item": []
            }
            
            for endpoint in endpoints:
                item = self.create_postman_item(endpoint)
                folder['item'].append(item)
            
            collection['item'].append(folder)
        
        return collection

    def create_postman_item(self, endpoint):
        """Create a Postman request item from endpoint data."""
        operation = endpoint['operation']
        
        # Base request structure
        request = {
            "name": operation.get('summary', f"{endpoint['method']} {endpoint['path']}"),
            "request": {
                "method": endpoint['method'],
                "header": [
                    {
                        "key": "Content-Type",
                        "value": "application/json",
                        "type": "text"
                    },
                    {
                        "key": "Accept",
                        "value": "application/json",
                        "type": "text"
                    }
                ],
                "url": {
                    "raw": "{{base_url}}" + endpoint['path'],
                    "host": ["{{base_url}}"],
                    "path": endpoint['path'].strip('/').split('/'),
                    "query": []
                }
            }
        }
        
        # Add description
        if operation.get('description'):
            request['request']['description'] = operation['description']
        
        # Add authentication for protected endpoints
        if 'security' in operation:
            request['request']['auth'] = {
                "type": "bearer",
                "bearer": [
                    {
                        "key": "token",
                        "value": "{{jwt_token}}",
                        "type": "string"
                    }
                ]
            }
        
        # Add request body for POST/PUT/PATCH
        if endpoint['method'] in ['POST', 'PUT', 'PATCH']:
            request_body = operation.get('requestBody', {})
            if request_body:
                content = request_body.get('content', {})
                json_content = content.get('application/json', {})
                
                if json_content:
                    example = self.get_example_from_schema(json_content.get('schema', {}))
                    request['request']['body'] = {
                        "mode": "raw",
                        "raw": json.dumps(example, indent=2),
                        "options": {
                            "raw": {
                                "language": "json"
                            }
                        }
                    }
        
        # Add query parameters
        parameters = operation.get('parameters', [])
        for param in parameters:
            if param.get('in') == 'query':
                request['request']['url']['query'].append({
                    "key": param['name'],
                    "value": self.get_example_value(param.get('schema', {})),
                    "description": param.get('description', ''),
                    "disabled": not param.get('required', False)
                })
        
        # Add path variables
        path_params = [p for p in parameters if p.get('in') == 'path']
        if path_params:
            request['request']['url']['variable'] = []
            for param in path_params:
                request['request']['url']['variable'].append({
                    "key": param['name'],
                    "value": self.get_example_value(param.get('schema', {})),
                    "description": param.get('description', '')
                })
        
        # Add response examples
        responses = operation.get('responses', {})
        if responses:
            request['response'] = []
            for status_code, response in responses.items():
                if status_code.startswith('2'):  # Success responses
                    example_response = {
                        "name": f"Success ({status_code})",
                        "originalRequest": request['request'].copy(),
                        "status": response.get('description', 'OK'),
                        "code": int(status_code),
                        "header": [
                            {
                                "key": "Content-Type",
                                "value": "application/json"
                            }
                        ]
                    }
                    
                    # Add response body
                    content = response.get('content', {})
                    json_content = content.get('application/json', {})
                    if json_content:
                        example_body = self.get_example_from_schema(
                            json_content.get('schema', {})
                        )
                        example_response['body'] = json.dumps(example_body, indent=2)
                    
                    request['response'].append(example_response)
        
        return request

    def get_example_from_schema(self, schema):
        """Generate example data from JSON schema."""
        if 'example' in schema:
            return schema['example']
        
        schema_type = schema.get('type', 'object')
        
        if schema_type == 'object':
            example = {}
            properties = schema.get('properties', {})
            for prop_name, prop_schema in properties.items():
                example[prop_name] = self.get_example_value(prop_schema)
            return example
        
        elif schema_type == 'array':
            items_schema = schema.get('items', {})
            return [self.get_example_value(items_schema)]
        
        else:
            return self.get_example_value(schema)

    def get_example_value(self, schema):
        """Get example value for a schema type."""
        if 'example' in schema:
            return schema['example']
        
        schema_type = schema.get('type', 'string')
        schema_format = schema.get('format')
        
        examples = {
            'string': {
                'email': 'user@example.com',
                'uuid': str(uuid.uuid4()),
                'date': '2024-01-15',
                'date-time': '2024-01-15T10:30:00Z',
                'phone': '+8801712345678',
                'default': 'example string'
            },
            'integer': 42,
            'number': 42.0,
            'boolean': True,
            'array': [],
            'object': {}
        }
        
        if schema_type == 'string' and schema_format:
            return examples['string'].get(schema_format, examples['string']['default'])
        
        return examples.get(schema_type, 'example')

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
                    "type": "text"
                },
                {
                    "key": "jwt_token",
                    "value": "",
                    "enabled": True,
                    "type": "secret"
                },
                {