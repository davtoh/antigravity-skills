#!/usr/bin/env python3
"""Unit tests for system-diagnostics arch_mapper.py."""

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import arch_mapper
import diagnose


class TestArchMapper(unittest.TestCase):
    """Verify AST architecture scanning, modularity budgets, and CLI integration."""

    def test_scan_architecture_detects_routes_cli_and_unused(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pkg = root / "mypkg"
            api = root / "web"
            pkg.mkdir()
            api.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "core.py").write_text(
                "import argparse\n"
                "def build_cli():\n"
                "    p = argparse.ArgumentParser()\n"
                "    p.add_argument('--mode')\n"
                "    return p\n",
                encoding="utf-8",
            )
            (api / "__init__.py").write_text("", encoding="utf-8")
            (api / "routes.py").write_text(
                "from fastapi import APIRouter\n"
                "from mypkg.core import build_cli\n"
                "from mypkg import unused_sym\n"
                "router = APIRouter(prefix='/api/v1')\n"
                "@router.get('/health')\n"
                "def health():\n"
                "    return build_cli()\n",
                encoding="utf-8",
            )

            report = arch_mapper.scan_architecture(root)
            self.assertEqual(report["routes_count"], 1)
            self.assertEqual(report["routes_by_file"]["web/routes.py"][0]["path"], "/api/v1/health")
            self.assertEqual(report["cross_package_coupling"]["web"], ["mypkg", "mypkg.core"])
            unused = {u["file"]: u["symbols"] for u in report["unused_internal_or_module_imports"]}
            self.assertIn("mypkg.unused_sym", unused["web/routes.py"])
            self.assertIn("cli_surfaces", report)
            self.assertEqual(report["cli_surfaces"][0]["flags"], ["--mode"])

    def test_scan_architecture_flags_modularity_overruns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            big = root / "big_mod.py"
            methods = "\n".join(f"    def m{i}(self): pass" for i in range(14))
            padding = "\n".join("# pad" for _ in range(350))
            big.write_text(f"class GodClass:\n{methods}\n{padding}\n", encoding="utf-8")

            report = arch_mapper.scan_architecture(root)
            viol = report["modularity_violations"]
            self.assertEqual(viol["files_350_to_499"][0]["path"], "big_mod.py")
            self.assertEqual(viol["classes_over_budget"][0]["name"], "GodClass")
            self.assertEqual(viol["classes_over_budget"][0]["methods"], 14)

    def test_diagnose_parser_registers_arch_map(self):
        parser = diagnose.build_parser()
        args = parser.parse_args(["arch-map", "--json", "--full"])
        self.assertEqual(args.subcommand, "arch-map")
        self.assertTrue(args.json)
        self.assertTrue(args.full)

    def test_cmd_arch_map_writes_out_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "sample.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
            out_file = root / "arch.json"
            rc = arch_mapper.cmd_arch_map(
                argparse.Namespace(path=str(root), include_tests=False, json=True, full=False, out=str(out_file))
            )
            self.assertEqual(rc, 0)
            parsed = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(parsed["total_files"], 1)

    def test_unused_imports_respects_all_and_ignores_docstrings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pkg = root / "mypkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "defs.py").write_text("class A: pass\nclass B: pass\nclass C: pass\n", encoding="utf-8")
            (pkg / "consumer.py").write_text(
                '"""Mentions A in docstring and "A" in text."""\n'
                "from mypkg.defs import A, B, C\n"
                "__all__ = ['B']\n"
                "def use(x: 'C') -> str:\n"
                "    return 'A'\n",
                encoding="utf-8",
            )
            report = arch_mapper.scan_architecture(root)
            unused = {u["file"]: u["symbols"] for u in report["unused_internal_or_module_imports"]}
            self.assertEqual(unused["mypkg/consumer.py"], ["mypkg.defs.A"])

    def test_flags_long_functions_and_explicit_truncation_notice(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            body = "\n".join("    x += 1" for _ in range(42))
            (root / "long_fn.py").write_text(f"def too_long():\n    x = 0\n{body}\n    return x\n", encoding="utf-8")
            for i in range(32):
                (root / f"m{i:02d}.py").write_text("import sys\n", encoding="utf-8")
            report = arch_mapper.scan_architecture(root)
            self.assertEqual(report["modularity_violations"]["functions_over_40"][0]["name"], "too_long")
            md = arch_mapper.format_markdown(report, full=False)
            self.assertIn("more file(s) omitted", md)
            md_full = arch_mapper.format_markdown(report, full=True)
            self.assertNotIn("more file(s) omitted", md_full)

    def test_scan_architecture_single_file_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pkg = root / "mypkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            core = pkg / "core.py"
            core.write_text("def helper():\n    return 42\n", encoding="utf-8")

            report = arch_mapper.scan_architecture(core)
            self.assertEqual(report["total_files"], 1)
            self.assertIn("mypkg", report["local_packages"])
            self.assertEqual(report["directories"]["mypkg"]["files"], 1)

    def test_diagnose_arch_map_accepts_multiple_subpaths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            for sub in ("pkg_a", "pkg_b", "pkg_c"):
                d = root / sub
                d.mkdir()
                (d / "__init__.py").write_text("", encoding="utf-8")
                (d / "mod.py").write_text("def fn():\n    return 1\n", encoding="utf-8")
            parser = diagnose.build_parser()
            out_file = root / "multi.json"
            args = parser.parse_args([
                "arch-map", "--path", str(root / "pkg_a"), str(root / "pkg_b"),
                "--json", "--out", str(out_file),
            ])
            rc = arch_mapper.cmd_arch_map(args)
            self.assertEqual(rc, 0)
            parsed = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(parsed["total_files"], 4)
            self.assertIn("pkg_a", parsed["directories"])
            self.assertIn("pkg_b", parsed["directories"])
            self.assertNotIn("pkg_c", parsed["directories"])

    def test_unused_imports_ignores_importerror_availability_probes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "probes.py").write_text(
                "import unused_top\n"
                "try:\n"
                "    import zlib\n"
                "    HAS_ZLIB = True\n"
                "except ImportError:\n"
                "    HAS_ZLIB = False\n"
                "try:\n"
                "    from scipy.optimize import linear_sum_assignment\n"
                "except (ModuleNotFoundError, OSError):\n"
                "    linear_sum_assignment = None\n"
                "try:\n"
                "    import unused_non_import_try\n"
                "except Exception:\n"
                "    pass\n"
                "def check():\n"
                "    return HAS_ZLIB\n",
                encoding="utf-8",
            )
            report = arch_mapper.scan_architecture(root)
            unused = {u["file"]: u["symbols"] for u in report["unused_internal_or_module_imports"]}
            self.assertEqual(unused["probes.py"], ["unused_non_import_try", "unused_top"])


if __name__ == "__main__":
    unittest.main()
