from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework.renderers import BaseRenderer


class EventStreamRenderer(BaseRenderer):
    """Allow DRF content negotiation for Server-Sent Events responses."""

    media_type = "text/event-stream"
    format = "sse"
    charset = "utf-8"
    render_style = "binary"

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,  # noqa: ARG002
        renderer_context: Mapping[str, Any] | None = None,  # noqa: ARG002
    ) -> bytes:
        # StreamingHttpResponse consumes the generator directly. This fallback
        # only applies when DRF needs to render an early validation/error response.
        if data is None:
            return b""
        return str(data).encode(self.charset)
