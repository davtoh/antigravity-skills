"""Tests for transcript_claude (synthetic sessions only)."""

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parent / "scripts", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import transcript_claude as tc  # noqa: E402
from _claude_fixtures import result, rec, session, text, use  # noqa: E402

USAGE = {"input_tokens": 3, "output_tokens": 5, "cache_read_input_tokens": 7, "cache_creation_input_tokens": 11}


class TestClaudeReader(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def test_normalizes_calls_results_and_tokens(self) -> None:
        main = session(self.root, "s1", [
            rec("user", text("hello there")),
            rec("assistant", text("on it"), use("t1", "Bash", command="ls\nmore"), model="m", usage=USAGE),
            rec("user", result("t1", "Exit code 2\nboom", error=True)),
            rec("assistant", use("t2", "Write", file_path="/a/b.py")),
        ])
        steps = list(tc.read_session(main))
        self.assertEqual([s["kind"] for s in steps], ["text", "text", "tool_call", "tool_result", "tool_call"])
        call, res = steps[2], steps[3]
        self.assertEqual((call["tool"], call["args"]["command"], call["args"]["target"]), ("run_command", "ls\nmore", "ls"))
        self.assertEqual((res["tool"], res["error"], res["exit_code"], res["ok"]), ("run_command", True, 2, False))
        self.assertEqual(steps[1]["tokens"], {"input": 3, "output": 5, "cache_read": 7, "cache_creation": 11})
        self.assertIsNone(steps[2]["tokens"])  # usage counted once per record
        self.assertEqual(steps[4]["tool"], "edit_file")
        self.assertEqual([s["idx"] for s in steps], list(range(5)))

    def test_tolerates_unknown_and_malformed_input(self) -> None:
        main = session(self.root, "s2", [
            "not json", "[1, 2]", {"type": "queue-operation"}, {"type": "user"}, {"type": "assistant", "message": "str"},
            {"type": "user", "message": {"content": "plain string prompt"}},
            rec("assistant", {"type": "mystery", "x": 1}, "junk", {"type": "tool_use", "input": 5}),
        ])
        steps = list(tc.read_session(main))
        self.assertEqual([s["text_snippet"] for s in steps[:1]], ["plain string prompt"])
        self.assertEqual(steps[1]["kind"], "tool_call")
        self.assertEqual(steps[1]["args"], {"path": "", "command": "", "target": ""})

    def test_subagents_are_read_after_main_with_agent_id(self) -> None:
        main = session(self.root, "s3", [rec("assistant", use("a", "Agent", prompt="go"))], subagents={
            "zz": [rec("assistant", use("r", "Read", file_path="/x.py"))],
            "aa": [rec("assistant", use("r", "Grep", pattern="q"))],
        })
        steps = list(tc.read_session(main))
        self.assertEqual([(s["agent_id"], s["tool"]) for s in steps], [(None, "invoke_subagent"), ("aa", "search"), ("zz", "view_file")])
        self.assertEqual(len(list(tc.read_session(main, include_subagents=False))), 1)

    def test_snippets_are_capped(self) -> None:
        main = session(self.root, "s4", [rec("user", text("x" * 500))])
        self.assertEqual(len(next(tc.read_session(main))["text_snippet"]), tc.SNIPPET_MAX)

    def test_missing_file_yields_nothing(self) -> None:
        self.assertEqual(list(tc.read_session(self.root / "nope.jsonl")), [])


if __name__ == "__main__":
    unittest.main()
