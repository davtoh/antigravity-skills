#!/usr/bin/env python3
"""Unit tests for `system-diagnostics/scripts/mini_ci.py` and `diagnose.py ci`."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import diagnose
import mini_ci


class TestMiniCiLayoutAndConfig(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_detect_skills_monorepo_via_validate_script(self) -> None:
        val = self.root / ".github" / "scripts" / "validate_skills.py"
        val.parent.mkdir(parents=True)
        val.write_text("print('ok')\n", encoding="utf-8")
        self.assertEqual(mini_ci.detect_layout(self.root), "skills_monorepo")

    def test_detect_skills_monorepo_via_multiple_skill_test_dirs(self) -> None:
        for name in ("skill-a", "skill-b"):
            tdir = self.root / name / "tests"
            tdir.mkdir(parents=True)
            (tdir / "test_ok.py").write_text("", encoding="utf-8")
        self.assertEqual(mini_ci.detect_layout(self.root), "skills_monorepo")
        self.assertEqual(mini_ci.discover_skill_test_dirs(self.root), ["skill-a/tests", "skill-b/tests"])

    def test_detect_standard_python_repo(self) -> None:
        tdir = self.root / "tests"
        tdir.mkdir()
        (tdir / "test_app.py").write_text("", encoding="utf-8")
        self.assertEqual(mini_ci.detect_layout(self.root), "python_repo")

    def test_load_config_optional_and_invalid(self) -> None:
        self.assertEqual(mini_ci.load_config(self.root), {})
        cfg_file = self.root / ".diagnostics" / "mini_ci.json"
        cfg_file.parent.mkdir(parents=True)
        cfg_file.write_text(json.dumps({"env": {"FOO": "bar"}, "steps": [["{python}", "-V"]]}), encoding="utf-8")
        cfg = mini_ci.load_config(self.root)
        self.assertEqual(cfg["env"]["FOO"], "bar")
        cfg_file.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            mini_ci.load_config(self.root)


class TestMiniCiBuilders(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_windows_to_wsl_path(self) -> None:
        self.assertEqual(mini_ci.windows_to_wsl_path(r"C:\Users\Dev\my_repo"), "/mnt/c/Users/Dev/my_repo")
        self.assertEqual(mini_ci.windows_to_wsl_path("D:/work/proj"), "/mnt/d/work/proj")
        self.assertEqual(mini_ci.windows_to_wsl_path("C:\\"), "/mnt/c")
        self.assertEqual(mini_ci.windows_to_wsl_path("/home/dev/repo"), "/home/dev/repo")

    def test_select_linux_backend(self) -> None:
        self.assertEqual(mini_ci.select_linux_backend("wsl"), "wsl")
        self.assertEqual(mini_ci.select_linux_backend("docker"), "docker")
        with self.assertRaises(ValueError):
            mini_ci.select_linux_backend("podman")
        self.assertEqual(
            mini_ci.select_linux_backend("auto", is_windows=True, which_fn=lambda x: "/wsl" if "wsl" in x else None),
            "wsl",
        )
        self.assertEqual(
            mini_ci.select_linux_backend("auto", is_windows=True, which_fn=lambda x: "/docker" if x == "docker" else None),
            "docker",
        )
        self.assertEqual(
            mini_ci.select_linux_backend("auto", is_windows=False, which_fn=lambda x: "/docker" if x == "docker" else None),
            "docker",
        )
        with self.assertRaises(RuntimeError):
            mini_ci.select_linux_backend("auto", is_windows=False, which_fn=lambda _x: None)

    def test_create_clean_snapshot_excludes_caches_and_custom_dirs(self) -> None:
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
        for junk in (".git", ".venv", "__pycache__", "custom_cache"):
            d = self.root / junk
            d.mkdir()
            (d / "dummy.txt").write_text("junk", encoding="utf-8")
        snap = mini_ci.create_clean_snapshot(self.root, exclude_dirs=["custom_cache"])
        self.addCleanup(lambda: mini_ci.shutil.rmtree(snap, ignore_errors=True))
        self.assertTrue((snap / "src" / "app.py").is_file())
        for junk in (".git", ".venv", "__pycache__", "custom_cache"):
            self.assertFalse((snap / junk).exists())

    def test_build_fast_env(self) -> None:
        base = {"EXISTING": "1"}
        env = mini_ci.build_fast_env(base, config={"env": {"APP_ENV": "ci"}}, simulate_ci_chrome=True)
        self.assertEqual(env["CI"], "true")
        self.assertEqual(env["MPLBACKEND"], "Agg")
        self.assertEqual(env["QT_QPA_PLATFORM"], "offscreen")
        self.assertEqual(env["CHROME_NO_SANDBOX"], "1")
        self.assertEqual(env["APP_ENV"], "ci")
        self.assertNotIn("CI", base)

    def test_build_ci_steps_monorepo_python_custom_and_targeted(self) -> None:
        # Standard python repo with pytest + ruff
        (self.root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
        steps = mini_ci.build_ci_steps(self.root, "py", which_fn=lambda x: f"/bin/{x}")
        self.assertEqual(steps, [["ruff", "check", "."], ["py", "-m", "pytest"]])
        steps_no_lint = mini_ci.build_ci_steps(self.root, "py", skip_lint=True, which_fn=lambda x: f"/bin/{x}")
        self.assertEqual(steps_no_lint, [["py", "-m", "pytest"]])
        # Custom config steps (including --skip-lint filtering)
        cfg = {"steps": ["{python} -m ruff check .", "{python} -m unittest"]}
        self.assertEqual(mini_ci.build_ci_steps(self.root, "py", config=cfg), [["py", "-m", "ruff", "check", "."], ["py", "-m", "unittest"]])
        self.assertEqual(mini_ci.build_ci_steps(self.root, "py", config=cfg, skip_lint=True), [["py", "-m", "unittest"]])
        # Targeted .py file without pytest
        targeted = mini_ci.build_ci_steps(
            self.root, "py", tests=["system-diagnostics/tests/test_mini_ci.py"], which_fn=lambda _x: None
        )
        self.assertEqual(
            targeted,
            [["py", "-m", "unittest", "discover", "-s", "system-diagnostics/tests", "-p", "test_mini_ci.py", "-v"]],
        )

    def test_build_wsl_script_and_docker_commands(self) -> None:
        steps = [[mini_ci.PY_TOKEN, "-m", "unittest", "discover", "-s", "tests"]]
        script = mini_ci.build_wsl_script(
            "/mnt/c/repo", steps, config={"env": {"MY_VAR": "a b"}, "pip_packages": ["pytest"]}, has_requirements=True
        )
        self.assertIn('CLEAN_HOME="$(mktemp -d)"', script)
        self.assertIn('export HOME="$CLEAN_HOME"', script)
        self.assertIn("export MY_VAR='a b'", script)
        self.assertIn('VENV_DIR="/tmp/mini_ci_venvs/$REQ_HASH"', script)
        self.assertIn('if [ ! -f "$VENV_DIR/.ready" ]; then', script)
        self.assertIn('import ensurepip', script)
        self.assertIn('"$PY_BIN" -m unittest discover -s tests', script)

        df = mini_ci.build_dockerfile("python:3.12-slim", config={"apt_packages": ["git"]}, has_requirements=True)
        self.assertIn("FROM python:3.12-slim", df)
        self.assertIn("apt-get install -y --no-install-recommends git", df)
        self.assertIn("COPY requirements.txt .", df)

        req_a = self.root / "requirements.txt"
        req_a.write_text("pytest==8.0.0\n", encoding="utf-8")
        tag_a = mini_ci._docker_image_tag(df, req_a)
        req_a.write_text("pytest==8.1.0\n", encoding="utf-8")
        tag_b = mini_ci._docker_image_tag(df, req_a)
        self.assertNotEqual(tag_a, tag_b)

        dcmd = mini_ci.build_docker_run_command(self.root, "python:3.12-slim", steps, config={"env": {"K": "V"}})
        self.assertEqual(dcmd[:3], ["docker", "run", "--rm"])
        self.assertIn("HOME=/tmp/mini_ci_home", dcmd)
        self.assertIn("K=V", dcmd)
        self.assertIn("python3 -m unittest discover -s tests", dcmd[-1])


class TestMiniCiCliExecution(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        tdir = self.root / "tests"
        tdir.mkdir()
        (tdir / "test_sample.py").write_text(
            "import os, unittest\n"
            "class SampleTest(unittest.TestCase):\n"
            "    def test_ci_env(self):\n"
            "        self.assertEqual(os.environ.get('CI'), 'true')\n",
            encoding="utf-8",
        )

    def test_cmd_ci_fast_execution_and_clean_snapshot(self) -> None:
        parser = diagnose.build_parser()
        args = parser.parse_args(["ci", "--path", str(self.root), "--fast", "--skip-lint", "--clean-snapshot"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = mini_ci.cmd_ci(args)
        self.assertEqual(rc, 0)
        self.assertIn("Mini-CI [fast]", buf.getvalue())

    def test_cmd_ci_dry_run_wsl_and_docker(self) -> None:
        parser = diagnose.build_parser()
        for backend, expected in (("wsl", "CLEAN_HOME"), ("docker", "HOME=/tmp/mini_ci_home")):
            args = parser.parse_args(["ci", "--path", str(self.root), "--linux", "--backend", backend, "--dry-run"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = mini_ci.cmd_ci(args)
            self.assertEqual(rc, 0)
            self.assertIn(expected, buf.getvalue())

    def test_cmd_ci_root_alias_parses_to_path(self) -> None:
        parser = diagnose.build_parser()
        args = parser.parse_args(["ci", "--root", str(self.root), "--fast", "--dry-run"])
        self.assertEqual(args.path, str(self.root))

    def test_cmd_ci_invalid_path_returns_2(self) -> None:
        parser = diagnose.build_parser()
        args = parser.parse_args(["ci", "--path", str(self.root / "does_not_exist"), "--dry-run"])
        err = io.StringIO()
        with redirect_stderr(err):
            rc = mini_ci.cmd_ci(args)
        self.assertEqual(rc, 2)

    def test_cmd_ci_wsl_streams_lf_bytes(self) -> None:
        from unittest import mock

        parser = diagnose.build_parser()
        args = parser.parse_args(["ci", "--path", str(self.root), "--linux", "--backend", "wsl"])
        with mock.patch("mini_ci.subprocess.run", return_value=mock.Mock(returncode=0)) as m_run:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = mini_ci.cmd_ci(args)
        self.assertEqual(rc, 0)
        payload = m_run.call_args.kwargs["input"]
        self.assertIsInstance(payload, bytes)
        self.assertNotIn(b"\r\n", payload)
        self.assertIn(b"set -euo pipefail\n", payload)


if __name__ == "__main__":
    unittest.main()
