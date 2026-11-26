"""Tests for plan_sessions (ledger) and the plan_transcripts vendor routing (isolated temp workspaces)."""

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
SCRIPTS = HERE.parent / "scripts"
for p in (SCRIPTS, HERE.parent.parent / "system-diagnostics" / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import plan_digest as pd  # noqa: E402
import plan_engine  # noqa: E402
import plan_sessions as ps  # noqa: E402
import plan_transcripts as pt  # noqa: E402

PLAN = "# Demo Plan\n\n## Milestone 1: Core\n- [ ] **a.py**: add\n\n## Milestone 2: UI\n- [ ] **b.py**: add\n"
SID = "cccccccc-1111-2222-3333-444444444444"


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / ".TODO").mkdir()
        (self.root / ".TODO" / "demo.md").write_text(PLAN, encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": SID})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ledger = self.root / ".frontier" / "sessions.jsonl"

    def _lines(self) -> list[dict]:
        return [json.loads(x) for x in self.ledger.read_text(encoding="utf-8").splitlines()]


class TestLedger(_Base):
    def test_record_writes_contract_line(self) -> None:
        self.assertTrue(ps.record_session(self.root, "demo", 1, "advance"))
        line = self._lines()[0]
        self.assertEqual((line["v"], line["plan"], line["milestone"], line["event"], line["vendor"], line["session_id"], line["inferred"]),
                         (1, "demo", 1, "advance", "claude", SID, False))
        self.assertRegex(line["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_same_event_is_idempotent_different_event_appends(self) -> None:
        ps.record_session(self.root, "demo", 1, "advance")
        self.assertFalse(ps.record_session(self.root, "demo", 1, "advance"))
        self.assertTrue(ps.record_session(self.root, "demo", 1, "retrospective"))
        self.assertEqual(len(self._lines()), 2)

    def test_unknown_session_writes_nothing_and_notices(self) -> None:
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": "", "CLAUDECODE": "1"}), contextlib.redirect_stderr(err):
            self.assertFalse(ps.record_session(self.root, "demo", 1, "advance"))
        self.assertFalse(self.ledger.exists())
        self.assertIn("nothing recorded", err.getvalue())

    def test_unknown_event_and_bad_milestone_are_normalized(self) -> None:
        ps.record_session(self.root, "demo", None, "weird")  # type: ignore[arg-type]
        line = self._lines()[0]
        self.assertEqual((line["event"], line["milestone"]), ("manual", None))

    def test_advance_hook_appends_ledger_line(self) -> None:
        plan_engine.main(["init", ".TODO/demo.md"], root=self.root)
        with contextlib.redirect_stdout(io.StringIO()):
            plan_engine.main(["advance", "demo", "--milestone", "1"], root=self.root)
        events = [(l["plan"], l["milestone"], l["event"]) for l in self._lines()]
        self.assertIn(("demo", 1, "advance"), events)


class TestTranscriptRouting(_Base):
    def test_resolve_prefix_of_claude_session_and_dedupe(self) -> None:
        claude = self.root / "projects"
        (claude / "-p").mkdir(parents=True)
        (claude / "-p" / f"{SID}.jsonl").write_text(json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "hi"}]}}) + "\n", encoding="utf-8")
        brain = self.root / "brain"
        brain.mkdir()
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.root)}):
            self.assertEqual(pt._resolve_one_cid(brain, SID[:8]), SID)
            self.assertEqual(pt._dedupe_cids([SID[:8], SID], brain), [SID])
            row = pt.audit_single_cid(SID[:8], str(brain))
            rows = pt._transcript_rows([SID], str(brain))
        self.assertEqual((row["vendor"], row["cid"]), ("claude", SID))
        self.assertEqual(rows[0]["steps"], 1)

    def test_plan_digest_reexports_for_existing_imports_and_patches(self) -> None:
        for name in ("audit_single_cid", "_transcript_rows", "_dedupe_cids", "_resolve_one_cid", "_load_auditor"):
            self.assertIs(getattr(pd, name), getattr(pt, name))

    def test_unknown_cid_stays_missing_gemini_default(self) -> None:
        brain = self.root / "brain"
        brain.mkdir()
        self.assertIsNone(pt.audit_single_cid("nonexistent-id", str(brain)))

    def test_plan_digest_under_budget(self) -> None:
        self.assertLess(len((SCRIPTS / "plan_digest.py").read_text(encoding="utf-8").splitlines()), 350)


if __name__ == "__main__":
    unittest.main()
