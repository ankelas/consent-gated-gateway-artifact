import tempfile
import threading
import unittest
from pathlib import Path

from state_store import StateStore


class TelemetryStoreTests(unittest.TestCase):
    def test_span_is_persisted_without_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            with store.telemetry.span("inbound_event", attributes={
                "message_bytes": 12,
                "message_body": "secret",
                "caller_id": "+8613800000000",
            }):
                pass
            rows = store.telemetry_summary()
            self.assertEqual(rows[0]["operation"], "inbound_event")
            with store._connect() as conn:
                payload = conn.execute("SELECT attributes_json FROM telemetry_spans_v1").fetchone()[0]
            self.assertNotIn("secret", payload)
            self.assertNotIn("+8613800000000", payload)

    def test_event_claim_is_atomic_under_concurrency(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            barrier = threading.Barrier(8)
            results = []
            lock = threading.Lock()

            def claim():
                barrier.wait()
                result = store.claim_event("caller", "message")
                with lock:
                    results.append(result[0])

            threads = [threading.Thread(target=claim) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(results.count("claimed"), 1)
            self.assertEqual(results.count("processing"), 7)
            store.save_event_response("caller", "message", {"messages": ["done"]})
            self.assertEqual(store.claim_event("caller", "message"), ("completed", {"messages": ["done"]}))


if __name__ == "__main__":
    unittest.main()
