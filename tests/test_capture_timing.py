import asyncio
import importlib.util
import unittest
from pathlib import Path


SERVER_PATH = Path("rootfs/usr/src/app/server.py")


def load_server_module():
    spec = importlib.util.spec_from_file_location("dashboard_streams_server_timing", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CaptureTimingTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()

    async def test_unchanged_screenshot_is_still_encoded_for_wall_clock_timing(self):
        class Capture:
            async def capture_frame(self):
                return b"same-frame", False

        class FrameStore:
            async def update(self, jpeg, captured_at):
                raise AssertionError("unchanged frames must not update the snapshot store")

        frame_queue = asyncio.Queue(maxsize=1)
        task = asyncio.create_task(
            self.server.capture_loop(
                Capture(),
                frame_queue,
                FrameStore(),
                {"fps": 30},
            )
        )
        try:
            await asyncio.sleep(0.02)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        self.assertEqual(await frame_queue.get(), b"same-frame")


if __name__ == "__main__":
    unittest.main()
