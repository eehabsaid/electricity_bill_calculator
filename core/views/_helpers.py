"""Small shared helpers for the plain-JsonResponse view style (no DRF)."""
import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse


def parse_json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def bad_request(message, status=400):
    return JsonResponse({"error": message}, status=status)


def not_found(message="Not found"):
    return JsonResponse({"error": message}, status=404)


def as_decimal(value, field_name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError(f"'{field_name}' must be a valid number.")
