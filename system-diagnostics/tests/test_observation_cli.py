import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DIAGNOSE = str(Path(__file__).resolve().parent.parent / "scripts" / "diagnose.py")


class CliTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.ws = Path(self._td.name).resolve()

    def run_cli(self, *args):
        p = subprocess.run([sys.executable, DIAGNOSE, "observations", *args], cwd=self.ws,
                           capture_output=True, text=True, encoding="utf-8")
        return p.returncode, p.stdout

    def add(self, msg="Save does nothing", kind="element"):
        return self.run_cli("add", "--kind", kind, "--page", "/dashboard", "--selector", "button#save", "--message", msg)

    def test_empty_list(self):
        self.assertEqual(self.run_cli("list"), (0, "No active observations.\n"))

    def test_add_list_json(self):
        self.assertEqual(self.add()[0], 0)
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn('OBS-001 [open] element /dashboard button#save "Save does nothing" (1x,', out)
        data = json.loads(self.run_cli("list", "--json")[1])
        self.assertEqual(set(data[0]), {"id", "fingerprint", "status", "kind", "page_path", "selector", "message", "occurrence_count", "last_seen"})

    def test_show_and_usage_errors(self):
        self.assertEqual(self.run_cli("show", "--id", "OBS-999")[0], 1)
        self.add()
        self.assertEqual(self.run_cli("resolve", "--id", "OBS-001")[0], 2)
        self.assertEqual(self.run_cli("triage", "--id", "OBS-001")[0], 2)
        self.assertEqual(self.run_cli("triage", "--id", "OBS-001", "--root-cause", "x", "--missed-by", "bogus")[0], 2)

    def test_triage_resolve_flow(self):
        self.add()
        code, _ = self.run_cli("triage", "--id", "OBS-001", "--root-cause", "stale handler",
                               "--missed-by", "tests,surface", "--guard", "add click test")
        self.assertEqual(code, 0)
        _, shown = self.run_cli("show", "--id", "OBS-001")
        self.assertIn("['tests', 'surface']", shown)
        self.assertIn("add click test", shown)
        self.assertEqual(self.run_cli("resolve", "--id", "OBS-001", "--resolution", "fixed", "--commit", "abc123")[0], 0)
        self.assertEqual(self.run_cli("list")[1], "No active observations.\n")
        self.assertIn("OBS-001 [resolved]", self.run_cli("list", "--status", "all")[1])

    def test_dismiss_and_kind_filter(self):
        self.add()
        self.add("Add a pause button", kind="idea")
        out = self.run_cli("list", "--kind", "idea")[1]
        self.assertIn("idea", out)
        self.assertNotIn("Save does nothing", out)
        self.assertEqual(self.run_cli("dismiss", "--id", "OBS-001", "--reason", "by design")[0], 0)
        self.assertEqual(self.run_cli("dismiss", "--id", "OBS-001")[0], 2)

    def test_utf8_output(self):
        self.add("Guardar no funciona – ñandú ✓")
        code, out = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("ñandú ✓", out)

    def test_resolve_provenance_auto_base_commit_and_confirm_roundtrip(self):
        subprocess.run(["git", "init"], cwd=self.ws, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.ws, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.ws, check=True, capture_output=True)
        (self.ws / "a.txt").write_text("hi\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=self.ws, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.ws, check=True, capture_output=True)
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=self.ws, check=True,
                              capture_output=True, text=True).stdout.strip()

        self.add()
        self.assertEqual(self.run_cli("confirm", "--id", "OBS-001")[0], 2)
        self.assertEqual(self.run_cli("confirm")[0], 2)

        code, _ = self.run_cli(
            "resolve", "--id", "OBS-001", "--resolution", "fixed handler",
            "--plan", "demo_plan", "--milestone", "M1", "--task", "task-2",
        )
        self.assertEqual(code, 0)
        entry = json.loads(self.run_cli("show", "--id", "OBS-001", "--json")[1])
        self.assertEqual(entry["resolved_plan"], "demo_plan")
        self.assertEqual(entry["resolved_milestone"], "M1")
        self.assertEqual(entry["resolved_task"], "task-2")
        self.assertEqual(entry["base_commit"], f"pending:{head}")

        code, out = self.run_cli("confirm", "--id", "OBS-001", "--note", "verified live")
        self.assertEqual(code, 0)
        self.assertIn("OBS-001 -> confirmed", out)
        confirmed = json.loads(self.run_cli("show", "--id", "OBS-001", "--json")[1])
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["confirmed_note"], "verified live")
        self.assertTrue(confirmed["confirmed_at"])
        self.assertIn("OBS-001 [confirmed]", self.run_cli("list", "--status", "confirmed")[1])
        _, text_show = self.run_cli("show", "--id", "OBS-001")
        self.assertIn("resolved_plan: demo_plan", text_show)
        self.assertIn("confirmed_note: verified live", text_show)


if __name__ == "__main__":
    unittest.main()
