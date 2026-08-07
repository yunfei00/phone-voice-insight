"""统一 API 错误响应。"""

from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)
    if response is not None:
        response.data = {
            "status": "error",
            "code": getattr(exc, "default_code", "api_error"),
            "detail": response.data,
        }
    return response
