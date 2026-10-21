import importlib.util
import unittest
from pathlib import Path


class ServerConfigurationTests(unittest.TestCase):
    source = Path("rootfs/usr/src/app/server.py").read_text()

    def test_single_process_pi_workaround_is_removed(self):
        self.assertNotIn('"--single-process"', self.source)

    def test_server_uses_stream_core_url_resolver(self):
        self.assertIn("resolve_dashboard_url", self.source)

    def test_server_has_configurable_home_assistant_url(self):
        self.assertIn('config.get("home_assistant_url")', self.source)

    def test_capture_defaults_are_uhd_4k(self):
        spec = importlib.util.spec_from_file_location(
            "dashboard_streams_server", "rootfs/usr/src/app/server.py"
        )
        if spec is None:
            self.fail("could not load server module spec")
        module = importlib.util.module_from_spec(spec)
        if spec.loader is None:
            self.fail("server module spec has no loader")
        spec.loader.exec_module(module)

        self.assertEqual(module.DEFAULT_WIDTH, 3840)
        self.assertEqual(module.DEFAULT_HEIGHT, 2160)

    def test_auto_refresh_detects_home_assistant_updates(self):
        self.assertIn("get_config", self.source)
        self.assertIn("Home Assistant version changed", self.source)
        self.assertIn("connection.socket?.readyState", self.source)
        self.assertIn("setInterval(checkHomeAssistantHealth", self.source)


if __name__ == "__main__":
    unittest.main()
