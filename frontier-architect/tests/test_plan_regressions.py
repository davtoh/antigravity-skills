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

    def test_digest_dedupes_short_prefix_and_full_cid_across_entries_and_cli_args(self):
        """Passing a short CID prefix to digest must not duplicate a recorded full UUID."""
        import plan_digest as pd

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_text("# Demo\n## Milestone 1: A\n- [ ] **a.py**: task\n", encoding="utf-8")
            self.assertEqual(engine_main(["init", ".TODO/demo.md"], root=root), 0)
            full_cid = "9741e238-9bcb-4998-a0c7-f3914d12a749"
            retros_p = get_frontier_dir(root) / "plans" / "demo" / "retrospectives.json"
            retros_p.write_text(
                f'[{{"milestone_index": 1, "cid": "{full_cid}", "steps": 97, "retries": 3, "token_efficiency_grade": "B", "tool_reliability_scores": {{"overall": 5}}}}]',
                encoding="utf-8",
            )
            brain = root / "brain"
            log_dir = brain / full_cid / ".system_generated" / "logs"
            log_dir.mkdir(parents=True)
            (log_dir / "transcript.jsonl").write_text('{"type": "GENERIC", "content": "ok"}\n', encoding="utf-8")

            d_no_disk = pd.build_digest(root, "demo", cids=["9741e238", "9741E238"], brain_dir=str(root / "empty_brain"))
            self.assertEqual(d_no_disk["cids"], [full_cid])
            self.assertEqual([r["cid"] for r in d_no_disk["transcripts"]], [full_cid])

            d_disk = pd.build_digest(root, "demo", cids=["9741e238", "9741E238"], brain_dir=str(brain))
            self.assertEqual(d_disk["cids"], [full_cid])
            self.assertEqual([r["cid"] for r in d_disk["transcripts"]], [full_cid])

    def test_retrospective_emits_turn_end_echo_markdown_block(self):
        """plan_engine.py retrospective must emit a copy-pasteable Continuous Learning block."""
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".TODO").mkdir()
            (root / ".TODO" / "demo.md").write_text("# Demo\n## Milestone 1: A\n- [ ] **a.py**: task\n", encoding="utf-8")
            self.assertEqual(engine_main(["init", ".TODO/demo.md"], root=root), 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = engine_main([
                    "retrospective", "demo", "--milestone", "1", "--steps", "20", "--retries", "0",
                    "--went-well", "Fast verification", "--learn", "Keep CSS classes isolated",
                    "--skill-learn", "Echo turn-end summary",
                ], root=root)
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            self.assertIn("### Continuous Learning & Introspective Options", out)
            self.assertIn("- **What went well**: Fast verification", out)
            self.assertIn("- **`/learn` candidate (project)**: Keep CSS classes isolated", out)
            self.assertIn("- **`/learn` candidate (skill)**: Echo turn-end summary", out)
            self.assertIn("- **Introspective Options**: Review `.frontier/plans/demo/LEARNING_SCAFFOLD.md`", out)


if __name__ == "__main__":
    unittest.main()
