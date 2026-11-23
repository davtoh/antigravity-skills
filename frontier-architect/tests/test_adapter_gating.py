"""Adapter gating: one merged skill, Gemini vocabulary allowed only when mapped for Claude."""

import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REFS = SKILL_DIR / "references"
ADAPTER = REFS / "claude-adapter.md"

# Antigravity-only vocabulary that must never be left unexplained for a Claude run.
GEMINI_TOKENS = [
    "ask_question", "RequestFeedback", "appDataDir", "run_command", "view_file", "read_file",
    "edit_file", "WaitMsBeforeAsync", "manage_task", "manage_subagents", "invoke_subagent",
    "enter_plan_mode", "exit_plan_mode", "search_marketplace", "useG1Credits",
]
_TOKEN_RE = re.compile("|".join(re.escape(t) for t in GEMINI_TOKENS))
_CLAUDE_HINT = re.compile(
    r"Claude|AskUserQuestion|Antigravity|Explore|ExitPlanMode|EnterPlanMode|\.TODO|claude-adapter|"
    r"Bash|ToolSearch|`Read`|`Edit`|\.frontier/scratch|TaskStop"
)


class TestAdapterGating(unittest.TestCase):
    def test_skill_md_lines_with_gemini_terms_name_the_claude_equivalent(self):
        """Every SKILL.md line that uses a Gemini-only term also carries its Claude equivalent."""
        lines = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").splitlines()
        bad = [f"L{i}: {l.strip()[:90]}" for i, l in enumerate(lines, 1)
               if _TOKEN_RE.search(l) and not _CLAUDE_HINT.search(l)]
        self.assertEqual(bad, [], "Ungated Gemini terms in SKILL.md:\n" + "\n".join(bad))

    def test_skill_md_points_to_adapter_first(self):
        head = "\n".join((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").splitlines()[:16])
        self.assertIn("claude-adapter.md", head)

    def test_references_with_gemini_terms_carry_adapter_banner(self):
        """A reference that uses Gemini terms must link the adapter within its first 15 lines."""
        missing = []
        for ref in sorted(REFS.glob("*.md")):
            if ref == ADAPTER:
                continue
            text = ref.read_text(encoding="utf-8")
            if _TOKEN_RE.search(text) and "claude-adapter" not in "\n".join(text.splitlines()[:15]):
                missing.append(ref.name)
        self.assertEqual(missing, [], f"References missing the adapter banner: {missing}")

    def test_every_gemini_term_in_use_is_mapped_in_the_adapter(self):
        adapter = ADAPTER.read_text(encoding="utf-8")
        used = set()
        for path in [SKILL_DIR / "SKILL.md", *REFS.glob("*.md")]:
            if path != ADAPTER:
                used |= set(_TOKEN_RE.findall(path.read_text(encoding="utf-8")))
        unmapped = sorted(t for t in used if t not in adapter)
        self.assertEqual(unmapped, [], f"Gemini terms used but not mapped in claude-adapter.md: {unmapped}")

    def test_scripts_do_not_hardcode_a_single_platform_path(self):
        """Scripts must not require ~/.gemini; the Claude locations must be searched too."""
        for name in ("cdp_inspect.py", "docker_audit.py"):
            text = (SKILL_DIR / "scripts" / name).read_text(encoding="utf-8")
            self.assertIn(".claude", text, f"{name} does not search Claude install paths")


if __name__ == "__main__":
    unittest.main()
