import unittest
from pathlib import Path


class RokuScreensaverTests(unittest.TestCase):
    root = Path("roku-screensaver")

    def test_screensaver_package_has_required_layout(self):
        self.assertTrue((self.root / "manifest").is_file())
        self.assertTrue((self.root / "source" / "main.brs").is_file())
        self.assertTrue((self.root / "components" / "ScreensaverScene.xml").is_file())
        self.assertTrue((self.root / "components" / "ScreensaverScene.brs").is_file())
        self.assertTrue((self.root / "images" / "placeholder.png").is_file())

    def test_screensaver_uses_required_entrypoint_and_manifest(self):
        manifest = (self.root / "manifest").read_text()
        source = (self.root / "source" / "main.brs").read_text()
        self.assertIn("screensaver_title=", manifest)
        self.assertIn("ui_resolutions=fhd", manifest)
        self.assertIn("Function RunScreenSaver(", source)
        self.assertNotIn("RunUserInterface", source)
        self.assertNotIn("Function Main(", source)

    def test_screensaver_uses_lossless_double_buffered_snapshot_scene(self):
        source = (self.root / "components" / "ScreensaverScene.brs").read_text()
        scene = (self.root / "components" / "ScreensaverScene.xml").read_text()
        self.assertIn("/snapshot.png", source)
        self.assertIn('m.posterA.setField("uri"', source)
        self.assertIn('m.posterB.setField("uri"', source)
        self.assertIn('id="posterA"', scene)
        self.assertIn('id="posterB"', scene)
        self.assertIn('duration="1.0"', scene)


if __name__ == "__main__":
    unittest.main()
