"""Tests for transcript_cues: defaults, Spanish extras, the optional cue file, tolerance."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import transcript_checks as tc  # noqa: E402
from transcript_cues import CUE_FILE, load_cues  # noqa: E402


def _acc() -> dict:
    return {"seen_first_user": True, "user_corrections": [], "workflow_redirects": []}


class TestCues(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def _write(self, content: str) -> None:
        (self.root / CUE_FILE).parent.mkdir(parents=True, exist_ok=True)
        (self.root / CUE_FILE).write_text(content, encoding="utf-8")

    def test_defaults_include_english_and_spanish(self) -> None:
        cues = load_cues(self.root)
        self.assertTrue(cues["correction"].search("this is wrong"))
        self.assertTrue(cues["correction"].search("Eso está mal"))
        self.assertTrue(cues["correction"].search("EN LUGAR DE eso"))
        self.assertFalse(cues["correction"].search("normal"), "no substring matches")

    def test_cue_file_extends_defaults(self) -> None:
        self._write(json.dumps({"correction": ["nope.exe", "ni modo"], "workflow_redirect": ["gemini"], "unknown": ["x"]}))
        cues = load_cues(self.root)
        self.assertTrue(cues["correction"].search("ni  modo"), "phrase whitespace is flexible")
        self.assertTrue(cues["correction"].search("nope.exe"))
        self.assertFalse(cues["correction"].search("nopeXexe"), "entries are literal, not regex")
        self.assertTrue(cues["workflow_redirect"].search("use gemini"))
        self.assertTrue(cues["correction"].search("wrong"), "defaults remain")

    def test_malformed_or_mistyped_cue_file_is_ignored(self) -> None:
        for bad in ("{not json", "[1, 2]", json.dumps({"correction": "string", "redirect_verb": [1, None, "swap to"]})):
            self._write(bad)
            cues = load_cues(self.root)
            self.assertTrue(cues["correction"].search("stop"))
        self.assertTrue(cues["redirect_verb"].search("swap to"))

    def test_missing_file_or_workspace(self) -> None:
        self.assertTrue(load_cues(self.root)["correction"].search("stop"))
        self.assertTrue(load_cues(None)["correction"].search("stop"))

    def test_extractor_default_path_is_unchanged_for_english(self) -> None:
        acc = _acc()
        tc.extract_user_correction("no, that is wrong", 4, acc)
        self.assertEqual(acc["user_corrections"], ["step 4: no, that is wrong"])
        spanish = _acc()
        tc.extract_user_correction("en vez de eso hazlo simple", 5, spanish)
        self.assertEqual(spanish["user_corrections"], [], "Antigravity path stays English-only")
        tc.extract_user_correction("en vez de eso hazlo simple", 5, spanish, load_cues())
        self.assertEqual(len(spanish["user_corrections"]), 1)

    def test_plain_questions_are_not_corrections(self) -> None:
        cases = ["can you help me checking why the build failed", "is it true this is the best approach?",
                 "¿puedes revisar si esto está mal?", "cómo arreglo el error en el modelo", "what is wrong here?"]
        for text in cases:
            acc = _acc()
            tc.extract_user_correction(text, 1, acc, load_cues(self.root))
            self.assertEqual(acc["user_corrections"], [], text)
            self.assertEqual(acc.get("workflow_redirects", []), [], text)

    def test_pasted_content_and_hyphenated_words_do_not_trigger(self) -> None:
        acc = _acc()
        tc.extract_user_correction('based on this is it true this is best? <pasted_content id="b1">no, wrong, stop</pasted_content>', 1, acc, load_cues(self.root))
        tc.extract_user_correction('see this <pasted_content id="2"> do NOT load it (never closed)', 3, acc, load_cues(self.root))
        tc.extract_user_correction("keep the review-gate and no-brain guidance", 2, acc, load_cues(self.root))
        self.assertEqual(acc["user_corrections"], [])

    def test_blame_and_override_still_correct(self) -> None:
        for text in ["why did you delete that?", "por qué hiciste eso?", "no, that is wrong", "stop doing that?"]:
            acc = _acc()
            tc.extract_user_correction(text, 1, acc, load_cues(self.root))
            self.assertEqual(len(acc["user_corrections"]), 1, text)


if __name__ == "__main__":
    unittest.main()
