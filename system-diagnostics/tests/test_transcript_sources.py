"""Tests for transcript_sources: vendor precedence (D2), discovery, current session id."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
for p in (HERE.parent / "scripts", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import transcript_sources as src  # noqa: E402
from _claude_fixtures import rec, session, text, write_jsonl  # noqa: E402

CID = "11111111-2222-3333-4444-555555555555"


class TestSources(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.claude, self.brain = root / "projects", root / "brain"
        self.brain.mkdir()
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("TRANSCRIPT_VENDOR", None)

    def _claude(self, cid: str = CID, slug: str = "-proj") -> Path:
        return session(self.claude, cid, [rec("user", text("hi"))], slug=slug)

    def _gemini(self, cid: str = CID) -> None:
        write_jsonl(self.brain / cid / ".system_generated" / "logs" / "transcript.jsonl", [{"type": "USER_INPUT"}])

    def _detect(self, token: str = CID, explicit: str | None = None) -> str:
        return src.detect_vendor(token, explicit, self.brain, self.claude)

    def test_found_where_it_lives_and_default_gemini(self) -> None:
        self.assertEqual(self._detect(), "gemini")  # nowhere: fallback
        self._claude()
        self.assertEqual(self._detect(), "claude")
        self.assertEqual(self._detect(CID[:8]), "claude")  # 8-char prefix
        self.assertEqual(self._detect(CID[:4]), "gemini")  # too short to prefix-match

    def test_gemini_only(self) -> None:
        self._gemini("abcd1234-0")
        self.assertEqual(self._detect("abcd1234"), "gemini")

    def test_both_roots_is_an_error_unless_explicit(self) -> None:
        self._claude()
        self._gemini()
        with self.assertRaises(src.AmbiguousVendorError):
            self._detect()
        self.assertEqual(self._detect(explicit="gemini"), "gemini")

    def test_explicit_beats_env_beats_location(self) -> None:
        self._claude()
        os.environ["TRANSCRIPT_VENDOR"] = "gemini"
        self.assertEqual(self._detect(), "gemini")
        self.assertEqual(self._detect(explicit="claude"), "claude")
        self.assertEqual(self._detect(explicit="auto"), "gemini")  # auto defers to env
        os.environ["TRANSCRIPT_VENDOR"] = "bogus"
        with self.assertRaises(ValueError):
            self._detect()

    def test_project_dir_restricts_lookup(self) -> None:
        self._claude(slug="-other")
        self.assertEqual(src.detect_vendor(CID, None, self.brain, self.claude, self.claude / "-proj"), "gemini")
        self.assertEqual(len(src.find_claude_sessions(CID, self.claude, self.claude / "-other")), 1)

    def test_current_session_id_never_guessed(self) -> None:
        os.environ["CLAUDE_CODE_SESSION_ID"] = "abc"
        self.assertEqual(src.current_session_id("claude"), "abc")
        self.assertEqual(src.current_session_id("gemini"), "")
        os.environ.pop("CLAUDE_CODE_SESSION_ID")
        self.assertEqual(src.current_session_id("claude"), "")

    def test_dirs_and_slug(self) -> None:
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.claude.parent)
        self.assertEqual(src.default_claude_dir(), self.claude)
        os.environ["AGY_BRAIN_DIR"] = str(self.brain)
        self.assertEqual(src.default_brain_dir(), self.brain)
        self.assertEqual(src.project_slug("/Users/a.b/work/repo"), "-Users-a-b-work-repo")
        self.assertEqual(src.project_slug("C:\\Users\\a"), "C--Users-a")

    def test_list_sessions_newest_first(self) -> None:
        old = self._claude("old00000")
        os.utime(old, (1, 1))
        self._claude("new00000")
        self.assertEqual([i for i, _ in src.list_sessions("claude", claude_dir=self.claude)], ["new00000", "old00000"])
        self._gemini("g1")
        self.assertEqual([i for i, _ in src.list_sessions("gemini", brain_dir=self.brain)], ["g1"])


if __name__ == "__main__":
    unittest.main()
