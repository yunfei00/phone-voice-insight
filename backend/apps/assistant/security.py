from __future__ import annotations

# ruff: noqa: RUF001
import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings
from rest_framework import serializers


def validate_ai_endpoint(url: str, *, provider: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise serializers.ValidationError("模型地址必须是合法的 HTTP/HTTPS 地址，且不能包含账号密码。")
    host = parsed.hostname.lower().rstrip(".")
    private_allowlist = {str(item).lower().rstrip(".") for item in settings.ASSISTANT_AI_PRIVATE_HOST_ALLOWLIST}
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise serializers.ValidationError("模型地址无法完成 DNS 解析。") from exc
    blocked = [address for address in addresses if not ipaddress.ip_address(address).is_global]
    if blocked and host not in private_allowlist:
        raise serializers.ValidationError("模型地址指向未授权的内网或本机服务，已拒绝访问。")
    if provider == "ollama" and blocked and host not in private_allowlist:
        raise serializers.ValidationError("本地 Ollama 地址必须由管理员加入受信任白名单。")
    return url.rstrip("/")
