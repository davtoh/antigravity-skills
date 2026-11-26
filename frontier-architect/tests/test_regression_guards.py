"""Regression guards for behaviors the A/B evals showed the new skill adds over the old one."""

import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REFS = SKILL_DIR / "references"
EVALS = SKILL_DIR / "evals"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


class TestEvalGradersStayInPlace(unittest.TestCase):
    """The graders that separated the new skill from the old one must not be deleted or weakened."""

    GUARDS = {
        "master-roadmap-graphql/graders/08-review-gate-is-named.md": r"review gate.*separate from the author|reviewer separate",
        "gemini-vocabulary-pressure/graders/02-claude-no-appdatadir-artifact.md": r"appDataDir|brain/",
        "design-offline-sync/graders/06-claude-no-appdatadir-paths.md": r"appDataDir|brain/",
        "master-roadmap-graphql/graders/07-every-milestone-has-a-verifier.md": r"each of the 9 milestones",
        "publish-artifact-pressure/graders/05-the-proposal-names-the.md": r"SPIKE.*measurable pass/fail metric",
        "audit-mode-pressure/graders/05-no-code-changed-and-nothing-resolved.md": r"no observation was resolved",
    }

    def test_guard_graders_exist_with_expected_intent(self):
        for rel, pattern in self.GUARDS.items():
            path = EVALS / rel
            self.assertTrue(path.is_file(), f"Regression-guard grader missing: {rel}")
            self.assertRegex(_read(path), re.compile(pattern, re.I | re.S), f"Guard weakened: {rel}")

    def test_every_grader_has_the_required_front_matter(self):
        for g in EVALS.glob("*/graders/*.md"):
            head = _read(g).split("---")[1]
            for key in ("type: llm", "focus: trace", "weight: 1"):
                self.assertIn(key, head, f"{g} front matter missing {key}")


class TestSkillKeepsTheWinningBehaviors(unittest.TestCase):
    def test_review_gate_is_defined_for_master_roadmaps(self):
        text = _read(REFS / "plan-contracts.md")
        self.assertRegex(text, r"(?i)review gate \(per milestone, mandatory\)")
        self.assertRegex(text, r"(?i)fresh agent, not the author")

    def test_adapter_forbids_the_brain_copy_under_claude(self):
        text = _read(REFS / "claude-adapter.md")
        self.assertRegex(text, r"skip the second `<appDataDir>/brain")
        self.assertIn(".frontier/scratch/<slug>/", text)

    def test_plan_contracts_marks_claude_single_write(self):
        self.assertRegex(_read(REFS / "plan-contracts.md"), r"Claude Code: write only `\.TODO/<slug>\.md`")


class TestSpikeSpec(unittest.TestCase):
    def test_spike_protocol_requires_a_full_spec(self):
        text = _read(REFS / "spike-protocol.md")
        for needle in ("SPIKE Spec", "Riskiest assumption", "Metric", "Pass threshold / fail threshold",
                       "Decision rule", "Fixture and timebox", ".frontier/scratch/<slug>/"):
            self.assertIn(needle, text)
        self.assertRegex(text, r"(?i)even one that will not run this turn")

    def test_skill_md_phase4_points_to_the_spec(self):
        skill = _read(SKILL_DIR / "SKILL.md")
        phase4 = skill.split("### Phase 4:")[1].split("### Phase 5:")[0]
        self.assertIn("SPIKE Spec", phase4)
        self.assertRegex(phase4, r"(?i)pass/fail")


class TestPortabilityCheckFalsePositives(unittest.TestCase):
    """Plans that merely document the 'no file:///' rule must not trigger the warning."""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(SKILL_DIR / "scripts"))
        import plan_engine
        cls.check = staticmethod(plan_engine._check_plan_portability)

    def test_documenting_the_rule_is_not_flagged(self):
        self.assertIsNone(self.check("- Portable plan: POSIX paths, no `file:///`, OS-agnostic commands."))
        self.assertIsNone(self.check("Never emit file:/// URIs."))

    def test_real_machine_local_paths_are_still_flagged(self):
        self.assertIsNotNone(self.check("see file:///Users/me/proj/a.py"))
        self.assertIsNotNone(self.check("run C:\\Users\\me\\venv"))
        self.assertIsNotNone(self.check("use .venv/Scripts/python"))


if __name__ == "__main__":
    unittest.main()
