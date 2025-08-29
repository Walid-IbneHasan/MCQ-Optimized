from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that provides consistent error responses.
    """
    response = exception_handler(exc, context)

    if response is not None:
        # Log the error
        logger.error(f"API Error: {exc} - Context: {context}")

        # Create custom error response
        custom_response_data = {
            "error": True,
            "message": "An error occurred",
            "details": response.data if hasattr(response, "data") else str(exc),
            "status_code": (
                response.status_code if hasattr(response, "status_code") else 500
            ),
        }

        # Customize message based on error type
        if response.status_code == 400:
            custom_response_data["message"] = "Bad request"
        elif response.status_code == 401:
            custom_response_data["message"] = "Authentication required"
        elif response.status_code == 403:
            custom_response_data["message"] = "Permission denied"
        elif response.status_code == 404:
            custom_response_data["message"] = "Resource not found"
        elif response.status_code == 429:
            custom_response_data["message"] = "Rate limit exceeded"
        elif response.status_code >= 500:
            custom_response_data["message"] = "Internal server error"

        response.data = custom_response_data

    return response
