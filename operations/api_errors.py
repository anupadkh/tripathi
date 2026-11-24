from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, OperationalError
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class Conflict(APIException):
    status_code = 409
    default_detail = "This record changed. Reload it before saving."
    default_code = "conflict"


def exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        return Response(
            getattr(exc, "message_dict", {"detail": exc.messages}), status=400
        )
    if isinstance(exc, IntegrityError):
        return Response(
            {"detail": "A unique or referenced record conflicts with this change."},
            status=409,
        )
    if isinstance(exc, OperationalError) and "locked" in str(exc).lower():
        return Response(
            {
                "detail": "Database is busy. Retry the request with the same idempotency key."
            },
            status=409,
        )
    return drf_exception_handler(exc, context)
