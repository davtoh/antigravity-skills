#!/usr/bin/env python3
"""Viewport parsing and multi-viewport audit helpers for cdp_inspect.py."""

import argparse
import json
from pathlib import Path
from typing import Any


def parse_viewport(value: str) -> tuple[int, int]:
    """Parse 'WIDTHxHEIGHT' viewport string into integer tuple."""
    try:
        width, height = (int(x) for x in value.lower().split("x"))
        return width, height
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--window-size must look like 1440x900, got '{value}'") from exc


def parse_viewports_list(value: str | None) -> list[tuple[int, int]]:
    """Parse comma-separated viewport specs such as '960x720,1280x800,1920x1080'."""
    if not value:
        return []
    return [parse_viewport(part.strip()) for part in value.split(",") if part.strip()]


def build_generic_audit_js(custom_selectors: list[str], stability_ms: float = 0) -> str:
    """Assemble audit_layout_extra.js + audit_layout.js with injected runtime config."""
    scripts_dir = Path(__file__).parent
    extra_path = scripts_dir / "audit_layout_extra.js"
    extra_js = extra_path.read_text(encoding="utf-8") if extra_path.is_file() else ""
    base_js = (scripts_dir / "audit_layout.js").read_text(encoding="utf-8")
    return (
        f"window.__FRONTIER_SELECTORS__ = {json.dumps(custom_selectors)};\n"
        f"window.__FRONTIER_STABILITY_MS__ = {float(stability_ms)};\n"
        f"{extra_js}\n{base_js}"
    )


async def run_multi_viewport_audit(
    cdp: Any,
    session_id: str | None,
    evaluate_fn: Any,
    viewports: list[tuple[int, int]],
    custom_selectors: list[str],
    stability_ms: float = 0,
) -> list[dict[str, Any]]:
    """Run audit_layout across multiple viewports via Emulation.setDeviceMetricsOverride."""
    reports: list[dict[str, Any]] = []
    audit_js = build_generic_audit_js(custom_selectors, stability_ms)
    for width, height in viewports:
        await cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
            session_id=session_id,
        )
        res = await evaluate_fn(cdp, session_id, audit_js)
        if isinstance(res, dict):
            res.setdefault("requestedViewport", f"{width}x{height}")
            reports.append(res)
    return reports


async def execute_layout_audit(
    cdp: Any,
    session_id: str | None,
    evaluate_fn: Any,
    args: Any,
) -> int:
    """Execute single- or multi-viewport layout audit and return strict exit code."""
    custom_sels = [s.strip() for s in args.selectors.split(",") if s.strip()] if args.selectors else []
    viewports = parse_viewports_list(getattr(args, "viewports", None))
    if viewports and args.audit_layout:
        reports = await run_multi_viewport_audit(cdp, session_id, evaluate_fn, viewports, custom_sels, getattr(args, "stability_ms", 0))
        print(json.dumps({"viewports": reports}, indent=2, ensure_ascii=False))
        if getattr(args, "strict", False) and any(
            r.get("layoutOverflowWarnings") or r.get("layoutJitterWarnings") or r.get("viewport", {}).get("hasHorizontalWindowScroll", False)
            for r in reports
        ):
            return 1
        return 0
    if args.audit_layout or custom_sels:
        result = await evaluate_fn(cdp, session_id, build_generic_audit_js(custom_sels, getattr(args, "stability_ms", 0)))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if getattr(args, "strict", False) and isinstance(result, dict):
            if result.get("layoutOverflowWarnings") or result.get("layoutJitterWarnings") or result.get("viewport", {}).get("hasHorizontalWindowScroll", False):
                return 1
    return 0
