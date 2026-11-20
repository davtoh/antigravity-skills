#!/usr/bin/env python3
"""Automated unit tests for static_auditor and diagnose.py audit subcommand."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import static_auditor


class TestStaticAuditor(unittest.TestCase):
    """Test static defect scanning, platform smell detection, and callable smoke checks."""

    def test_callable_smoke_clean_classes_and_functions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "clean.py").write_text(
                "import abc\n"
                "class BaseWorker(abc.ABC):\n"
                "    @abc.abstractmethod\n"
                "    def run(self):\n"
                "        pass\n\n"
                "class ServiceWorker:\n"
                "    def __init__(self, name: str = 'default'):\n"
                "        self.name = name\n"
                "    def execute(self):\n"
                "        return 1\n\n"
                "def calculate(factor: int = 1) -> int:\n"
                "    return 42 * factor\n",
                encoding="utf-8",
            )
            issues = static_auditor.audit_callable_smoke(tmp)
            self.assertEqual(issues, [])

    def test_callable_smoke_skips_exception_subclasses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "errors.py").write_text(
                "class CameraError(Exception):\n"
                "    pass\n",
                encoding="utf-8",
            )
            issues = static_auditor.audit_callable_smoke(tmp / "errors.py")
            self.assertEqual(issues, [])

    def test_callable_smoke_skips_typing_protocol_and_reports_concrete_lineno(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "protos.py").write_text(
                "from typing import Protocol, runtime_checkable\n\n"
                "@runtime_checkable\n"
                "class SemanticProvider(Protocol):\n"
                "    name: str\n"
                "    def synthesize(self, query: str) -> str: ...\n\n"
                "class BrokenProvider:\n"
                "    def __init__(self) -> None:\n"
                "        raise TypeError('bad concrete init')\n",
                encoding="utf-8",
            )
            issues = static_auditor.audit_callable_smoke(tmp / "protos.py")
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["type"], "initialization_type_error")
            self.assertIn("BrokenProvider", issues[0]["message"])
            self.assertEqual(issues[0]["line"], 8)

    def test_callable_smoke_catches_init_type_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "faulty.py").write_text(
                "class FaultyClass:\n"
                "    def __init__(self):\n"
                "        raise TypeError('missing required parameter: stage')\n",
                encoding="utf-8",
            )
            issues = static_auditor.audit_callable_smoke(tmp)
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["type"], "initialization_type_error")
            self.assertIn("FaultyClass", issues[0]["message"])

    def test_callable_smoke_catches_syntax_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "broken_syntax.py").write_text("def broken(\n", encoding="utf-8")
            issues = static_auditor.audit_callable_smoke(tmp)
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["type"], "syntax_error")

    def test_platform_smells_flags_dynamic_import_ladder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "ladder.py").write_text(
                "try:\n"
                "    import win32api\n"
                "except ImportError:\n"
                "    win32api = None\n",
                encoding="utf-8",
            )
            smells = static_auditor.audit_platform_smells(tmp)
            self.assertEqual(len(smells), 1)
            self.assertEqual(smells[0]["type"], "dynamic_platform_import_ladder")
            self.assertIn("win32api", smells[0]["message"])

    def test_platform_smells_ignores_clean_imports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "clean_platform.py").write_text(
                "import sys\n"
                "if sys.platform == 'win32':\n"
                "    import os\n",
                encoding="utf-8",
            )
            smells = static_auditor.audit_platform_smells(tmp)
            self.assertEqual(smells, [])

    def test_static_typecheckers_pass(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0), # ruff --version
                MagicMock(returncode=0, stdout=""), # ruff check
                MagicMock(returncode=0), # mypy --version
                MagicMock(returncode=0, stdout=""), # mypy check
            ]
            with tempfile.TemporaryDirectory() as tmpdir:
                code, logs = static_auditor.run_static_typecheckers(Path(tmpdir), "python")
                self.assertEqual(code, 0)
                self.assertTrue(any("PASS" in l for l in logs))

    def test_static_typecheckers_token_truncation_top5(self) -> None:
        with patch("subprocess.run") as mock_run:
            # 8 error lines from ruff
            err_lines = "\n".join(f"file.py:{i}: error: E{i}" for i in range(8))
            mock_run.side_effect = [
                MagicMock(returncode=0), # ruff --version
                MagicMock(returncode=1, stdout=err_lines), # ruff check fails
                MagicMock(returncode=1), # mypy --version fails
            ]
            with tempfile.TemporaryDirectory() as tmpdir:
                code, logs = static_auditor.run_static_typecheckers(Path(tmpdir), "python")
                self.assertEqual(code, 1)
                self.assertTrue(any("omitted to conserve tokens" in l for l in logs))

    def test_cmd_audit_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "test.py").write_text("x = 1\n", encoding="utf-8")
            args = MagicMock(
                callable_smoke=True,
                smells=True,
                typecheck=False,
                json=True,
                strict=False,
            )
            with patch("builtins.print") as mock_print:
                code = static_auditor.cmd_audit(tmp, "python", args)
                self.assertEqual(code, 0)
                printed_json = mock_print.call_args[0][0]
                data = json.loads(printed_json)
                self.assertIn("status", data)
                self.assertEqual(data["status"], "PASS")

    def test_cmd_audit_strict_mode_fails_on_smells(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "smell.py").write_text(
                "try:\n"
                "    import fcntl\n"
                "except ImportError:\n"
                "    pass\n",
                encoding="utf-8",
            )
            args = MagicMock(
                callable_smoke=False,
                smells=True,
                typecheck=False,
                json=False,
                strict=True,
            )
            code = static_auditor.cmd_audit(tmp, "python", args)
            self.assertEqual(code, 1)

    def test_diagnose_audit_accepts_multiple_paths(self) -> None:
        import diagnose

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            f1 = tmp / "a.py"
            f2 = tmp / "b.py"
            f1.write_text("x = 1\n", encoding="utf-8")
            f2.write_text("y = 2\n", encoding="utf-8")
            args = MagicMock(
                path=[str(f1), str(f2)],
                callable_smoke=False,
                smells=True,
                typecheck=False,
                json=False,
                strict=True,
            )
            code = diagnose.cmd_audit(args)
            self.assertEqual(code, 0)

    def test_audit_modularity_budgets_flags_long_function_and_custom_max_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            f = tmp / "sample.py"
            body = "\n".join("    x += 1" for _ in range(42))
            f.write_text(f"def too_long():\n    x = 0\n{body}\n    return x\n", encoding="utf-8")
            args = MagicMock(
                callable_smoke=False,
                smells=False,
                typecheck=False,
                json=False,
                strict=False,
                max_lines=40,
                max_fn_lines=40,
            )
            code = static_auditor.cmd_audit(f, "python", args)
            self.assertEqual(code, 1)

    def test_cmd_audit_missing_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "does_not_exist.py"
            args = MagicMock(callable_smoke=False, smells=False, typecheck=False, json=True, strict=False, max_lines=None, max_fn_lines=None)
            with patch("builtins.print") as mock_print:
                code = static_auditor.cmd_audit(missing, "python", args)
                self.assertEqual(code, 1)
                data = json.loads(mock_print.call_args[0][0])
                self.assertEqual(data["status"], "DEFECTS_FOUND")
                self.assertEqual(data["issues"][0]["type"], "missing_file")

    def test_callable_smoke_skips_lazy_proxy_raising_on_attribute_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "lazy_mod.py").write_text(
                "class _LazyProxy:\n"
                "    def __getattribute__(self, name):\n"
                "        raise RuntimeError('Requested settings, but settings are not configured')\n"
                "settings = _LazyProxy()\n"
                "class Ok:\n"
                "    pass\n",
                encoding="utf-8",
            )
            issues = static_auditor.audit_callable_smoke(tmp / "lazy_mod.py")
            self.assertEqual(issues, [])

    def test_callable_smoke_skips_ctypes_structures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "win_structs.py").write_text(
                "import ctypes\n"
                "class IO_COUNTERS(ctypes.Structure):\n"
                "    _fields_ = [('ReadOperationCount', ctypes.c_uint64)]\n",
                encoding="utf-8",
            )
            issues = static_auditor.audit_callable_smoke(tmp / "win_structs.py")
            self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
