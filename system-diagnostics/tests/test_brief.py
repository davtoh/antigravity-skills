import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import brief
import brief_sections as sec
import observation_store as store

DIAGNOSE = str(SCRIPTS / "diagnose.py")
ORDER = ["Git", "Plans", "Observations", "Defects", "Traces", "Probes", "Architecture"]


class BriefTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.ws = Path(self._td.name).resolve()

    def titles(self, report):
        return [s["title"] for s in report["sections"]]

    def test_fixed_order_and_unavailable_isolation(self):
        report = brief.build(self.ws)
        self.assertEqual(self.titles(report), ORDER)
        by = {s["key"]: s for s in report["sections"]}
        self.assertEqual(by["git"]["status"], "unavailable")
        self.assertTrue(by["defects"]["lines"][0].startswith("UNAVAILABLE"))
        self.assertEqual(by["observations"]["status"], "ok")

    def test_collector_crash_does_not_stop_others(self):
        with mock.patch.object(sec, "plans", side_effect=RuntimeError("boom")):
            patched = tuple((k, t, c, (sec.plans if k == "plans" else f)) for k, t, c, f in brief.SECTIONS)
            with mock.patch.object(brief, "SECTIONS", patched):
                report = brief.build(self.ws)
        by = {s["key"]: s for s in report["sections"]}
        self.assertEqual(by["plans"]["lines"], ["UNAVAILABLE (boom)"])
        self.assertEqual(by["observations"]["status"], "ok")

    def test_observations_grouped_and_capped(self):
        for i in range(40):
            store.add_observation(self.ws, {"kind": "element", "page_path": "/p", "selector": f"#b{i}", "message": f"broken {i}"})
        store.add_observation(self.ws, {"kind": "idea", "page_path": "/p", "message": "add dark mode"})
        by = {s["key"]: s for s in brief.build(self.ws)["sections"]}
        lines = by["observations"]["lines"]
        self.assertLessEqual(len(lines), 30)
        self.assertTrue(lines[0].startswith("Findings (40)"))
        self.assertIn("more", lines[-1])

    def test_total_cap_keeps_every_header(self):
        report = brief.build(self.ws, max_lines=10)
        self.assertEqual(self.titles(report), ORDER)
        self.assertLessEqual(len(brief.render(report).splitlines()), 20)

    def test_probes_never_run_by_default(self):
        with mock.patch("probe_runner.run_probe") as rp:
            brief.build(self.ws)
        rp.assert_not_called()

    def test_run_probes_labels_fresh_and_infra_not_pass(self):
        d = self.ws / ".diagnostics" / "probes"
        d.mkdir(parents=True)
        (d / "stub.py").write_text('import json\nprint(json.dumps({"status": "INFRA_UNAVAILABLE", "summary": "no chrome", "details": {}}))\n', encoding="utf-8")
        by = {s["key"]: s for s in brief.build(self.ws, run_probes=True)["sections"]}
        line = next(ln for ln in by["probes"]["lines"] if "stub" in ln)
        self.assertIn("INFRA_UNAVAILABLE", line)
        self.assertIn("fresh", line)
        self.assertNotIn(": ok", line)

    def test_pull_runs_before_observations_and_failure_is_reported(self):
        with mock.patch("observation_pull.pull", side_effect=RuntimeError("refused")):
            by = {s["key"]: s for s in brief.build(self.ws, pull_url="http://127.0.0.1:9")["sections"]}
        self.assertIn("pull failed: refused", by["observations"]["lines"][0])

    def test_cli_json_and_usage_error(self):
        p = subprocess.run([sys.executable, DIAGNOSE, "brief", "--path", str(self.ws), "--json"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0)
        self.assertEqual([s["title"] for s in json.loads(p.stdout)["sections"]], ORDER)
        bad = subprocess.run([sys.executable, DIAGNOSE, "brief", "--path", str(self.ws), "--max-lines", "0"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)

    def test_brief_writes_nothing_without_run_probes(self):
        before = {p for p in self.ws.rglob("*")}
        brief.build(self.ws)
        self.assertEqual({p for p in self.ws.rglob("*")}, before)


if __name__ == "__main__":
    unittest.main()
