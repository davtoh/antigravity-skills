"""One fixture per Claude derivation row (Milestone 2), built from synthetic sessions only."""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parent / "scripts", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import transcript_claude_render as render  # noqa: E402
import transcript_router as tr  # noqa: E402
from _claude_fixtures import rec, result, session, text, use  # noqa: E402

GEMINI_KEYS = (
    "cid steps planner_turns models observed_models tool_calls failures total_failures audit_catches tooling_cli_fails "
    "failure_samples user_corrections workflow_redirects subagents reads_after_subagent reads_while_pending "
    "subagent_overlap_reads repeated_reads parallel_same_file_edits plan_mode_calls schedule_while_subagent has_debug_retro "
    "has_commit_hint has_learning_block cdp_live_fallbacks cdp_live_failures changelog_adds suggested_grade_cap"
).split()


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.claude, self.brain = self.root / "projects", self.root / "brain"
        self.brain.mkdir()

    def row(self, records: list, subagents: dict | None = None) -> dict:
        session(self.claude, "aaaa1111-0", records, subagents=subagents)
        return tr.audit("aaaa1111", "claude", self.brain, self.claude, workspace=self.root)


def bash(tid: str, cmd: str) -> dict:
    return use(tid, "Bash", command=cmd)


class TestFailures(_Base):
    def test_is_error_results_are_counted_by_tool_class(self) -> None:
        row = self.row([
            rec("user", text("go")),
            rec("assistant", bash("1", "false"), use("2", "Edit", file_path="/p/x.py"), use("3", "Read", file_path="/p/y.py"), use("4", "Grep", pattern="q")),
            rec("user", result("1", "Exit code 2\nboom", True), result("2", "no match", True), result("3", "missing", True), result("4", "bad", True)),
        ])
        self.assertEqual(row["failures"], {"cmd_fail": 1, "edit_fail": 1, "read_fail": 1, "tool_fail": 1})
        self.assertEqual(row["total_failures"], 4)
        self.assertEqual(len(row["failure_samples"]), 4)
        self.assertEqual(row["failure_samples"][0], "step 5 cmd_fail (false): boom")

    def test_nonzero_exit_without_is_error_counts_and_git_grep_miss_does_not(self) -> None:
        row = self.row([
            rec("assistant", bash("1", "make"), bash("2", "git grep nothing")),
            rec("user", result("1", "Exit code 2\nboom"), result("2", "Exit code 1")),
        ])
        self.assertEqual(row["failures"], {"cmd_fail": 1})

    def test_cli_usage_error_is_a_tooling_fail(self) -> None:
        row = self.row([
            rec("assistant", bash("1", "tool --x")),
            rec("user", result("1", "Exit code 2\nerror: unrecognized arguments: --x", True)),
        ])
        self.assertEqual((row["tooling_cli_fails"], row["total_failures"]), (1, 1))

    def test_test_runner_failure_is_an_audit_catch_not_a_failure(self) -> None:
        row = self.row([
            rec("assistant", bash("1", "python -m unittest discover -s tests")),
            rec("user", result("1", "Exit code 1\nFAILED (failures=2)", True)),
        ])
        self.assertEqual((row["audit_catches"], row["total_failures"]), (1, 0))

    def test_subagent_failures_are_not_attributed_to_the_main_thread(self) -> None:
        row = self.row([rec("assistant", text("hi"))], subagents={"s1": [
            rec("assistant", bash("9", "false")), rec("user", result("9", "Exit code 1\nx", True))]})
        self.assertEqual(row["total_failures"], 0)


class TestSubagentMetrics(_Base):
    def test_read_issued_while_agent_call_pending(self) -> None:
        row = self.row([
            rec("assistant", use("1", "Agent", prompt="x"), use("2", "Read", file_path="/p/a.py")),
            rec("user", result("2", "ok"), result("1", "done")),
            rec("assistant", use("3", "Read", file_path="/p/b.py")),
        ])
        self.assertEqual((row["reads_while_pending"], row["subagent_overlap_reads"], row["reads_after_subagent"]), (1, 0, 1))

    def test_background_agent_stays_pending_until_task_notification(self) -> None:
        row = self.row([
            rec("assistant", use("1", "Agent", prompt="x", run_in_background="true")),
            rec("user", result("1", "Async agent launched; running in the background")),
            rec("assistant", bash("2", "cat /p/a.py"), use("3", "ScheduleWakeup", delaySeconds="60")),
            rec("user", text("<task-notification>done</task-notification>")),
            rec("assistant", use("4", "Read", file_path="/p/b.py")),
        ])
        self.assertEqual((row["reads_while_pending"], row["schedule_while_subagent"]), (1, 1))

    def test_main_read_of_file_a_subagent_already_read_is_overlap(self) -> None:
        row = self.row([
            rec("assistant", use("1", "Agent", prompt="x")),
            rec("user", result("1", "done")),
            rec("assistant", use("2", "Read", file_path="/p/src/a.py"), use("3", "Read", file_path="/p/src/other.py"),
                use("4", "Edit", file_path="/p/src/z.py")),  # a code edit: doc-only sessions suppress overlap (parity)
        ], subagents={"s1": [rec("assistant", use("9", "Read", file_path="/p/src/a.py"))]})
        self.assertEqual((row["subagent_overlap_reads"], row["reads_after_subagent"], row["reads_while_pending"]), (1, 1, 0))

    def test_doc_only_sessions_suppress_small_overlap_like_antigravity(self) -> None:
        row = self.row([
            rec("assistant", use("1", "Agent", prompt="x")),
            rec("user", result("1", "done")),
            rec("assistant", use("2", "Read", file_path="/p/src/a.py"), use("3", "Edit", file_path="/p/docs/n.md")),
        ], subagents={"s1": [rec("assistant", use("9", "Read", file_path="/p/src/a.py"))]})
        self.assertEqual(row["subagent_overlap_reads"], 0)

    def test_overlap_ignored_when_main_edits_that_file(self) -> None:
        row = self.row([
            rec("assistant", use("1", "Agent", prompt="x")),
            rec("user", result("1", "done")),
            rec("assistant", use("2", "Read", file_path="/p/src/a.py"), use("3", "Edit", file_path="/p/src/a.py")),
        ], subagents={"s1": [rec("assistant", use("9", "Read", file_path="/p/src/a.py"))]})
        self.assertEqual(row["subagent_overlap_reads"], 0)

    def test_schedule_without_pending_agent_is_not_flagged(self) -> None:
        row = self.row([rec("assistant", use("1", "ScheduleWakeup", delaySeconds="60"))])
        self.assertEqual(row["schedule_while_subagent"], 0)


class TestPlanModeAndMarkers(_Base):
    def test_plan_mode_allowance_one_enter_two_exits(self) -> None:
        calls = [use(str(i), n) for i, n in enumerate(["EnterPlanMode", "ExitPlanMode", "EnterPlanMode", "ExitPlanMode", "ExitPlanMode"])]
        self.assertEqual(self.row([rec("assistant", *calls)])["plan_mode_calls"], 1 + 1)

    def test_text_and_command_markers(self) -> None:
        row = self.row([
            rec("user", text("please run /app-debugger now")),
            rec("assistant", text("Suggested: git commit -m x"), text("### Continuous Learning & Introspective Options")),
        ])
        self.assertEqual((row["has_debug_retro"], row["has_commit_hint"], row["has_learning_block"]), (True, True, True))
        cmd = self.row([rec("assistant", bash("1", "python diagnose.py debug-retro --cid x"))])
        self.assertTrue(cmd["has_debug_retro"])
        self.assertEqual(self.row([rec("assistant", text("hello"))])["has_debug_retro"], False)

    def test_changelog_add_counts_successes_and_skips_help(self) -> None:
        row = self.row([
            rec("assistant", bash("1", "diagnose.py changelog add --x"), bash("2", "diagnose.py changelog add --help"), bash("3", "diagnose.py changelog add --y")),
            rec("user", result("1", "[changelog add] Added entry"), result("2", "usage"), result("3", "Exit code 1\nfail", True)),
        ])
        self.assertEqual(row["changelog_adds"], 1)

    def test_cdp_fallback_and_live_failure(self) -> None:
        row = self.row([
            rec("assistant", bash("1", "diagnose.py ui --live --allow-headless-fallback"), bash("2", "diagnose.py ui --live"), bash("3", "git diff")),
            rec("user", result("1", "[CDP] Live connection failed\n[CDP] Falling back to isolated headless browser"),
                result("2", "[CDP] Live connection failed"), result("3", "[CDP] Falling back to isolated headless browser")),
        ])
        self.assertEqual((row["cdp_live_fallbacks"], row["cdp_live_failures"]), (1, 1))


class TestCuesAndShape(_Base):
    def test_english_and_spanish_corrections_and_redirects(self) -> None:
        row = self.row([
            rec("user", text("build it")),
            rec("user", text("no, wrong approach")),
            rec("user", text("en vez de eso, hazlo simple")),
            rec("user", text("switch to the opus model")),
            rec("user", text("cambia a otro modelo")),
        ])
        self.assertEqual(len(row["user_corrections"]), 2)
        self.assertEqual(len(row["workflow_redirects"]), 2)
        self.assertTrue(row["user_corrections"][0].startswith("step 1:"))

    def test_system_reminder_text_is_ignored(self) -> None:
        row = self.row([rec("user", text("<system-reminder>no, wrong, stop</system-reminder>")), rec("user", text("fine"))])
        self.assertEqual((row["user_corrections"], row["workflow_redirects"]), ([], []))

    def test_injected_user_records_are_not_corrections(self) -> None:
        meta = {**rec("user", text("Base directory for this skill. Do not stop. no wrong")), "isMeta": True}
        row = self.row([
            rec("user", text("go")), rec("user", text('<task-notification>Agent "x" failed: error, do not retry</task-notification>')), meta])
        self.assertEqual((row["user_corrections"], row["workflow_redirects"]), ([], []))

    def test_row_shape_is_antigravity_row_plus_documented_keys(self) -> None:
        row = self.row([rec("user", text("go")), rec("assistant", text("done"), model="m", usage={"input_tokens": 1, "output_tokens": 2})])
        self.assertEqual([k for k in GEMINI_KEYS if k not in row], [])
        self.assertEqual(sorted(set(row) - set(GEMINI_KEYS)), ["session_id", "token_note", "tokens", "vendor"])

    def test_heavy_token_totals_add_a_note_but_never_change_the_grade(self) -> None:
        row = self.row([rec("assistant", text("x"), usage={"cache_read_input_tokens": 6_000_000, "output_tokens": 300_000})])
        self.assertEqual(row["suggested_grade_cap"], "A")
        self.assertIn("heavy cache reads", row["token_note"])
        self.assertIn("heavy output", row["token_note"])

    def test_malformed_and_unknown_records_do_not_crash(self) -> None:
        row = self.row(["{not json", {"type": "mystery"}, {"type": "user", "message": 5}, rec("assistant", {"type": "tool_use"})])
        self.assertEqual(row["total_failures"], 0)


class TestRender(unittest.TestCase):
    def test_claude_row_adds_vendor_and_tokens_columns_and_token_note(self) -> None:
        r = {"cid": "abcdef123", "steps": 3, "total_failures": 0, "subagents": [], "reads_after_subagent": 0, "suggested_grade_cap": "A",
             "vendor": "claude", "tokens": {"input": 1, "output": 2, "cache_read": 3, "cache_creation": 4}, "token_note": "heavy output (9)",
             "parallel_same_file_edits": [], "repeated_reads": {}, "failure_samples": [], "user_corrections": [], "workflow_redirects": []}
        out = render.format_rows([r, {"cid": "zzz", "missing": True}])
        self.assertIn("| cid | vendor |", out)
        self.assertIn("| abcdef12 | claude | 3 | 0 | 0 | 0 | A | 5 in / 3 cached / 2 out |", out)
        self.assertIn("| zzz | - | MISSING |", out)
        self.assertIn("NOTE abcdef12: heavy output (9)", out)


if __name__ == "__main__":
    unittest.main()
