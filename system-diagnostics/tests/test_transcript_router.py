"""Tests for transcript_router, including the Antigravity golden-output guard (decision D4)."""

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
for p in (HERE.parent / "scripts", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import transcript_auditor as ta  # noqa: E402
import transcript_router as tr  # noqa: E402
from _claude_fixtures import rec, result, session, text, use, write_jsonl  # noqa: E402

GEMINI_STEPS = [
    {"type": "USER_INPUT", "content": "<USER_REQUEST>do it</USER_REQUEST>"},
    {"type": "PLANNER_RESPONSE", "model": "m1", "content": "git commit hint", "tool_calls": [
        {"name": "read_file", "args": {"Path": "a.py"}}, {"name": "run_command", "args": {"CommandLine": "python -m unittest x"}}]},
    {"type": "GENERIC", "content": "Command exited with code 2\nboom", "status": "DONE"},
    {"type": "GENERIC", "content": "ok", "status": "DONE"},
]
GOLDEN_MD = (
    "| cid | steps | fails | subagents | dup reads | grade cap |\n|---|---:|---:|---:|---:|:--:|\n"
    "| abcd1234 | 4 | 1 | 0 | 0 | A |\n\n- FAIL abcd1234: step 2 cmd_fail (a.py): boom\n"
)
GOLDEN_KEYS = (
    "cid steps planner_turns models observed_models tool_calls failures total_failures audit_catches tooling_cli_fails "
    "failure_samples user_corrections workflow_redirects subagents reads_after_subagent reads_while_pending "
    "subagent_overlap_reads repeated_reads parallel_same_file_edits plan_mode_calls schedule_while_subagent has_debug_retro "
    "has_commit_hint has_learning_block cdp_live_fallbacks cdp_live_failures changelog_adds suggested_grade_cap"
).split()


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.brain, self.claude = root / "brain", root / "projects"
        self.brain.mkdir()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("TRANSCRIPT_VENDOR", None)

    def _gemini(self, cid: str = "abcd1234-0000") -> None:
        write_jsonl(self.brain / cid / ".system_generated" / "logs" / "transcript.jsonl", GEMINI_STEPS)

    def _cli(self, **kw: object) -> tuple[int, str, str]:
        ns = dict(brain_dir=str(self.brain), claude_dir=str(self.claude), cids=None, latest=None, json=False)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ta.cmd_transcript_audit(argparse.Namespace(**{**ns, **kw}))
        return code, out.getvalue(), err.getvalue()


class TestAntigravityGolden(_Base):
    def test_markdown_output_is_byte_identical(self) -> None:
        self._gemini()
        code, out, _ = self._cli(cids=["abcd1234"])
        self.assertEqual((code, out), (0, GOLDEN_MD))

    def test_json_row_has_exactly_the_legacy_keys_and_matches_the_reader(self) -> None:
        self._gemini()
        _, out, _ = self._cli(cids=["abcd1234"], json=True)
        row = json.loads(out)[0]
        self.assertEqual(list(row), GOLDEN_KEYS)
        self.assertEqual(row, ta.audit_conversation(self.brain, "abcd1234-0000"))

    def test_unknown_id_is_missing_exit_1(self) -> None:
        code, out, _ = self._cli(cids=["nope"])
        self.assertEqual((code, "MISSING" in out), (1, True))


class TestClaudeRows(_Base):
    def _session(self, sid: str = "c1c1c1c1-0000", **kw: object) -> Path:
        return session(self.claude, sid, [
            rec("user", text("go")),
            rec("assistant", use("1", "Edit", file_path="/p/a.py"), use("2", "Edit", file_path="/p/a.py"),
                use("3", "Read", file_path="/p/a.py"), use("4", "Bash", command="false"), use("5", "Agent", prompt="x"),
                model="claude-x", usage={"input_tokens": 2, "output_tokens": 3}),
            rec("user", result("4", "Exit code 1\nbad", error=True), result("3", "fine")),
            rec("assistant", use("6", "Read", file_path="/p/a.py")),
        ], **kw)

    def test_row_has_common_keys_plus_vendor_fields(self) -> None:
        self._session(subagents={"x": [rec("assistant", use("9", "Bash", command="boom"), use("8", "Read", file_path="/z"))]})
        row = tr.audit("c1c1c1c1", "auto", self.brain, self.claude)
        self.assertTrue(set(GOLDEN_KEYS) <= set(row), set(GOLDEN_KEYS) - set(row))
        self.assertEqual((row["vendor"], row["session_id"], row["models"]), ("claude", "c1c1c1c1-0000", ["claude-x"]))
        self.assertEqual(row["tokens"], {"input": 2, "output": 3, "cache_read": 0, "cache_creation": 0})
        self.assertEqual((row["steps"], row["total_failures"], row["failures"]), (7, 1, {"cmd_fail": 1}))
        self.assertEqual(row["parallel_same_file_edits"], [{"step": 1, "path": "/p/a.py", "calls": 2}])
        self.assertEqual(row["repeated_reads"], {"/p/a.py": 2})
        self.assertEqual(len(row["subagents"]), 1)

    def test_markdown_renders_a_claude_row(self) -> None:
        self._session()
        code, out, _ = self._cli(cids=["c1c1c1c1"])
        self.assertEqual(code, 0)
        self.assertIn("| c1c1c1c1 | 7 | 1 | 1 | 0 | A |", out)

    def test_mixed_audit_returns_both_rows(self) -> None:
        self._gemini()
        self._session()
        _, out, _ = self._cli(cids=["abcd1234", "c1c1c1c1"], json=True)
        self.assertEqual([r.get("vendor") for r in json.loads(out)], [None, "claude"])

    def test_same_id_in_both_roots_exits_2(self) -> None:
        self._gemini("c1c1c1c1-0000")
        self._session()
        code, out, err = self._cli(cids=["c1c1c1c1-0000"])
        self.assertEqual((code, out, "--vendor" in err), (2, "", True))
        self.assertEqual(self._cli(cids=["c1c1c1c1-0000"], vendor="claude")[0], 0)

    def test_ambiguous_claude_prefix_is_reported_not_guessed(self) -> None:
        self._session("dddddddd-1")
        self._session("dddddddd-2")
        row = tr.audit("dddddddd", "claude", self.brain, self.claude)
        self.assertEqual((row["missing"], row["ambiguous"]), (True, ["dddddddd-1", "dddddddd-2"]))
        self.assertEqual(tr.audit("dddd", "claude", self.brain, self.claude), {"cid": "dddd", "missing": True})

    def test_output_never_contains_raw_transcript_text(self) -> None:
        session(self.claude, "eeee0001", [rec("user", text("SECRET-PROMPT")), rec("assistant", text("SECRET-REPLY"))])
        _, out, _ = self._cli(cids=["eeee0001"], json=True)
        self.assertNotIn("SECRET", out)


if __name__ == "__main__":
    unittest.main()
