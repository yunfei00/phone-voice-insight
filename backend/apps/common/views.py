"""系统健康检查。"""

from typing import Any

from django.conf import settings
from django.db import connections
from django.db.utils import DatabaseError
from drf_spectacular.utils import OpenApiResponse, extend_schema
from redis import Redis
from redis.exceptions import RedisError
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response


def get_redis_client() -> Redis:
    return Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)


@extend_schema(
    responses={200: OpenApiResponse(description="服务、数据库与 Redis 的基本状态")},
    tags=["system"],
)
@api_view(["GET"])
def health(request: Request) -> Response:  # noqa: ARG001
    checks: dict[str, str] = {"database": "ok", "redis": "ok"}
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        checks["database"] = "error"

    try:
        redis_result: Any = get_redis_client().ping()
        if not redis_result:
            checks["redis"] = "error"
    except (RedisError, OSError):
        checks["redis"] = "error"

    overall = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return Response(
        {
            "status": overall,
            "service": "phone-voice-insight-backend",
            **checks,
        }
    )
