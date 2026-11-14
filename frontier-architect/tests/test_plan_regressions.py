#!/usr/bin/env python3
"""Targeted regression tests for recent frontier-architect script fixes."""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from plan_cli_helpers import _suggest_slice_tools
from plan_engine import main as engine_main
from plan_state import get_frontier_dir, load_json
from plan_telemetry import _upsert_retro


class TestFrontierRegressions(unittest.TestCase):
    """Verify PowerShell-safe slice tools and workspace-scoped retrospective upserts."""

    def test_slice_tools_never_emit_double_ampersand(self):
        """UI slice tool suggestions must not chain commands with PowerShell-incompatible &&."""
        tools = _suggest_slice_tools({"tasks": [{"text": "Update dashboard modal layout in app.js"}]})
        self.assertTrue(any("diagnose.py surface" in t for t in tools))
        self.assertTrue(any("diagnose.py ui" in t for t in tools))
        for cmd in tools:
            self.assertNotIn("&&", cmd)

    def test_upsert_retro_replaces_incomplete_entry_without_cid(self):
        """An incomplete entry without a CID is replaced when a complete entry arrives."""
        entries = [{"milestone_index": 1, "steps": None, "token_efficiency_grade": "A"}]
        _upsert_retro(entries, {"milestone_index": 1, "steps": 24, "retries": 0, "token_efficiency_grade": "A"})
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["steps"], 24)

    def test_workspace_retrospectives_isolate_plans_sharing_cid(self):
        """Two plans logging Milestone 1 under the same CID must not overwrite each other in state.json."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".TODO").mkdir()
            (root / ".TODO" / "alpha.md").write_text("# Alpha\n## Milestone 1: A\n- [ ] **a.py**: task\n", encoding="utf-8")
            (root / ".TODO" / "beta.md").write_text("# Beta\n## Milestone 1: B\n- [ ] **b.py**: task\n", encoding="utf-8")
            self.assertEqual(engine_main(["init", ".TODO/alpha.md"], root=root), 0)
            self.assertEqual(engine_main(["init", ".TODO/beta.md"], root=root), 0)
            cid = "11111111-2222-3333-4444-555555555555"
            self.assertEqual(engine_main(["retrospective", "alpha", "--milestone", "1", "--steps", "10", "--retries", "0", "--cid", cid], root=root), 0)
            self.assertEqual(engine_main(["retrospective", "beta", "--milestone", "1", "--steps", "15", "--retries", "0", "--cid", cid], root=root), 0)
            ws = load_json(get_frontier_dir(root) / "state.json", {})
            ws_retros = ws.get("retrospectives", [])
            self.assertEqual(len(ws_retros), 2)
            self.assertEqual({r.get("_slug") for r in ws_retros}, {"alpha", "beta"})


if __name__ == "__main__":
    unittest.main()
