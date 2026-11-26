import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import observation_store as s  # noqa: E402


def rec(**kw):
    base = {"kind": "element", "page_path": "/dashboard", "selector": "main > button#save", "message": "Save does nothing"}
    base.update(kw)
    return base


class StoreTestBase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.ws = Path(self._td.name).resolve()
        self.addCleanup(self._td.cleanup)


class FingerprintTests(unittest.TestCase):
    def test_published_vectors(self):
        self.assertEqual(s.make_fingerprint("element", "/dashboard", "main > button#save", "Save   does NOTHING"), "OBS-ELEMENT-fdd3fe")
        self.assertEqual(s.make_fingerprint("error", "/tracker", "/api/frames", "Request 123456 failed at 0xDEADBEEF"), "OBS-ERROR-f93b8a")
        self.assertEqual(s.make_fingerprint("idea", "/dashboard", "", "Add a pause button"), "OBS-IDEA-eca73f")

    def test_deterministic_and_normalized(self):
        a = s.make_fingerprint("note", "/p", "", "Hello   World 99999")
        b = s.make_fingerprint("note", "/p", "", "hello world 12345678")
        self.assertEqual(a, b)


class SanitizeTests(unittest.TestCase):
    def test_drops_forbidden_nested(self):
        out = s.sanitize_record(rec(timeline=[{"t": 0, "type": "input", "value": "x", "meta": {"Password": "p", "ok": 1}}]))
        self.assertNotIn("value", out["timeline"][0])
        self.assertEqual(out["timeline"][0]["meta"], {"ok": 1})

    def test_truncation_and_cap(self):
        out = s.sanitize_record(rec(message="x" * 900, timeline=[{"t": i} for i in range(80)]))
        self.assertEqual(len(out["message"]), 500)
        self.assertEqual(len(out["timeline"]), 50)
        self.assertEqual(out["timeline"][-1]["t"], 79)

    def test_oversize_and_bad_kind(self):
        with self.assertRaises(ValueError):
            s.sanitize_record(rec(blob="y" * 70000))
        with self.assertRaises(ValueError):
            s.sanitize_record(rec(kind="bogus"))


class RawLogTests(StoreTestBase):
    def test_roundtrip_corrupt_and_gitignore(self):
        s.append_raw(self.ws, {"a": 1})
        with open(self.ws / ".diagnostics" / s.RAW_NAME, "a", encoding="utf-8") as f:
            f.write("{not json\n")
        s.append_raw(self.ws, {"a": 2})
        records, corrupt = s.iter_raw(self.ws)
        self.assertEqual([r["a"] for r in records], [1, 2])
        self.assertEqual(corrupt, 1)
        self.assertTrue((self.ws / ".diagnostics" / ".gitignore").exists())

    def test_rotation(self):
        old = s.ROTATE_BYTES
        s.ROTATE_BYTES = 50
        self.addCleanup(setattr, s, "ROTATE_BYTES", old)
        for i in range(5):
            s.append_raw(self.ws, {"padding": "z" * 40, "i": i})
        self.assertTrue((self.ws / ".diagnostics" / s.BACKUP_NAME).exists())
        self.assertLess(len(s.iter_raw(self.ws)[0]), 5)


class CatalogTests(StoreTestBase):
    def test_ids_dedup_and_atomic(self):
        e1, d1 = s.add_observation(self.ws, rec())
        e2, _ = s.add_observation(self.ws, rec(message="Other"))
        e3, d3 = s.add_observation(self.ws, rec())
        self.assertEqual((e1["id"], e2["id"], d1, d3), ("OBS-001", "OBS-002", False, True))
        self.assertEqual(e3["occurrence_count"], 2)
        self.assertEqual(len(s.load_catalog(self.ws)["observations"]), 2)
        self.assertEqual(list((self.ws / ".diagnostics").glob("*.tmp")), [])

    def test_reopen_on_recurrence(self):
        e, _ = s.add_observation(self.ws, rec())
        s.update_status(self.ws, e["id"], "resolved", resolution="fixed")
        again, dedup = s.add_observation(self.ws, rec())
        self.assertTrue(dedup)
        self.assertEqual(again["status"], "open")
        self.assertEqual(again["history"][-1]["note"], "recurrence")

    def test_transitions(self):
        for src, targets in s.TRANSITIONS.items():
            for t in targets:
                with self.subTest(src=src, to=t):
                    ws = Path(tempfile.mkdtemp()).resolve()
                    e, _ = s.add_observation(ws, rec())
                    path = {"open": [], "triaged": ["triaged"], "in_progress": ["in_progress"],
                            "resolved": ["resolved"], "dismissed": ["dismissed"]}[src]
                    for step in path:
                        s.update_status(ws, e["id"], step)
                    self.assertEqual(s.update_status(ws, e["id"], t)["status"], t)
        e, _ = s.add_observation(self.ws, rec())
        s.update_status(self.ws, e["id"], "dismissed")
        with self.assertRaises(ValueError):
            s.update_status(self.ws, e["id"], "triaged")
        with self.assertRaises(KeyError):
            s.update_status(self.ws, "OBS-999", "triaged")

    def test_idea_and_triage_meta(self):
        e, _ = s.add_observation(self.ws, rec(kind="idea", selector="", message="Add pause"))
        self.assertTrue(e["fingerprint"].startswith("OBS-IDEA-"))
        out = s.update_status(self.ws, e["id"], "triaged", missed_by="tests, surface", proposed_guard="probe X", root_cause="rc")
        self.assertEqual(out["missed_by"], ["tests", "surface"])
        self.assertEqual(out["proposed_guard"], "probe X")
        with self.assertRaises(ValueError):
            s.update_status(self.ws, e["id"], "in_progress", missed_by="bogus")

    def test_list_filters(self):
        a, _ = s.add_observation(self.ws, rec())
        s.add_observation(self.ws, rec(kind="idea", selector="", message="idea"))
        s.add_observation(self.ws, rec(message="third"))
        s.update_status(self.ws, a["id"], "resolved")
        self.assertEqual(len(s.list_observations(self.ws)), 2)
        self.assertEqual(len(s.list_observations(self.ws, status="all")), 3)
        self.assertEqual(len(s.list_observations(self.ws, status="resolved")), 1)
        self.assertEqual([e["kind"] for e in s.list_observations(self.ws, kind="idea")], ["idea"])
        self.assertEqual(len(s.list_observations(self.ws, status="all", limit=1)), 1)


if __name__ == "__main__":
    unittest.main()
