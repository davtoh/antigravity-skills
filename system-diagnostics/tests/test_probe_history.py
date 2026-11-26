import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import probe_history
import probe_runner


class ProbeHistoryTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.ws = Path(self._td.name).resolve()

    def test_record_and_load(self):
        probe_history.record(self.ws, {"probe": "p1", "status": "ok", "summary": "fine", "latency_ms": 5})
        h = probe_history.load(self.ws)
        self.assertEqual(h["p1"]["status"], "ok")
        self.assertIn("ran_at", h["p1"])

    def test_corrupt_file_is_empty(self):
        (self.ws / ".diagnostics").mkdir()
        (self.ws / ".diagnostics" / "probe_last_run.json").write_text("{nope", encoding="utf-8")
        self.assertEqual(probe_history.load(self.ws), {})

    def test_age_labels(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(probe_history.age((now - timedelta(minutes=5)).isoformat(), now), "5m")
        self.assertEqual(probe_history.age((now - timedelta(hours=3)).isoformat(), now), "3h")
        self.assertEqual(probe_history.age((now - timedelta(days=2)).isoformat(), now), "2d")
        self.assertEqual(probe_history.age("garbage"), "unknown")

    def test_run_probe_stub_records_and_infra_not_pass(self):
        d = self.ws / ".diagnostics" / "probes"
        d.mkdir(parents=True)
        (d / "stub.py").write_text('import json\nprint(json.dumps({"status": "INFRA_UNAVAILABLE", "summary": "no chrome", "details": {}}))\n', encoding="utf-8")
        res = probe_runner.run_probe("stub", workspace_root=self.ws, timeout=20)
        self.assertEqual(res["status"], "INFRA_UNAVAILABLE")
        self.assertEqual(probe_history.load(self.ws)["stub"]["status"], "INFRA_UNAVAILABLE")

    def test_missing_probe_not_recorded(self):
        probe_runner.run_probe("does_not_exist_xyz", workspace_root=self.ws)
        self.assertEqual(probe_history.load(self.ws), {})


if __name__ == "__main__":
    unittest.main()
