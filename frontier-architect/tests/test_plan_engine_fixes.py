"""Unit tests for Frontier Architect plan_engine fixes (concurrency, tactical master gate, commit hint)."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from plan_cli_helpers import print_master_gate, resolve_commit_hint
from plan_state import load_json, save_json


class TestPlanEngineFixes(unittest.TestCase):
    """Verify concurrent save_json, tactical master gate, and commit hint edge cases."""

    def test_concurrent_save_json_no_tmp_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "state.json"

            def _write(idx: int) -> None:
                save_json(target, {"worker": idx, "ok": True})

            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(_write, range(24)))

            data = load_json(target)
            self.assertIsInstance(data, dict)
            self.assertTrue(data.get("ok"))
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_tactical_master_gate_vs_full_gate(self):
        import io
        from contextlib import redirect_stdout

        ps = {"slug": "demo_master_roadmap", "title": "Demo Master", "child_plans": {}}
        buf_small = io.StringIO()
        with redirect_stdout(buf_small):
            print_master_gate(ps, 1, declared_child=None, tasks=[{"text": "one"}, {"text": "two"}])
        self.assertIn("MASTER STEP PRE-PLAN GATE (Step 1)", buf_small.getvalue())
        self.assertIn("Tactical Master Step", buf_small.getvalue())

        buf_large = io.StringIO()
        with redirect_stdout(buf_large):
            print_master_gate(ps, 2, declared_child=None, tasks=[{"text": str(i)} for i in range(4)])
        self.assertIn("MASTER STEP PRE-PLAN GATE (Step 2)", buf_large.getvalue())
        self.assertNotIn("Tactical Master Step", buf_large.getvalue())

    def test_resolve_commit_hint_precommitted_vs_audit_only(self):
        ps = {"slug": "step_4", "milestones": [{"index": 2, "title": "Verification"}]}
        hint_committed, has_diff = resolve_commit_hint(ps, 2, [], True, "b76f7a5")
        self.assertEqual(hint_committed, "(Already committed as b76f7a5)")
        self.assertTrue(has_diff)

        hint_audit, has_diff_audit = resolve_commit_hint(ps, 2, [], True, None)
        self.assertIn("verification/audit only", hint_audit)
        self.assertFalse(has_diff_audit)


if __name__ == "__main__":
    unittest.main()
