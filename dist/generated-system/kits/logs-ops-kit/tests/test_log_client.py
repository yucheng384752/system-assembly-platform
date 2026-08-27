import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "src/backend/app/core/log_client.py"
MONITORING_PATH = Path(__file__).parents[1] / "src/backend/app/core/monitoring.py"
httpx = types.ModuleType("httpx")
httpx.HTTPError = type("HTTPError", (Exception,), {})
httpx.post = unittest.mock.Mock()
sys.modules.setdefault("httpx", httpx)
SPEC = importlib.util.spec_from_file_location("log_client", MODULE_PATH)
log_client = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(log_client)
MONITORING_SPEC = importlib.util.spec_from_file_location("monitoring", MONITORING_PATH)
monitoring = importlib.util.module_from_spec(MONITORING_SPEC)
assert MONITORING_SPEC and MONITORING_SPEC.loader
MONITORING_SPEC.loader.exec_module(monitoring)


class LogCollectClientTest(unittest.TestCase):
    @patch.object(log_client.httpx, "post")
    @patch.object(log_client.socket, "gethostname", return_value="test-host")
    def test_heartbeat_payload_contains_only_machine_state(self, _hostname, post):
        post.return_value.raise_for_status.return_value = None

        sent = log_client.LogCollectClient("https://monitor.test", "test-source").send_heartbeat()

        self.assertTrue(sent)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(set(payload), {"source", "host", "state", "timestamp"})
        self.assertEqual(payload | {"timestamp": "ignored"}, {
            "source": "test-source",
            "host": "test-host",
            "state": "alive",
            "timestamp": "ignored",
        })

    def test_empty_monitor_url_does_not_start_heartbeat_thread(self):
        monitoring._monitor_client = None
        monitoring._heartbeat_thread = None

        with (
            patch.object(monitoring, "_ensure_initialized"),
            patch.object(monitoring, "_enqueue"),
            patch.object(monitoring.threading, "Thread") as thread,
        ):
            monitoring.init_monitoring(server_url="")
            monitoring.start_heartbeat()

        thread.assert_not_called()
        self.assertIsNone(monitoring._heartbeat_thread)


if __name__ == "__main__":
    unittest.main()
