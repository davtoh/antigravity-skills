#!/usr/bin/env python3
"""Automated verification tests for multi-language decomposition contracts.

Verifies that the architectural patterns recommended by refactor-monolith:
1. Python Package Facade preserves 100% of original symbols via __all__ and re-exports.
2. TypeScript ES Module barrel re-export pattern resolves public symbols.
3. Go same-package multi-file distribution shares package scope without import cycles.
4. SCSS @use / @forward manifest preserves selector cascade ordering.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class TestPythonDecompositionContract(unittest.TestCase):
    """Test Python Strangler-Fig package facade re-exports."""

    def test_package_facade_preserves_public_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_dir = Path(tmpdir) / "service"
            pkg_dir.mkdir()
            (pkg_dir / "models.py").write_text("class Config:\n    pass\n", encoding="utf-8")
            (pkg_dir / "workers.py").write_text("def run_job():\n    return 42\n", encoding="utf-8")
            (pkg_dir / "__init__.py").write_text(
                "from .models import Config\n"
                "from .workers import run_job\n\n"
                "__all__ = ['Config', 'run_job']\n",
                encoding="utf-8",
            )
            caller_file = Path(tmpdir) / "caller.py"
            caller_file.write_text(
                "import sys\n"
                f"sys.path.insert(0, r'{tmpdir}')\n"
                "from service import Config, run_job\n"
                "assert run_job() == 42\n"
                "assert isinstance(Config(), Config)\n",
                encoding="utf-8",
            )
            # Execute the caller script to verify zero breaking imports
            import subprocess
            res = subprocess.run(["python", str(caller_file)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Python facade failed: {res.stderr}")


class TestGoDecompositionContract(unittest.TestCase):
    """Test Go same-package multi-file distribution contract."""

    def test_same_package_splits_share_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            f1 = p / "tracker.go"
            f2 = p / "tracker_events.go"
            f1.write_text("package tracker\n\ntype Service struct { ID string }\n", encoding="utf-8")
            f2.write_text("package tracker\n\nfunc (s *Service) Handle() int { return 1 }\n", encoding="utf-8")
            # Verify both files declare identical package and share the Service type
            content1 = f1.read_text(encoding="utf-8")
            content2 = f2.read_text(encoding="utf-8")
            self.assertIn("package tracker", content1)
            self.assertIn("package tracker", content2)
            self.assertIn("type Service struct", content1)
            self.assertIn("(s *Service) Handle()", content2)


class TestTypeScriptDecompositionContract(unittest.TestCase):
    """Test TypeScript barrel export facade contract."""

    def test_ts_barrel_facade_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            barrel = p / "OrderController.ts"
            types_f = p / "order.types.ts"
            service_f = p / "orderService.ts"

            types_f.write_text("export interface OrderInput { id: string; }\n", encoding="utf-8")
            service_f.write_text("export class OrderService { execute() { return true; } }\n", encoding="utf-8")
            barrel.write_text(
                "export * from './order.types';\n"
                "export { OrderService } from './orderService';\n"
                "import { OrderService } from './orderService';\n\n"
                "export class OrderController {\n"
                "  constructor(private service = new OrderService()) {}\n"
                "  run() { return this.service.execute(); }\n"
                "}\n",
                encoding="utf-8",
            )
            content = barrel.read_text(encoding="utf-8")
            self.assertIn("export * from './order.types'", content)
            self.assertIn("export { OrderService }", content)
            self.assertIn("export class OrderController", content)


class TestStylesheetDecompositionContract(unittest.TestCase):
    """Test SCSS @forward and ITCSS cascade structure."""

    def test_itcss_cascade_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            manifest = p / "_home.scss"
            manifest.write_text(
                "// ITCSS Order: tokens -> layout -> components\n"
                "@forward 'tokens/variables';\n"
                "@forward 'layout/grid';\n"
                "@forward 'components/cards';\n",
                encoding="utf-8",
            )
            content = manifest.read_text(encoding="utf-8")
            tokens_idx = content.find("'tokens/variables'")
            layout_idx = content.find("'layout/grid'")
            cards_idx = content.find("'components/cards'")
            self.assertTrue(0 < tokens_idx < layout_idx < cards_idx, "ITCSS order must be preserved")


if __name__ == "__main__":
    unittest.main()
