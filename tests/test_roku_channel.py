import unittest
from pathlib import Path


class RokuSnapshotChannelTests(unittest.TestCase):
    root = Path("roku")

    def test_channel_has_manifest_and_scene(self):
        self.assertTrue((self.root / "manifest").is_file())
        self.assertTrue((self.root / "source" / "main.brs").is_file())
        self.assertTrue((self.root / "components" / "MainScene.xml").is_file())
        self.assertTrue((self.root / "components" / "MainScene.brs").is_file())

    def test_channel_uses_cached_snapshot_with_cache_busting(self):
        source = (self.root / "components" / "MainScene.brs").read_text()
        scene = (self.root / "components" / "MainScene.xml").read_text()
        self.assertIn("/snapshot.jpg", source)
        self.assertIn("?t=", source)
        self.assertIn('duration="1.0"', scene)
        self.assertIn("pkg:/components/MainScene.brs", scene)

    def test_addon_exposes_snapshot_endpoint(self):
        server = Path("rootfs/usr/src/app/server.py").read_text()
        self.assertIn('"/snapshot.jpg"', server)
        self.assertIn('"no-store, no-cache, must-revalidate"', server)


if __name__ == "__main__":
    unittest.main()
