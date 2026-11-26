"""Tests for transcript_list: --list, --since, --plan, --export-summary and the deleted-log fallback."""

import argparse
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parent / "scripts", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import transcript_list as tl  # noqa: E402
from _claude_fixtures import rec, result, session, text, use  # noqa: E402
from test_transcript_router import _Base  # noqa: E402

SID_A, SID_B = "aaaaaaaa-1111-2222-3333-444444444444", "bbbbbbbb-1111-2222-3333-444444444444"


def _records(prompt: str, ts: str, branch: str = "feat/x") -> list:
    first = rec("user", text(prompt), ts=ts)
    first["gitBranch"] = branch
    return [first, rec("assistant", use("t1", "Bash", command="ls"), ts=ts), rec("user", result("t1", "ok"), ts=ts)]


class TestListAndPlan(_Base):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.brain.parent
        (self.root / ".TODO").mkdir()
        (self.root / ".TODO" / "my_plan.md").write_text("# plan\n", encoding="utf-8")
        session(self.claude, SID_A, _records("Continue my_plan please, " + "x" * 100, "2026-11-20T10:00:00Z"))
        session(self.claude, SID_B, _records("unrelated", "2026-11-26T10:00:00Z"))

    def _args(self, **kw: object) -> argparse.Namespace:
        base = dict(brain_dir=str(self.brain), claude_dir=str(self.claude), cids=None, latest=None, json=True, vendor="claude",
                    workspace=str(self.root), list=False, plan=None, since=None, limit=20, export_summary=False, no_snippet=False,
                    project_dir=None)
        return argparse.Namespace(**{**base, **kw})

    def _run(self, **kw: object) -> tuple[int, str]:
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tl.run_cli(self._args(**kw), self.brain, self.root)
        return code, out.getvalue()

    def test_list_lines_are_compact_with_60_char_prompt_and_plan_slug(self) -> None:
        code, out = self._run(list=True)
        lines = out.strip().splitlines()
        self.assertEqual((code, len(lines)), (0, 2))
        self.assertTrue(lines[1].startswith("aaaaaaaa | claude | 2026-11-20T10:00Z | 3 | feat/x | Continue my_plan"))
        self.assertTrue(lines[1].endswith("| my_plan"))
        self.assertLessEqual(len(lines[1].split(" | ")[5]), 60)

    def test_no_snippet_omits_prompt(self) -> None:
        _, out = self._run(list=True, no_snippet=True)
        self.assertNotIn("Continue", out)

    def test_since_filters_old_sessions(self) -> None:
        _, out = self._run(list=True, since="2026-11-25")
        self.assertEqual([l[:8] for l in out.splitlines()], ["bbbbbbbb"])

    def test_parse_since_relative_and_invalid(self) -> None:
        now = datetime(2026, 11, 26, tzinfo=timezone.utc)
        self.assertEqual(tl.parse_since("2d", now), datetime(2026, 11, 24, tzinfo=timezone.utc))
        self.assertIsNone(tl.parse_since("garbage"))

    def test_plan_reads_ledger_retros_and_labels_inferred(self) -> None:
        fr = self.root / ".frontier"
        (fr / "plans" / "my_plan").mkdir(parents=True)
        (fr / "sessions.jsonl").write_text("not json\n" + json.dumps({"v": 1, "plan": "my_plan", "session_id": SID_B, "inferred": False}) + "\n", encoding="utf-8")
        code, out = self._run(plan="my_plan")
        rows = {r["cid"][:8]: r for r in json.loads(out)}
        self.assertEqual(code, 0)
        self.assertEqual(set(rows), {"aaaaaaaa", "bbbbbbbb"})
        self.assertTrue(rows["aaaaaaaa"].get("inferred"))
        self.assertFalse(rows["bbbbbbbb"].get("inferred", False))

    def test_plan_unknown_slug_exit_1_no_rows(self) -> None:
        code, out = self._run(plan="nothing_here")
        self.assertEqual((code, json.loads(out)), (1, []))

    def test_export_summary_then_deleted_log_served_from_summary(self) -> None:
        (self.root / ".frontier").mkdir()
        (self.root / ".frontier" / "sessions.jsonl").write_text(json.dumps({"plan": "p", "session_id": SID_A}) + "\n", encoding="utf-8")
        self._run(plan="p", export_summary=True)
        saved = self.root / ".diagnostics" / "retro" / "claude-aaaaaaaa.json"
        self.assertTrue(saved.is_file())
        (self.claude / "-proj" / f"{SID_A}.jsonl").unlink()
        code, out = self._run(plan="p")
        row = json.loads(out)[0]
        self.assertEqual((code, row.get("from_summary"), row["steps"]), (0, True, 2))

    def test_plan_with_id_in_both_roots_exits_2_asking_for_vendor(self) -> None:
        self._gemini(SID_A)
        (self.root / ".frontier").mkdir()
        (self.root / ".frontier" / "sessions.jsonl").write_text(json.dumps({"plan": "p", "session_id": SID_A}) + "\n", encoding="utf-8")
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, _ = self._run(plan="p", vendor="auto")
        self.assertEqual(code, 2)
        self.assertIn("--vendor", err.getvalue())

    def test_plan_uses_ledger_vendor_to_resolve_ambiguity(self) -> None:
        self._gemini(SID_A)
        (self.root / ".frontier").mkdir()
        (self.root / ".frontier" / "sessions.jsonl").write_text(json.dumps({"plan": "p", "session_id": SID_A, "vendor": "claude"}) + "\n", encoding="utf-8")
        code, out = self._run(plan="p", vendor="auto")
        self.assertEqual((code, json.loads(out)[0]["vendor"]), (0, "claude"))

    def test_legacy_flags_without_new_options_still_work(self) -> None:
        code, out = self._run(cids=[SID_A[:8]])
        self.assertEqual((code, json.loads(out)[0]["vendor"]), (0, "claude"))


class TestDebugRetroVendor(_Base):
    def test_claude_id_telemetry_and_vendor_env_restored(self) -> None:
        import os
        import debug_retro as dr
        session(self.claude, SID_A, _records("hi", "2026-11-20T10:00:00Z"))
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.claude.parent)
        self.assertIn("steps=2", dr._audit_metrics(SID_A[:8], str(self.brain)))
        with dr._vendor_env("gemini"):
            self.assertEqual(os.environ["TRANSCRIPT_VENDOR"], "gemini")
            self.assertIn("(missing)", dr._audit_metrics(SID_A[:8], str(self.brain)))
        self.assertNotIn("TRANSCRIPT_VENDOR", os.environ)

    def test_gemini_id_metrics_unchanged(self) -> None:
        import debug_retro as dr
        self._gemini()
        self.assertEqual(dr._audit_metrics("abcd1234", str(self.brain)), "cid=abcd1234 steps=4 fails=1 cap=A cdp_fallbacks=0")


if __name__ == "__main__":
    unittest.main()
