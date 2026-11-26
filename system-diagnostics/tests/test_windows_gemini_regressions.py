#!/usr/bin/env python3
"""Regression tests for Windows + Gemini parity (user_rejected & .sh LF staging)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import skill_packager as sp  # noqa: E402
import transcript_auditor as ta  # noqa: E402


def _write_gemini(brain: Path, cid: str, steps: list[dict]) -> None:
    log = brain / cid / ".system_generated" / "logs"
    log.mkdir(parents=True, exist_ok=True)
    (log / "transcript.jsonl").write_bytes(("\n".join(json.dumps(s) for s in steps) + "\n").encode("utf-8"))


class TestGeminiUserRejectedParity(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.brain = Path(tmp.name).resolve()

    def test_gemini_user_rejected_or_canceled_not_counted_as_failure(self) -> None:
        _write_gemini(self.brain, "gem-rej-1", [
            {"type": "USER_INPUT", "content": "<USER_REQUEST>check git log</USER_REQUEST>"},
            {"type": "PLANNER_RESPONSE", "tool_calls": [
                {"name": "run_command", "args": {"CommandLine": "git log -2"}},
                {"name": "edit_file", "args": {"Path": "a.py"}},
            ]},
            {"type": "GENERIC", "content": "Tool execution was rejected by the user.", "status": "ERROR"},
            {"type": "GENERIC", "content": "Cancelled", "status": "CANCELED"},
        ])
        row = ta.audit_conversation(self.brain, "gem-rej-1")
        self.assertEqual(row["total_failures"], 0)
        self.assertEqual(row["failures"], {})
        self.assertEqual(row["user_rejected"], 2)
        self.assertEqual(row["suggested_grade_cap"], "A")
        md = ta.format_markdown([row])
        self.assertIn("- NOTE gem-rej-: 2 tool call(s) rejected by the user (not counted as failures)", md)
        self.assertNotIn("- FAIL", md)

    def test_normal_gemini_row_omits_user_rejected_key_for_d4_compat(self) -> None:
        _write_gemini(self.brain, "gem-clean-1", [
            {"type": "PLANNER_RESPONSE", "tool_calls": [
                {"name": "read_file", "args": {"Path": "test_transcript_claude_checks.py"}},
                {"name": "run_command", "args": {"CommandLine": "git diff --cached"}},
            ]},
            {"type": "GENERIC", "content": "Showing lines 1-5\nThe tool use was rejected", "status": "DONE"},
            {"type": "GENERIC", "content": "Command exited with code 0.\n+The user doesn't want to proceed", "status": "DONE"},
        ])
        row = ta.audit_conversation(self.brain, "gem-clean-1")
        self.assertNotIn("user_rejected", row)
        self.assertEqual(row["total_failures"], 0)


class TestSkillPackagerShellLfNormalization(unittest.TestCase):
    def test_stage_standalone_skill_converts_crlf_sh_scripts_to_lf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            fake_skill = root / "demo-skill"
            (fake_skill / "scripts").mkdir(parents=True)
            (fake_skill / "SKILL.md").write_bytes(b"---\r\nname: demo-skill\r\ndescription: demo\r\n---\r\n")
            (fake_skill / "scripts" / "py.sh").write_bytes(b"#!/bin/sh\r\necho ok\r\n")
            staging = root / "stage"
            staging.mkdir()
            staged = sp.stage_standalone_skill(fake_skill, staging)
            sh_bytes = (staged / "scripts" / "py.sh").read_bytes()
        self.assertEqual(sh_bytes, b"#!/bin/sh\necho ok\n")


if __name__ == "__main__":
    unittest.main()
