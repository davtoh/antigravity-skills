#!/usr/bin/env python3
"""Merge rules for `observations pull`: new / updated / unchanged, local triage kept, redaction."""

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import observation_merge as M
import observation_store as store

URL = "http://127.0.0.1:9"


def remote(**kw):
    base = {"id": "OBS-007", "fingerprint": "OBS-NOTE-aaaaaa", "kind": "note", "status": "open",
            "first_seen": "2026-11-01T00:00:00+00:00", "last_seen": "2026-11-02T00:00:00+00:00",
            "occurrence_count": 3, "page_path": "/p", "selector": "", "message": "hello"}
    base.update(kw)
    return base


def empty():
    return {"observations": []}


class TestMerge(unittest.TestCase):
    def test_new_entry_gets_local_id_and_source_url(self):
        cat = empty()
        self.assertEqual(M.merge_remote(cat, remote(), URL), "new")
        e = cat["observations"][0]
        self.assertEqual((e["id"], e["source_url"], e["occurrence_count"], e["status"]), ("OBS-001", URL, 3, "open"))
        self.assertEqual(e["first_seen"], "2026-11-01T00:00:00+00:00")
        self.assertEqual(e["fingerprint"], "OBS-NOTE-aaaaaa")

    def test_older_or_equal_remote_is_unchanged(self):
        cat = empty()
        M.merge_remote(cat, remote(), URL)
        self.assertEqual(M.merge_remote(cat, remote(), URL), "unchanged")
        self.assertEqual(M.merge_remote(cat, remote(last_seen="2026-10-01T00:00:00+00:00"), URL), "unchanged")

    def test_newer_remote_updates_status_keeps_local_triage(self):
        cat = empty()
        M.merge_remote(cat, remote(), URL)
        local = cat["observations"][0]
        local.update(root_cause="mine", missed_by=["tests"], proposed_guard="g", linked_plan="p")
        res = M.merge_remote(cat, remote(status="resolved", last_seen="2026-11-05T00:00:00+00:00",
                                         occurrence_count=5, root_cause="theirs"), URL)
        self.assertEqual(res, "updated")
        self.assertEqual((local["status"], local["occurrence_count"], local["root_cause"]), ("resolved", 5, "mine"))
        self.assertEqual((local["missed_by"], local["linked_plan"]), (["tests"], "p"))
        self.assertEqual(local["history"][-1]["to"], "resolved")
        self.assertEqual(len(cat["observations"]), 1)

    def test_remote_data_is_resanitized(self):
        cat = empty()
        M.merge_remote(cat, remote(message="m" * 900, attrs={"password": "x", "id": "a"}, timeline=list(range(80))), URL)
        e = cat["observations"][0]
        self.assertEqual(len(e["message"]), 500)
        self.assertNotIn("password", e["attrs"])
        self.assertEqual(len(e["timeline"]), store.MAX_TIMELINE)

    def test_unusable_remote_raises(self):
        with self.assertRaises(ValueError):
            M.merge_remote(empty(), remote(kind="bogus"), URL)
        with self.assertRaises(ValueError):
            M.merge_remote(empty(), "nope", URL)

    def test_needs_fetch(self):
        cat = empty()
        M.merge_remote(cat, remote(), URL)
        same = {"fingerprint": "OBS-NOTE-aaaaaa", "last_seen": "2026-11-02T00:00:00+00:00"}
        self.assertFalse(M.needs_fetch(cat, same))
        self.assertTrue(M.needs_fetch(cat, {**same, "last_seen": "2026-11-03T00:00:00+00:00"}))
        self.assertTrue(M.needs_fetch(cat, {"fingerprint": "OBS-NOTE-bbbbbb", "last_seen": "x"}))


if __name__ == "__main__":
    unittest.main()
