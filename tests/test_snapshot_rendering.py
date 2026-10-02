import io
import importlib.util
import unittest
from pathlib import Path

from PIL import Image


SERVER_PATH = Path("rootfs/usr/src/app/server.py")


def load_server_module():
    spec = importlib.util.spec_from_file_location("dashboard_streams_snapshot_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SnapshotRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = load_server_module()

    def test_snapshot_removes_uniform_left_rail_and_preserves_canvas_size(self):
        image = Image.new("RGB", (192, 108), (16, 16, 16))
        for x in range(64, 192):
            for y in range(108):
                image.putpixel((x, y), (40 + (x % 80), 80, 140))
        source = io.BytesIO()
        image.save(source, format="PNG")

        jpeg = self.server.png_to_jpeg(source.getvalue(), quality=95)
        rendered = Image.open(io.BytesIO(jpeg))

        self.assertEqual(rendered.size, (192, 108))
        self.assertNotEqual(rendered.getpixel((0, 54)), (16, 16, 16))

    def test_snapshot_quality_is_high_by_default(self):
        image = Image.new("RGB", (192, 108))
        for x in range(192):
            for y in range(108):
                image.putpixel((x, y), ((x * 37 + y * 13) % 256, (x * 17 + y * 29) % 256, (x * 7 + y * 43) % 256))
        source = io.BytesIO()
        image.save(source, format="PNG")

        jpeg = self.server.png_to_jpeg(source.getvalue())

        self.assertGreater(len(jpeg), 1000)


if __name__ == "__main__":
    unittest.main()
