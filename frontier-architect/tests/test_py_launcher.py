"""Cross-platform launcher tests for scripts/py.sh (POSIX) and scripts/py.cmd (Windows)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
SH_LAUNCHER = SCRIPTS_DIR / "py.sh"
CMD_LAUNCHER = SCRIPTS_DIR / "py.cmd"
SH_BIN = shutil.which("sh")


class LauncherPackagingInvariantsTests(unittest.TestCase):
    def test_both_launchers_exist_and_py_sh_uses_lf_only(self):
        self.assertTrue(SH_LAUNCHER.is_file())
        self.assertTrue(CMD_LAUNCHER.is_file())
        raw_sh = SH_LAUNCHER.read_bytes()
        self.assertNotIn(b"\r\n", raw_sh, "py.sh must keep LF line endings even on Windows checkouts")
        self.assertTrue(raw_sh.startswith(b"#!/bin/sh\n"))


@unittest.skipIf(os.name == "nt" and not SH_BIN, "sh not available on this Windows host")
class PyShLauncherTests(unittest.TestCase):
    def setUp(self):
        self._sh = SH_BIN or "/bin/sh"

    def test_runs_script_with_args_and_propagates_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            script = root / "echo.py"
            script.write_text(
                "import sys; print(sys.version_info[0], *sys.argv[1:]); sys.exit(int(sys.argv[1]))\n",
                encoding="utf-8",
            )
            ok = subprocess.run([self._sh, str(SH_LAUNCHER), str(script), "0", "a b"], capture_output=True, text=True, timeout=30)
            bad = subprocess.run([self._sh, str(SH_LAUNCHER), str(script), "2"], capture_output=True, text=True, timeout=30)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(ok.stdout.strip(), "3 0 a b")
        self.assertEqual(bad.returncode, 2)

    @unittest.skipIf(os.name == "nt", "POSIX empty-PATH isolation uses /bin/sh directly")
    def test_fails_cleanly_without_python(self):
        out = subprocess.run(
            ["/bin/sh", str(SH_LAUNCHER), "x.py"],
            capture_output=True, text=True, env={"PATH": "/nonexistent"}, timeout=30,
        )
        self.assertEqual(out.returncode, 127)
        self.assertIn("no Python 3.10+", out.stderr)


@unittest.skipUnless(os.name == "nt", "py.cmd requires Windows cmd.exe")
class PyCmdLauncherTests(unittest.TestCase):
    def _clean_env(self, **overrides: str) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k.upper() != "VIRTUAL_ENV"}
        env.update(overrides)
        return env

    def test_runs_script_and_preserves_parentheses_and_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp).resolve() / "echo.py"
            script.write_text("import json, sys; print(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
            out = subprocess.run(
                ["cmd", "/c", str(CMD_LAUNCHER), str(script), "pytest (45 passed)", "two words"],
                capture_output=True, text=True, env=self._clean_env(), timeout=30,
            )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), '["pytest (45 passed)", "two words"]')

    def test_propagates_nonzero_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp).resolve() / "exit_code.py"
            script.write_text("import sys; sys.exit(int(sys.argv[1]))\n", encoding="utf-8")
            for expected in (1, 2, 124):
                out = subprocess.run(
                    ["cmd", "/c", str(CMD_LAUNCHER), str(script), str(expected)],
                    capture_output=True, text=True, env=self._clean_env(), timeout=30,
                )
                self.assertEqual(out.returncode, expected, f"Expected exit {expected}, got {out.returncode}")

    def test_fails_cleanly_with_127_when_no_python_on_path(self):
        with tempfile.TemporaryDirectory() as empty_dir:
            sys_root = os.environ.get("SystemRoot", r"C:\Windows")
            comspec = os.environ.get("COMSPEC", rf"{sys_root}\System32\cmd.exe")
            env = {"PATH": str(Path(empty_dir).resolve()), "SystemRoot": sys_root, "COMSPEC": comspec}
            out = subprocess.run([comspec, "/c", str(CMD_LAUNCHER), "x.py"], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(out.returncode, 127)
        self.assertIn("no Python 3.10+", out.stderr)

    def test_skips_old_python_shim_and_falls_back_to_valid_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            fake_bin = root / "fake_bins"
            fake_bin.mkdir()
            # Isolated PATH with no py.exe: fake python.cmd exits 1 (< 3.10), valid python3.cmd delegates to sys.executable.
            (fake_bin / "python.cmd").write_text("@echo off\r\nexit /b 1\r\n", encoding="utf-8")
            (fake_bin / "python3.cmd").write_text(f'@echo off\r\n"{sys.executable}" %*\r\n', encoding="utf-8")
            script = root / "ok.py"
            script.write_text("import sys; print(sys.version_info[0])\n", encoding="utf-8")
            sys_root = os.environ.get("SystemRoot", r"C:\Windows")
            comspec = os.environ.get("COMSPEC", rf"{sys_root}\System32\cmd.exe")
            env = {"PATH": str(fake_bin), "SystemRoot": sys_root, "COMSPEC": comspec}
            out = subprocess.run([comspec, "/c", str(CMD_LAUNCHER), str(script)], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "3")

    def test_no_self_recursion_when_cwd_is_scripts_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp).resolve() / "ok.py"
            script.write_text("print('cwd-ok')\n", encoding="utf-8")
            out = subprocess.run(
                ["cmd", "/c", "py.cmd", str(script)],
                cwd=SCRIPTS_DIR, capture_output=True, text=True, env=self._clean_env(), timeout=15,
            )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "cwd-ok")


if __name__ == "__main__":
    unittest.main()
