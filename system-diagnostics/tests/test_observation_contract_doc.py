#!/usr/bin/env python3
"""The published contract doc and JSON Schema must stay consistent with the implementation."""

import json
import re
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import observation_routes as R
import observation_store as S

REFS = Path(__file__).resolve().parent.parent / "references"
DOC = (REFS / "observation-connector-contract.md").read_text(encoding="utf-8")
SCHEMA = json.loads((REFS / "observation_contract.schema.json").read_text(encoding="utf-8"))


class TestContractDoc(unittest.TestCase):
    def test_doc_route_table_matches_implementation(self):
        documented = re.findall(r"^\| `((?:GET|POST) [^`]+)`", DOC, re.M)
        self.assertEqual(tuple(documented), R.ROUTES)

    def test_doc_lists_every_error_code_and_header(self):
        for code in R.ERROR_CODES:
            self.assertIn(f"`{code}`", DOC)
        self.assertIn("X-Diagnostics-Contract: 1", DOC)
        self.assertIn(R.BASE_PATH, DOC)
        self.assertIn(R.ENABLE_ENV, DOC)

    def test_schema_enums_match_store_and_routes(self):
        defs = SCHEMA["$defs"]
        self.assertEqual(tuple(defs["kind"]["enum"]), S.KINDS)
        self.assertEqual(tuple(defs["error"]["properties"]["error"]["enum"]), R.ERROR_CODES)
        self.assertEqual(defs["record"]["properties"]["message"]["maxLength"], S.MAX_MESSAGE)
        self.assertEqual(defs["record"]["properties"]["timeline"]["maxItems"], S.MAX_TIMELINE)

    def test_schema_record_example_passes_store_validation(self):
        S.sanitize_record({"kind": "element", "message": "x", "page_path": "/", "timeline": []})

    def test_no_forbidden_runtime_strings(self):
        for bad in ("python skills/", "<appDataDir>", "RequestFeedback"):
            self.assertNotIn(bad, DOC)


if __name__ == "__main__":
    unittest.main()
