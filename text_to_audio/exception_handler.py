"""Custom DRF exception handler for consistent error response format.

AIDEV-NOTE: All API errors return {"error": "msg"} with optional {"fields": {...}} for field-level errors (#195)
"""

from rest_framework.views import exception_handler as drf_exception_handler


def api_exception_handler(exc, context):
    """Normalize all DRF error responses into a consistent envelope.

    Response shapes:
      - Field-level: {"error": "Validation failed.", "fields": {"speed": [...]}}
      - Non-field:   {"error": "Human-readable message."}
      - 404/429/etc: {"error": "Human-readable message."}

    Non-DRF exceptions return None (fall through to Django's handler).
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    data = response.data

    if isinstance(data, dict):
        # Already has "error" key as only/primary key — pass through
        if "error" in data and len(data) <= 2:
            return response
        # Has "detail" key (DRF default for NotFound, Throttled, etc.)
        if "detail" in data:
            response.data = {"error": str(data["detail"])}
            return response
        # AIDEV-NOTE: DRF wraps validate() errors as {"non_field_errors": ["msg"]}
        # Extract as top-level error message instead of treating as field errors
        if "non_field_errors" in data and len(data) == 1:
            errors = data["non_field_errors"]
            response.data = {"error": str(errors[0]) if errors else "Validation failed."}
            return response
        # Field-level errors dict — wrap in envelope
        response.data = {"error": "Validation failed.", "fields": data}
    elif isinstance(data, list):
        # Non-field errors as list
        response.data = {"error": str(data[0]) if data else "Validation failed."}

    return response
