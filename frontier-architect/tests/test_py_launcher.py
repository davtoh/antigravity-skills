"""py.sh launcher: resolves a Python 3.10+ and forwards args (skips on Windows)."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "scripts" / "py.sh"


@unittest.skipIf(os.name == "nt", "py.sh is POSIX; py.cmd covers Windows")
class PyLauncherTests(unittest.TestCase):
    def test_runs_script_with_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp).resolve() / "echo.py"
            script.write_text("import sys; print(sys.version_info[0], *sys.argv[1:])\n", encoding="utf-8")
            out = subprocess.run(["sh", str(LAUNCHER), str(script), "a", "b"],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.split(), ["3", "a", "b"])

    def test_fails_cleanly_without_python(self):
        env = {"PATH": "/nonexistent"}
        out = subprocess.run([sys.executable and "/bin/sh", str(LAUNCHER), "x.py"],
                             capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(out.returncode, 127)
        self.assertIn("no Python 3.10+", out.stderr)

    def test_windows_twin_exists(self):
        self.assertTrue(LAUNCHER.with_name("py.cmd").is_file())


if __name__ == "__main__":
    unittest.main()
