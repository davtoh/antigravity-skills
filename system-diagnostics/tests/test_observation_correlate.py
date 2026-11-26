import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import observation_correlate as c  # noqa: E402


class CorrelateTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.dir = Path(self._td.name).resolve() / "traces"
        self.dir.mkdir()

    def write(self, day, events, raw=()):
        with open(self.dir / f"trace_{day}.jsonl", "a", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
            for line in raw:
                f.write(line + "\n")

    def test_exact_match(self):
        self.write("20261126", [
            {"fingerprint": "TRC-A-111111", "timestamp": "2026-11-26T10:00:00+00:00", "context": {"recording_id": "rec-1"}},
            {"fingerprint": "TRC-B-222222", "timestamp": "2026-11-26T10:00:00+00:00", "context": {"recording_id": "rec-2"}},
        ])
        self.assertEqual(c.correlate({"recording_id": "rec-1"}, self.dir), ["TRC-A-111111"])

    def test_window_edges(self):
        self.write("20261126", [
            {"fingerprint": "TRC-IN", "timestamp": "2026-11-26T10:00:12+00:00"},
            {"fingerprint": "TRC-OUT", "timestamp": "2026-11-26T10:00:12.1+00:00"},
            {"fingerprint": "TRC-LOW", "timestamp": "2026-11-26T09:59:58+00:00"},
        ])
        obs = {"window": {"started_at": "2026-11-26T10:00:00Z", "stopped_at": "2026-11-26T10:00:10Z"}}
        self.assertEqual(c.correlate(obs, self.dir), ["TRC-IN", "TRC-LOW"])

    def test_missing_dir_and_no_keys(self):
        self.assertEqual(c.correlate({"recording_id": "r"}, self.dir / "nope"), [])
        self.assertEqual(c.correlate({}, self.dir), [])

    def test_malformed_line_skipped(self):
        self.write("20261126", [{"fingerprint": "TRC-OK", "context": {"recording_id": "r"}}], raw=["{bad", "[1]"])
        self.assertEqual(c.correlate({"recording_id": "r"}, self.dir), ["TRC-OK"])

    def test_parse_iso_forms(self):
        self.assertEqual(c.parse_iso("2026-11-26T10:00:00Z"), c.parse_iso("2026-11-26T10:00:00+00:00"))
        self.assertIsNone(c.parse_iso("garbage"))

    def test_midnight_spans_two_files(self):
        self.write("20261126", [{"fingerprint": "TRC-D1", "timestamp": "2026-11-26T23:59:59+00:00"}])
        self.write("20261127", [{"fingerprint": "TRC-D2", "timestamp": "2026-11-27T00:00:01+00:00"}])
        obs = {"window": {"started_at": "2026-11-26T23:59:58Z", "stopped_at": "2026-11-27T00:00:00Z"}}
        self.assertEqual(c.correlate(obs, self.dir), ["TRC-D1", "TRC-D2"])


if __name__ == "__main__":
    unittest.main()
