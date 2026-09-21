from __future__ import annotations

import asyncio
from urllib.parse import urlsplit, urlunsplit


def resolve_dashboard_url(
    dashboard_url: str,
    home_assistant_url: str,
    kiosk_mode: bool,
) -> tuple[str, str | None]:
    """Return the browser URL and origin used for Home Assistant auth."""
    if not dashboard_url:
        raise ValueError("dashboard_url must not be empty")

    parsed = urlsplit(dashboard_url)
    if parsed.scheme and parsed.netloc:
        base_url = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        full_url = dashboard_url
    elif dashboard_url.startswith("/"):
        base_url = home_assistant_url.rstrip("/")
        base = urlsplit(base_url)
        if not base.scheme or not base.netloc:
            raise ValueError("home_assistant_url must be an absolute URL")
        full_url = f"{base_url}{dashboard_url}"
    else:
        return dashboard_url, None

    if kiosk_mode and "kiosk" not in full_url.lower():
        full_url = f"{full_url}&kiosk" if "?" in full_url else f"{full_url}?kiosk"

    return full_url, base_url


def put_latest(queue: asyncio.Queue, frame: bytes) -> bool:
    """Put a frame into a one-slot queue, replacing stale data when full."""
    try:
        queue.put_nowait(frame)
        return False
    except asyncio.QueueFull:
        queue.get_nowait()
        queue.put_nowait(frame)
        return True


class LatestFrameStore:
    """In-memory store for the newest JPEG and its monotonic timestamp."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._jpeg: bytes | None = None
        self._captured_at: float | None = None

    async def update(self, jpeg: bytes, captured_at: float) -> None:
        async with self._lock:
            self._jpeg = jpeg
            self._captured_at = captured_at

    async def get(self) -> tuple[bytes, float] | None:
        async with self._lock:
            if self._jpeg is None or self._captured_at is None:
                return None
            return self._jpeg, self._captured_at


def retry_delay_seconds(attempt: int) -> int:
    """Return bounded exponential backoff for a one-based retry attempt."""
    return min(30, 2 ** max(0, attempt - 1))
