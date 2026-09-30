import asyncio
import unittest

from stream_core import (
    LatestFrameStore,
    put_latest,
    resolve_dashboard_url,
    retry_delay_seconds,
)


class ResolveDashboardUrlTests(unittest.TestCase):
    def test_relative_path_uses_configured_origin(self):
        full_url, base_url = resolve_dashboard_url(
            "/air-quality/0",
            home_assistant_url="http://homeassistant:8123",
            kiosk_mode=True,
        )
        self.assertEqual(
            full_url,
            "http://homeassistant:8123/air-quality/0?kiosk",
        )
        self.assertEqual(base_url, "http://homeassistant:8123")

    def test_existing_query_gets_kiosk_without_duplication(self):
        full_url, _ = resolve_dashboard_url(
            "/lovelace/0?foo=bar",
            home_assistant_url="http://ha.local:8123/",
            kiosk_mode=True,
        )
        self.assertEqual(full_url, "http://ha.local:8123/lovelace/0?foo=bar&kiosk")

        already_kiosk, _ = resolve_dashboard_url(
            "/lovelace/0?kiosk",
            home_assistant_url="http://ha.local:8123",
            kiosk_mode=True,
        )
        self.assertEqual(already_kiosk, "http://ha.local:8123/lovelace/0?kiosk")

    def test_absolute_url_is_preserved(self):
        full_url, base_url = resolve_dashboard_url(
            "https://demo.home-assistant.io/lovelace/0",
            home_assistant_url="http://unused:8123",
            kiosk_mode=False,
        )
        self.assertEqual(full_url, "https://demo.home-assistant.io/lovelace/0")
        self.assertEqual(base_url, "https://demo.home-assistant.io")


class LatestFrameQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_queue_discards_old_frame(self):
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait(b"old")

        dropped = put_latest(queue, b"new")

        self.assertTrue(dropped)
        self.assertEqual(await queue.get(), b"new")

    async def test_empty_queue_keeps_new_frame(self):
        queue = asyncio.Queue(maxsize=1)

        dropped = put_latest(queue, b"new")

        self.assertFalse(dropped)
        self.assertEqual(await queue.get(), b"new")


class LatestFrameStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_store_has_no_frame(self):
        store = LatestFrameStore()
        self.assertIsNone(await store.get())

    async def test_store_returns_latest_jpeg_and_timestamp(self):
        store = LatestFrameStore()
        await store.update(b"jpeg-new", 123.0)
        self.assertEqual(await store.get(), (b"jpeg-new", 123.0))


class RetryDelayTests(unittest.TestCase):
    def test_retry_delay_is_bounded_exponential_backoff(self):
        self.assertEqual(retry_delay_seconds(1), 1)
        self.assertEqual(retry_delay_seconds(3), 4)
        self.assertEqual(retry_delay_seconds(99), 30)


if __name__ == "__main__":
    unittest.main()
