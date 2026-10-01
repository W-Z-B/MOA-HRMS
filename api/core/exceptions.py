"""One shape for every refusal: {"code": ..., "detail": ...}.

Views already answer that way. Errors raised by the framework itself (not signed in, no permission,
not found, too many requests) carried only "detail"; this adds the code, so the web app can tell "your
session ended" from "you may not do that" without reading sentences. Field validation errors keep their
per-field shape.
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None or not isinstance(response.data, dict):
        return response
    # The framework turns Django's own errors into its equivalents only inside its handler; do the same
    # here so that their codes are known.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    if "detail" in response.data and "code" not in response.data:
        codes = exc.get_codes() if hasattr(exc, "get_codes") else None
        response.data["code"] = codes if isinstance(codes, str) else getattr(exc, "default_code", "error")
    return response
