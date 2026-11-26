#!/usr/bin/env python3
"""Workflow docs for observations must point at real commands and keep the router light."""

import re
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REFS = SKILL_DIR / "references"
DIAGNOSE = SKILL_DIR / "scripts" / "diagnose.py"
DOC = (REFS / "observations.md").read_text(encoding="utf-8")
CLI_REF = (REFS / "cli-reference.md").read_text(encoding="utf-8")
SKILL = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


class TestObservationDocs(unittest.TestCase):
    def test_skill_points_to_observations_doc(self):
        self.assertIn("(./references/observations.md)", SKILL)

    def test_commands_use_skill_dir_form(self):
        self.assertNotIn("skills/system-diagnostics/scripts", DOC)
        self.assertIn('python "<skill_dir>/scripts/diagnose.py"', DOC)

    def test_documented_flags_exist_in_cli(self):
        helps = []
        for sub in (["observations", "--help"], ["brief", "--help"]):
            out = subprocess.run([sys.executable, str(DIAGNOSE), *sub], capture_output=True, text=True, timeout=60)
            helps.append(out.stdout)
        help_text = "\n".join(helps)
        flags = set(re.findall(r"`?(--[a-z][a-z-]+)", DOC + CLI_REF.split("`observations` & `brief`")[-1].split("## 2.")[0]))
        for flag in flags:
            self.assertIn(flag, help_text, f"documented flag missing from CLI: {flag}")

    def test_privacy_rules_stated(self):
        for needle in ("never leave the machine", "--allow-remote", "FRONTIER_DEBUG_OBSERVATIONS"):
            self.assertIn(needle, DOC)


if __name__ == "__main__":
    unittest.main()
