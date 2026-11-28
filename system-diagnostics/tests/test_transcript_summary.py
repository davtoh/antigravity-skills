"""Tests for transcript_summary: metrics-only export that survives log cleanup (decision D7)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parent / "scripts", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import transcript_summary as ts  # noqa: E402


class TestSummary(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.row = {"cid": "abcdef12-3456", "vendor": "claude", "steps": 7, "failure_samples": ["x" * 300], "tokens": {"input": 1}}

    def test_export_writes_vendor_id8_file_with_clamped_strings(self) -> None:
        path = ts.export_summary(self.root, self.row)
        self.assertEqual(path, self.root / ".diagnostics" / "retro" / "claude-abcdef12.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((data["steps"], len(data["failure_samples"][0])), (7, 120))

    def test_missing_row_is_not_exported(self) -> None:
        self.assertIsNone(ts.export_summary(self.root, {"cid": "abcdef12", "missing": True}))
        self.assertFalse((self.root / ".diagnostics").exists())

    def test_read_summary_by_prefix_labels_from_summary(self) -> None:
        ts.export_summary(self.root, self.row)
        got = ts.read_summary(self.root, "abcdef12")
        self.assertEqual((got["steps"], got["from_summary"]), (7, True))

    def test_read_summary_short_or_unknown_token_is_none(self) -> None:
        ts.export_summary(self.root, self.row)
        self.assertIsNone(ts.read_summary(self.root, "abc"))
        self.assertIsNone(ts.read_summary(self.root, "zzzzzzzz"))

    def test_corrupt_summary_is_skipped(self) -> None:
        folder = self.root / ".diagnostics" / "retro"
        folder.mkdir(parents=True)
        (folder / "claude-abcdef12.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(ts.read_summary(self.root, "abcdef12"))


if __name__ == "__main__":
    unittest.main()
