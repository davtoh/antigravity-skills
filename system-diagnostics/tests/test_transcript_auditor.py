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
            {
                "type": "USER_INPUT",
                "content": (
                    "<USER_REQUEST>\nModel Selection` from A to Fake In User Prompt. No need\n</USER_REQUEST>\n"
                    "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection` from None to "
                    "Claude Sonnet 5.5 (Medium). No need to comment\n</USER_SETTINGS_CHANGE>"
                ),
            },
            _planner(("invoke_subagent", {"TypeName": "research", "Model": "flash"})),
            _planner(("read_file", {"Path": "a.py"}), ("read_file", {"Path": "a.py"})),
            {"type": "GENERIC", "content": "Showing lines 1-5\nModel Selection` from X to Fake Read. No need\n", "status": "DONE"},
            {"type": "GENERIC", "content": "Created At: x\nCommand exited with code 1.\n", "status": "DONE"},
            {"type": "GENERIC", "content": "Showing lines 1-3\nCommand exited with code 1", "status": "DONE"},
            {"type": "GENERIC", "content": "target content not found", "status": "ERROR"},
            {"type": "GENERIC", "content": "file does not exist", "status": "ERROR"},
            {"type": "GENERIC", "content": "Command exited with code 0.", "status": "DONE"},
        ])
        row = ta.audit_conversation(self.brain, "c1")
        self.assertEqual(row["failures"], {"cmd_fail": 1, "edit_fail": 1, "read_fail": 1})
        self.assertEqual(row["models"], ["Claude Sonnet 5.5 (Medium)"])
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

    def test_subagent_completion_clears_pending_and_ignores_edited_or_new_reads(self) -> None:
        _write(self.brain, "sub-1", [_planner(("read_file", {"Path": "already.py"}), ("read_file", {"Path": "edited.py"}))])
        _write(self.brain, "parent-1", [
            _planner(("invoke_subagent", {"TypeName": "research", "Model": "flash"})),
            {"type": "GENERIC", "content": '{"conversationId": "sub-1"}', "status": "DONE"},
            {"type": "SYSTEM_MESSAGE", "content": "[Message] sender=sub-1 content=summary", "status": "DONE"},
            _planner(
                ("read_file", {"Path": "fresh.py"}),
                ("read_file", {"Path": "edited.py"}),
                ("edit_file", {"Path": "edited.py", "Target": "a", "Replacement": "b"}),
                ("read_file", {"Path": "already.py"}),
            ),
        ])
        row = ta.audit_conversation(self.brain, "parent-1")
        self.assertEqual(row["reads_while_pending"], 0)
        self.assertEqual(row["subagent_overlap_reads"], 1)
        self.assertEqual(row["reads_after_subagent"], 1)

    def test_reads_while_pending_and_markdown_dup_reads_flag(self) -> None:
        _write(self.brain, "parent-2", [
            _planner(("invoke_subagent", {"TypeName": "research", "Model": "flash"})),
            _planner(
                ("read_file", {"Path": "a.py"}), ("read_file", {"Path": "b.py"}),
                ("read_file", {"Path": "c.py"}), ("read_file", {"Path": "d.py"}),
                ("read_file", {"Path": "e.py"}),
            ),
        ])
        row = ta.audit_conversation(self.brain, "parent-2")
        self.assertEqual(row["reads_while_pending"], 5)
        self.assertEqual(row["reads_after_subagent"], 5)
        md = ta.format_markdown([row])
        self.assertIn("| dup reads |", md)
        self.assertIn("5 subagent duplicate reads (5 pending + 0 unedited overlap)", md)

    def test_prefix_and_comma_separated_cids(self) -> None:
        _write(self.brain, "20aa8189-94b2-4ab5", [_planner()])
        _write(self.brain, "7dba2e24-97af-455c", [_planner()])
        resolved = ta._resolve_cids(self.brain, ["20aa8189,7dba2e24"], None)
        self.assertEqual(resolved, ["20aa8189-94b2-4ab5", "7dba2e24-97af-455c"])

    def test_latest_prefers_substantive_conversations(self) -> None:
        import os
        import time
        _write(self.brain, "older-long", [_planner() for _ in range(7)])
        _write(self.brain, "newer-short", [_planner(), _planner()])
        old_log = self.brain / "older-long" / ".system_generated" / "logs" / "transcript.jsonl"
        new_log = self.brain / "newer-short" / ".system_generated" / "logs" / "transcript.jsonl"
        now = time.time()
        os.utime(old_log, (now - 100, now - 100))
        os.utime(new_log, (now, now))
        self.assertEqual(ta._resolve_cids(self.brain, None, 1, min_steps=6), ["older-long"])

    def test_markdown_includes_fail_repeat_and_correction(self) -> None:
        _write(self.brain, "diag-1", [
            {"type": "USER_INPUT", "content": "<USER_REQUEST>\nNo, fix parser instead\n</USER_REQUEST>"},
            _planner(("read_file", {"Path": "foo.py"}), ("read_file", {"Path": "foo.py"})),
            _planner(("run_command", {"CommandLine": "pytest tests/test_foo.py"})),
            {"type": "GENERIC", "content": "Created At: x\nCommand exited with code 1.\nCommand output:\nAssertionError: boom\nLog: file:///x.log\n</SYSTEM_MESSAGE>\n", "status": "DONE"},
        ])
        row = ta.audit_conversation(self.brain, "diag-1")
        self.assertEqual(len(row["failure_samples"]), 1)
        self.assertEqual(len(row["user_corrections"]), 1)
        md = ta.format_markdown([row])
        self.assertIn("- FAIL diag-1:", md)
        self.assertIn("AssertionError: boom", md)
        self.assertNotIn("</SYSTEM_MESSAGE>", md)
        self.assertIn("- REPEAT diag-1: foo.py (2x)", md)
        self.assertIn("- CORRECTION diag-1: step 0: No, fix parser instead", md)

    def test_git_grep_exit_1_not_counted_as_cmd_fail(self) -> None:
        _write(self.brain, "grep-1", [
            _planner(("run_command", {"CommandLine": 'git grep -n "missing_sym" src/'})),
            {"type": "GENERIC", "content": "Command exited with code 1.\nNo output from the command.\n", "status": "DONE"},
            _planner(("run_command", {"CommandLine": 'git grep -n "[" src/'})),
            {"type": "GENERIC", "content": "Command exited with code 2.\nfatal: bad pattern\n", "status": "DONE"},
            _planner(("run_command", {"CommandLine": "pytest tests/"})),
            {"type": "GENERIC", "content": "Command exited with code 1.\n1 failed\n", "status": "DONE"},
        ])
        row = ta.audit_conversation(self.brain, "grep-1")
        self.assertEqual(row["failures"], {"cmd_fail": 2})
        self.assertEqual(row["total_failures"], 2)

    def test_parallel_call_target_attribution_and_audit_catch_exclusion(self) -> None:
        _write(self.brain, "fifo-1", [
            _planner(("read_file", {"Path": "missing.py"}), ("run_command", {"CommandLine": "git status -s"})),
            {"type": "GENERIC", "content": "file does not exist", "status": "ERROR"},
            {"type": "GENERIC", "content": "Command exited with code 0.\n", "status": "DONE"},
            _planner(("run_command", {"CommandLine": "python skills/system-diagnostics/scripts/diagnose.py audit --path a.py"})),
            {"type": "GENERIC", "content": "Command exited with code 1.\n[audit] DEFECTS_FOUND\n", "status": "DONE"},
        ])
        row = ta.audit_conversation(self.brain, "fifo-1")
        self.assertEqual(row["failures"], {"read_fail": 1})
        self.assertEqual(row["total_failures"], 1)
        self.assertEqual(row["audit_catches"], 1)
        self.assertIn("read_fail (missing.py)", row["failure_samples"][0])

    def test_scan_audit_catch_vs_traceback_and_empty_pending_calls(self) -> None:
        _write(self.brain, "scan-1", [
            {"type": "GENERIC", "content": "Command exited with code 1.\n", "status": "DONE"},
            _planner(("run_command", {"CommandLine": "python skills/system-diagnostics/scripts/diagnose.py scan --path src/"})),
            {"type": "GENERIC", "content": "Command exited with code 1.\n[scan] DEFECTS_FOUND\n", "status": "DONE"},
            _planner(("run_command", {"CommandLine": "python skills/system-diagnostics/scripts/diagnose.py scan --path src/"})),
            {"type": "GENERIC", "content": "Command exited with code 1.\nTraceback (most recent call last):\n", "status": "DONE"},
        ])
        row = ta.audit_conversation(self.brain, "scan-1")
        self.assertEqual(row["audit_catches"], 1)
        self.assertEqual(row["failures"], {"cmd_fail": 2})

    def test_background_task_attribution_beyond_400_chars(self) -> None:
        long_pad = "INFO line\n" * 50
        _write(self.brain, "bg-1", [
            _planner(("run_command", {"CommandLine": "pytest tests/test_slow.py"})),
            {"type": "GENERIC", "content": "Command running in the background with task id: task-1", "status": "DONE"},
            _planner(("edit_file", {"Path": "src/other.py"})),
            {"type": "GENERIC", "content": "Applied edit", "status": "DONE"},
            {"type": "SYSTEM_MESSAGE", "content": f"<SYSTEM_MESSAGE>\nsender=bg-1/task-1\n{long_pad}Command exited with code 1.\nAssertionError: bg fail\n</SYSTEM_MESSAGE>", "status": "DONE"},
        ])
        row = ta.audit_conversation(self.brain, "bg-1")
        self.assertEqual(row["failures"], {"cmd_fail": 1})
        self.assertIn("pytest tests/test_slow.py", row["failure_samples"][0])
        self.assertNotIn("other.py", row["failure_samples"][0])

    def test_step0_spec_prose_with_instead_not_flagged_as_correction(self) -> None:
        _write(self.brain, "spec-1", [
            {"type": "USER_INPUT", "content": "<USER_REQUEST>\nImplement Wagtail hybrid CMS instead of duplicating JSON tables, and do not break existing routes.\n</USER_REQUEST>"},
            _planner(("read_file", {"Path": "app.py"})),
        ])
        row = ta.audit_conversation(self.brain, "spec-1")
        self.assertEqual(row["user_corrections"], [])

    def test_flags_cdp_fallbacks_repeat_changelog_and_read_fail_guesses(self) -> None:
        _write(self.brain, "waste-1", [
            _planner(("read_file", {"Path": "missing1.py"}), ("read_file", {"Path": "missing2.py"})),
            {"type": "GENERIC", "content": "file does not exist", "status": "ERROR"},
            {"type": "GENERIC", "content": "file does not exist", "status": "ERROR"},
            _planner(("run_command", {"CommandLine": "python diagnose.py changelog add --title A"})),
            {"type": "GENERIC", "content": "[CDP] Live connection failed (TimeoutError).", "status": "DONE"},
            _planner(("run_command", {"CommandLine": "python diagnose.py changelog add --title B"})),
            {"type": "GENERIC", "content": "Command exited with code 0.", "status": "DONE"},
        ])
        row = ta.audit_conversation(self.brain, "waste-1")
        self.assertEqual(row["cdp_live_fallbacks"], 1)
        self.assertEqual(row["changelog_adds"], 2)
        md = ta.format_markdown([row])
        self.assertIn("CDP --live->headless fallback", md)
        self.assertIn("2 changelog add calls", md)
        self.assertIn("2 read_fail path-guess errors", md)


if __name__ == "__main__":
    unittest.main()
