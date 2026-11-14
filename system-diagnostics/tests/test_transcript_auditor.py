"""Tests for transcript_auditor (isolated tmp brain dir; never touches the real brain)."""

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import transcript_auditor as ta  # noqa: E402


def _write(brain: Path, cid: str, steps: list[dict]) -> None:
    log = brain / cid / ".system_generated" / "logs"
    log.mkdir(parents=True)
    (log / "transcript.jsonl").write_bytes(("\n".join(json.dumps(s) for s in steps) + "\n").encode("utf-8"))


def _planner(*calls: tuple[str, dict]) -> dict:
    return {"type": "PLANNER_RESPONSE", "tool_calls": [{"name": n, "args": a} for n, a in calls]}


class TestTranscriptAuditor(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.brain = Path(self._tmp.name)

    def test_missing_conversation(self) -> None:
        self.assertTrue(ta.audit_conversation(self.brain, "nope")["missing"])

    def test_failures_models_and_subagent_duplication(self) -> None:
        _write(self.brain, "c1", [
            {"type": "USER_INPUT", "content": "Model Selection` from None to Gemini X. No need to comment"},
            _planner(("invoke_subagent", {"TypeName": "research", "Model": "flash"})),
            _planner(("read_file", {"Path": "a.py"}), ("read_file", {"Path": "a.py"})),
            {"type": "GENERIC", "content": "Created At: x\nCommand exited with code 1.\n", "status": "DONE"},
            {"type": "GENERIC", "content": "Showing lines 1-3\nCommand exited with code 1", "status": "DONE"},
            {"type": "GENERIC", "content": "target content not found", "status": "ERROR"},
            {"type": "GENERIC", "content": "file does not exist", "status": "ERROR"},
            {"type": "GENERIC", "content": "Command exited with code 0.", "status": "DONE"},
        ])
        row = ta.audit_conversation(self.brain, "c1")
        self.assertEqual(row["failures"], {"cmd_fail": 1, "edit_fail": 1, "read_fail": 1})
        self.assertEqual(row["models"], ["Gemini X"])
        self.assertEqual(row["reads_after_subagent"], 2)
        self.assertEqual(row["repeated_reads"], {"a.py": 2})
        self.assertEqual(row["suggested_grade_cap"], "A")

    def test_parallel_same_file_edits_flagged(self) -> None:
        _write(self.brain, "c2", [_planner(("edit_file", {"Path": "S.md"}), ("edit_file", {"Path": "S.md"}), ("edit_file", {"Path": "T.md"}))])
        edits = ta.audit_conversation(self.brain, "c2")["parallel_same_file_edits"]
        self.assertEqual(edits, [{"step": 0, "path": "S.md", "calls": 2}])

    def test_grade_cap_thresholds_and_malformed_lines(self) -> None:
        log = self.brain / "c3" / ".system_generated" / "logs"
        log.mkdir(parents=True)
        body = "not json\n" + "\n".join(json.dumps({"type": "GENERIC", "content": ""}) for _ in range(101)) + "\n"
        (log / "transcript.jsonl").write_bytes(body.encode("utf-8"))
        self.assertEqual(ta.audit_conversation(self.brain, "c3")["suggested_grade_cap"], "C")

    def test_cmd_latest_and_exit_codes(self) -> None:
        _write(self.brain, "c4", [_planner()])
        ns = argparse.Namespace(cids=None, latest=1, brain_dir=str(self.brain), json=True)
        self.assertEqual(ta.cmd_transcript_audit(ns), 0)
        ns_missing = argparse.Namespace(cids=["zzz"], latest=None, brain_dir=str(self.brain), json=False)
        self.assertEqual(ta.cmd_transcript_audit(ns_missing), 1)

    def test_json_encoded_string_arguments_are_decoded(self) -> None:
        _write(self.brain, "c5", [_planner(("invoke_subagent", {"TypeName": '"research"', "Model": '"flash"'}))])
        sub = ta.audit_conversation(self.brain, "c5")["subagents"][0]
        self.assertEqual((sub["type"], sub["model"]), ("research", "flash"))

    def test_default_brain_dir_honors_env(self) -> None:
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"AGY_BRAIN_DIR": self._tmp.name}):
            self.assertEqual(ta.default_brain_dir(), Path(self._tmp.name))


if __name__ == "__main__":
    unittest.main()
