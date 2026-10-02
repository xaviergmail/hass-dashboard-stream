import asyncio
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock


SERVER_PATH = Path("rootfs/usr/src/app/server.py")


def load_server_module():
    spec = importlib.util.spec_from_file_location("dashboard_streams_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CachedEndpointTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()

    async def asyncSetUp(self):
        self.capture = type("Capture", (), {"driver": object(), "kiosk_mode_detected": None})()
        self.encoder = type("Encoder", (), {"running": True})()
        self.store = self.server.LatestFrameStore()
        await self.store.update(b"cached-jpeg", asyncio.get_running_loop().time())
        self.png_store = self.server.LatestFrameStore()
        await self.png_store.update(b"cached-png", asyncio.get_running_loop().time())
        self.stream_server = self.server.StreamServer(
            self.capture,
            self.encoder,
            {"dashboard_url": "/lovelace/0"},
            self.store,
            self.png_store,
        )

    async def test_snapshot_uses_cached_bytes_without_capture(self):
        self.capture.capture_frame = AsyncMock(side_effect=AssertionError("must not capture"))
        response = await self.stream_server.handle_snapshot(None)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"cached-jpeg")
        self.assertEqual(response.content_type, "image/jpeg")
        self.assertIn("no-store", response.headers["Cache-Control"])

    async def test_snapshot_png_uses_cached_bytes_without_capture(self):
        response = await self.stream_server.handle_snapshot_png(None)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"cached-png")
        self.assertEqual(response.content_type, "image/png")
        self.assertIn("no-store", response.headers["Cache-Control"])

    async def test_health_reports_snapshot_and_frame_age(self):
        response = await self.stream_server.handle_health(None)
        payload = json.loads(response.text)
        self.assertEqual(payload["status"], "starting")
        self.assertTrue(payload["snapshot_ready"])
        self.assertIsInstance(payload["last_frame_age_ms"], int)
        self.assertTrue(payload["capture_ready"])


if __name__ == "__main__":
    unittest.main()
