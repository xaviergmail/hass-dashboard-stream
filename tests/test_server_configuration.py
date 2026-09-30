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


if __name__ == "__main__":
    unittest.main()
