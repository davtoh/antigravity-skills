#!/usr/bin/env python3
"""Tests for OBS-020 (trace chips + composer restore), OBS-021 (export/import), OBS-022 (collapsed dirty)."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import observation_assets  # noqa: E402
import observation_routes as R  # noqa: E402
import observation_store as S  # noqa: E402

ENV_ON = {"FRONTIER_DEBUG_OBSERVATIONS": "1"}
JSON_H = {"Content-Type": "application/json"}
LOCAL = "127.0.0.1"
UX_TRACE_DRIVER = ROOT / "tests" / "fixtures" / "hud" / "ux_trace_export_driver.js"


class TestObservationTraceAndExportBackend(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)
        self.ws = Path(self._td.name).resolve()

    def _call(self, method: str, path: str, query: str = "", headers: dict | None = None,
              host: str = LOCAL, body: bytes = b"", env: dict | None = None):
        return R.handle(method, path, query, headers or {}, host, body, self.ws, ENV_ON if env is None else env)

    def test_list_fields_include_trace_metadata_and_compact_timeline(self) -> None:
        timeline = [{"t": i * 10, "type": "click", "target": f"#b{i}", "extra": "ignored"} for i in range(12)]
        rec = {
            "kind": "idea", "page_path": "/#live", "selector": "#live-stream-img",
            "message": "trace attached", "recording_id": "rec-f6d540",
            "window": {"started_at": "2026-11-27T00:00:00Z", "stopped_at": "2026-11-27T00:00:05Z"},
            "timeline": timeline,
        }
        st, _, _ = self._call("POST", "/observation", headers=JSON_H, body=json.dumps(rec).encode("utf-8"))
        self.assertEqual(st, 201)
        listed = json.loads(self._call("GET", "/observations")[2])["observations"]
        row = listed[0]
        self.assertEqual(row["recording_id"], "rec-f6d540")
        self.assertEqual(row["window"]["started_at"], "2026-11-27T00:00:00Z")
        self.assertEqual(row["trace_count"], 12)
        self.assertEqual(len(row["timeline"]), 5)
        self.assertEqual(row["timeline"][-1], {"t": 110, "type": "click", "target": "#b11"})

    def test_export_redacts_secrets_and_filters_by_status_or_kind(self) -> None:
        self._call("POST", "/observation", headers=JSON_H, body=json.dumps({
            "kind": "note", "message": "one", "attrs": {"password": "pw", "id": "ok"}, "value": "secret",
        }).encode("utf-8"))
        self._call("POST", "/observation", headers=JSON_H, body=json.dumps({
            "kind": "idea", "message": "two",
        }).encode("utf-8"))
        self._call("PATCH", "/observations/OBS-001", headers=JSON_H, body=b'{"status":"dismissed"}')

        st, hdrs, body = self._call("GET", "/observations/export")
        self.assertEqual(st, 200)
        self.assertEqual(hdrs["X-Diagnostics-Contract"], "1")
        self.assertIn("observations-export.json", hdrs["Content-Disposition"])
        bundle = json.loads(body)
        self.assertEqual(bundle["count"], 2)
        dumped = json.dumps(bundle)
        self.assertNotIn("secret", dumped)
        self.assertNotIn('"password"', dumped)

        idea_only = json.loads(self._call("GET", "/observations/export", "kind=idea")[2])
        self.assertEqual(idea_only["count"], 1)
        self.assertEqual(idea_only["observations"][0]["kind"], "idea")
        self.assertEqual(self._call("GET", "/observations/export", "status=bogus")[0], 400)
        self.assertEqual(self._call("GET", "/observations/export", host="8.8.8.8")[0], 403)
        self.assertEqual(self._call("GET", "/observations/export", env={})[0], 404)

    def test_import_roundtrip_idempotent_update_and_new_workspace(self) -> None:
        self._call("POST", "/observation", headers=JSON_H, body=json.dumps({
            "kind": "element", "page_path": "/#studio", "selector": "#btn", "message": "initial",
        }).encode("utf-8"))
        bundle = json.loads(self._call("GET", "/observations/export")[2])

        same = self._call("POST", "/observations/import", headers=JSON_H, body=json.dumps(bundle).encode("utf-8"))
        self.assertEqual((same[0], json.loads(same[2])), (200, {"schema": 1, "imported": 0, "updated": 0, "skipped": 1, "total": 1}))

        bundle["observations"][0]["message"] = "edited offline"
        bundle["observations"][0]["status"] = "triaged"
        bundle["observations"].append({"kind": "idea", "message": "added offline", "attrs": {"cookie": "bad", "tag": "div"}})
        edited = self._call("POST", "/observations/import", headers=JSON_H, body=json.dumps(bundle).encode("utf-8"))
        self.assertEqual((edited[0], json.loads(edited[2])), (200, {"schema": 1, "imported": 1, "updated": 1, "skipped": 0, "total": 2}))

        obs1 = S.get_observation(self.ws, "OBS-001")
        obs2 = S.get_observation(self.ws, "OBS-002")
        self.assertEqual((obs1["message"], obs1["status"], obs1["history"][-1]["note"]), ("edited offline", "triaged", "imported"))
        self.assertEqual(obs2["attrs"], {"tag": "div"})

        with tempfile.TemporaryDirectory() as other_td:
            other_ws = Path(other_td).resolve()
            res = R.handle("POST", "/observations/import", "", JSON_H, LOCAL, json.dumps(bundle).encode("utf-8"), other_ws, ENV_ON)
            self.assertEqual((res[0], json.loads(res[2])["imported"]), (200, 2))

    def test_import_validation_and_gating_are_atomic(self) -> None:
        self._call("POST", "/observation", headers=JSON_H, body=json.dumps({"kind": "note", "message": "seed"}).encode("utf-8"))
        self.assertEqual(self._call("POST", "/observations/import", headers={"Content-Type": "text/plain"}, body=b"{}")[0], 415)
        self.assertEqual(self._call("POST", "/observations/import", headers=JSON_H, body=b"{bad")[0], 400)
        self.assertEqual(self._call("POST", "/observations/import", headers=JSON_H, body=b" " * 70000)[0], 413)
        self.assertEqual(self._call("POST", "/observations/import", headers=JSON_H, host="8.8.8.8", body=b"{}")[0], 403)
        self.assertEqual(self._call("POST", "/observations/import", headers=JSON_H, env={}, body=b"{}")[0], 404)

        bad_batch = {"observations": [{"kind": "note", "message": "ok"}, {"kind": "bogus", "message": "bad"}]}
        res = self._call("POST", "/observations/import", headers=JSON_H, body=json.dumps(bad_batch).encode("utf-8"))
        self.assertEqual((res[0], json.loads(res[2])["error"]), (400, "invalid_record"))
        self.assertEqual(len(S.list_observations(self.ws, status="all")), 1)


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class TestObservationHudTraceExportDirtyUx(unittest.TestCase):
    def test_hud_trace_chips_export_import_and_collapsed_dirty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle_path = Path(td) / "bundle.js"
            bundle_path.write_text(observation_assets.hud_bundle(), encoding="utf-8")
            proc = subprocess.run(
                ["node", str(UX_TRACE_DRIVER), str(bundle_path)],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertTrue(out["cardHasTraceChip"])
        self.assertEqual(out["plainCardCount"], 1)
        self.assertTrue(out["collapsedSelectedNull"])
        self.assertTrue(out["collapsedDirtyBadge"])
        self.assertTrue(out["dirtyClearedAfterSave"])
        self.assertEqual(out["restoredFinished"], {"id": "rec-abc123", "count": 12, "restored": True})
        self.assertTrue(out["composerHasTraceChip"])
        self.assertFalse(out["patchKeepHasTimeline"])
        self.assertEqual(out["patchClearedTrace"], {"rid": None, "win": None, "tl": []})
        self.assertTrue(out["hasExportImportBtns"])
        self.assertTrue(out["exportOk"])
        self.assertEqual(out["exportStatus"], "Exported 2 observations")
        self.assertEqual(out["badImportStatus"], "Import failed: invalid JSON")
        self.assertEqual(out["postCallsAfterBad"], 0)
        self.assertEqual(out["importStatus"], "Imported 1, updated 0, skipped 1")
        self.assertEqual(out["postCallsAfterGood"], 1)
        self.assertEqual(out["drawerCountAfterImport"], 3)


if __name__ == "__main__":
    unittest.main()
