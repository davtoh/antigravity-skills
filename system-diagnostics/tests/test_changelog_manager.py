#!/usr/bin/env python3
"""Comprehensive Unit & Integration Tests for Unified Changelog Engine.

Tests:
1. Declarative SANITIZATION_RULES (file:///, .venv, localhost, user paths).
2. Archive discovery priority (.changelogs/ vs docs/archive/changelogs/ vs fallback).
3. Identity & Coexistence guards (same-path in-place, deduplication, safe unlinking).
4. Entry-boundary rotation at 150 lines (never splitting entries, archiving shards).
5. Single-generation commit hint echo & CLI subcommands.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure system-diagnostics/scripts is in sys.path
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import changelog_manager
from changelog_manager import (
    AI_GUARD_BANNER,
    ChangelogEntry,
    parse_changelog,
    resolve_archive_dir,
    rotate_entries,
    sanitize_text,
)


class TestSanitizationRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_file_uri_sanitization(self):
        src_file = self.root / "src" / "worker.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("pass", encoding="utf-8")

        # Windows file URI with line fragment
        win_uri = f"file:///{src_file.as_posix()}#L15-L25"
        sanitized = sanitize_text(f"Check {win_uri}", self.root)
        self.assertIn("src/worker.py#L15-L25", sanitized)
        self.assertNotIn("file:///", sanitized)

    def test_venv_and_localhost_sanitization(self):
        text = "Run .venv\\Scripts\\python.exe tests on http://localhost:8080/api"
        sanitized = sanitize_text(text, self.root)
        self.assertIn("Run python tests on $APP_URL/api", sanitized)
        self.assertNotIn("localhost:8080", sanitized)

        posix_text = "Run ./venv/bin/python3 tests on http://127.0.0.1:3000"
        sanitized_posix = sanitize_text(posix_text, self.root)
        self.assertIn("Run python tests on $APP_URL", sanitized_posix)

    def test_user_path_sanitization(self):
        # File within repo
        local_target = self.root / "services" / "app.py"
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.write_text("code", encoding="utf-8")

        internal_path = str(local_target)
        sanitized_internal = sanitize_text(f"Refactored {internal_path}", self.root)
        self.assertIn("services/app.py", sanitized_internal)

        # Path outside repo
        outside_path = "C:\\Users\\RandomUser\\secrets.txt"
        sanitized_outside = sanitize_text(f"Read {outside_path}", self.root)
        self.assertIn("<local_path>", sanitized_outside)
        self.assertNotIn("RandomUser", sanitized_outside)


class TestArchiveDiscovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_priority_1_existing_dot_changelogs(self):
        dot_c = self.root / ".changelogs"
        dot_c.mkdir()
        resolved = resolve_archive_dir(self.root)
        self.assertEqual(resolved, dot_c)

    def test_priority_2_docs_archive_changelogs(self):
        docs_arch = self.root / "docs" / "archive" / "changelogs"
        docs_arch.mkdir(parents=True)
        resolved = resolve_archive_dir(self.root)
        self.assertEqual(resolved, docs_arch)

    def test_priority_3_creates_dot_changelogs_with_gitignore(self):
        resolved = resolve_archive_dir(self.root)
        self.assertEqual(resolved, self.root / ".changelogs")
        self.assertTrue(resolved.is_dir())
        gi = resolved / ".gitignore"
        self.assertTrue(gi.exists())
        self.assertEqual(gi.read_text(encoding="utf-8").strip(), "*")


class TestIdentityAndCoexistenceGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_path_guard_in_place_rotation(self):
        log_file = self.root / "CHANGELOG.md"
        entries_text = "\n\n".join(
            f"## [2026-11-0{i}] Milestone {i}\n- **Summary**: Work {i}\n- **Details**: Long description for line padding\n- **Notes**: Extra line\n- **Files**:\n  - `f1.py`\n  - `f2.py`"
            for i in range(1, 10)
        )
        log_file.write_text(f"# Changelog\n\n{entries_text}\n", encoding="utf-8")

        ok, msg = changelog_manager.migrate_logs(self.root, "CHANGELOG.md", "CHANGELOG.md", max_lines=25)
        self.assertTrue(ok)
        self.assertIn("Same-path guard", msg)
        self.assertTrue(log_file.exists())
        # Check archive directory has shard
        arch = self.root / ".changelogs"
        shards = list(arch.glob("changelog_*.md"))
        self.assertTrue(len(shards) >= 1)

    def test_coexistence_merge_and_source_unlinking(self):
        src = self.root / "MIGRATION_LOG.md"
        tgt = self.root / "CHANGELOG.md"

        src.write_text("## [2026-05-01] Old Milestone\n- **Summary**: Legacy work\n", encoding="utf-8")
        tgt.write_text("## [2026-11-05] New Milestone\n- **Summary**: Current work\n", encoding="utf-8")

        ok, msg = changelog_manager.migrate_logs(self.root, "MIGRATION_LOG.md", "CHANGELOG.md")
        self.assertTrue(ok)
        self.assertIn("Migrated 1 entries", msg)
        self.assertFalse(src.exists())  # Unlinked safely
        self.assertTrue(tgt.exists())
        tgt_content = tgt.read_text(encoding="utf-8")
        self.assertIn("New Milestone", tgt_content)
        self.assertIn("Old Milestone", tgt_content)


class TestEntryBoundaryRotation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rotation_maintains_min_3_entries_and_shards_overflow(self):
        arch_dir = self.root / ".changelogs"
        arch_dir.mkdir()

        entries = []
        for i in range(1, 8):
            header = f"## [2026-0{i:02d}-15] feat: Feature {i}"
            body = [f"- **Type**: feat", f"- **Summary**: Implementation {i}", "- **Files**:"] + [f"  - `file_{j}.py`" for j in range(5)]
            entries.append(ChangelogEntry(header, body))

        prologue = "# Changelog\n\n"
        # max_lines=20 will fit 2 entries normally (each ~9 lines), but min_entries=3 forces keeping 3
        final_content, shards = rotate_entries(prologue, entries, arch_dir, max_lines=20, min_entries=3)

        _, kept = parse_changelog(final_content)
        self.assertEqual(len(kept), 3)  # Kept exactly min 3 entries
        self.assertEqual(kept[0].header, entries[0].header)
        self.assertEqual(kept[1].header, entries[1].header)
        self.assertEqual(kept[2].header, entries[2].header)

        # Shards should exist for overflow entries (4 through 7)
        self.assertTrue(len(shards) >= 1)
        shard_text = shards[0].read_text(encoding="utf-8")
        self.assertIn(AI_GUARD_BANNER.strip(), shard_text)
        self.assertIn("Feature 4", shard_text)

    def test_compacting_verbose_entries(self):
        header = "## [2026-11-05] refactor: Massive refactoring"
        body = [f"- **Type**: refactor", f"- **Summary**: Big split", "- **Files**:"] + [f"  - `file_{j}.py`" for j in range(30)]
        entry = ChangelogEntry(header, body)
        self.assertGreaterEqual(len(entry.body), 25)

        compacted = entry.compact(max_body_lines=15)
        self.assertLessEqual(len(compacted.splitlines()), 16)
        self.assertIn("(+more modified files)", compacted)


class TestCliSubcommands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_subcommand_with_commit_hint(self):
        parser = changelog_manager.argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="subcommand")
        changelog_manager.register_parser(sub)

        args = parser.parse_args([
            "changelog", "add",
            "--path", str(self.root),
            "--type", "refactor",
            "--title", "Stream Worker Decomposition",
            "--summary", "Split 800L module into 4 SRP services",
            "--files", "worker.py", "service.py",
            "--verify", "pytest (45 passed)",
        ])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            ret = changelog_manager.cmd_changelog(args)
            output = mock_stdout.getvalue()

        self.assertEqual(ret, 0)
        self.assertIn("Added entry to CHANGELOG.md", output)
        self.assertIn("=== Suggested Git Commit ===", output)
        self.assertIn('git commit -m "refactor: Stream Worker Decomposition" -m "Split 800L module into 4 SRP services"', output)

    def test_add_subcommand_git_notice_when_uninitialized(self):
        parser = changelog_manager.argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="subcommand")
        changelog_manager.register_parser(sub)

        args = parser.parse_args([
            "changelog", "add",
            "--path", str(self.root),
            "--title", "Initial Setup",
        ])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            ret = changelog_manager.cmd_changelog(args)
            output = mock_stdout.getvalue()

        self.assertEqual(ret, 0)
        self.assertIn("# Notice: Git uninitialized. Run 'git init' first", output)
        self.assertIn("git init", output)

        tgt = self.root / "CHANGELOG.md"
        self.assertTrue(tgt.exists())
        self.assertIn("Initial Setup", tgt.read_text(encoding="utf-8"))

    def test_show_and_status_json(self):
        # Create a sample changelog
        tgt = self.root / "CHANGELOG.md"
        tgt.write_text("# Changelog\n\n## [2026-11-05] feat: Initial\n- **Summary**: Started project\n", encoding="utf-8")

        parser = changelog_manager.argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="subcommand")
        changelog_manager.register_parser(sub)

        # Show JSON
        args_show = parser.parse_args(["changelog", "show", "--path", str(self.root), "--json"])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            ret = changelog_manager.cmd_changelog(args_show)
            data = json.loads(mock_stdout.getvalue())
        self.assertEqual(ret, 0)
        self.assertEqual(len(data), 1)
        self.assertIn("Initial", data[0]["header"])

        # Status JSON
        args_status = parser.parse_args(["changelog", "status", "--path", str(self.root), "--json"])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            ret = changelog_manager.cmd_changelog(args_status)
            data = json.loads(mock_stdout.getvalue())
        self.assertEqual(ret, 0)
        self.assertEqual(data["target"]["name"], "CHANGELOG.md")
        self.assertGreater(data["target"]["lines"], 0)


if __name__ == "__main__":
    unittest.main()
