#!/usr/bin/env python3
"""HTML-to-CSS layout class verification helper for surface_verifier."""

import re
from pathlib import Path

_HTML_CLASS_ATTR_RE = re.compile(r"""\bclass\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_HTML_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>([\s\S]*?)</style>", re.IGNORECASE)
_CSS_CLASS_SEL_RE = re.compile(r"\.([a-zA-Z_-][a-zA-Z0-9_-]*)")

_LAYOUT_TOKENS = frozenset({
    "grid", "flex", "layout", "split", "pane", "stack",
    "row", "col", "cols", "rows", "wide", "resizable", "sidebar", "wrapper",
})


def _is_layout_class(cls_name: str) -> bool:
    """Return True if a hyphen-delimited class token denotes a structural layout class."""
    return bool(set(cls_name.lower().split("-")) & _LAYOUT_TOKENS)


def check_undefined_layout_classes(
    html_files: list[Path],
    css_files: list[Path],
    target_path: Path,
) -> list[dict[str, str]]:
    """Flag HTML layout classes that have no matching .class selector in CSS."""
    css_classes: set[str] = set()
    for cp in css_files:
        text = cp.read_text(encoding="utf-8", errors="replace")
        css_classes.update(_CSS_CLASS_SEL_RE.findall(text))
    for hp in html_files:
        htext = hp.read_text(encoding="utf-8", errors="replace")
        for blk in _HTML_STYLE_BLOCK_RE.findall(htext):
            css_classes.update(_CSS_CLASS_SEL_RE.findall(blk))
    if not css_classes:
        return []

    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for hp in html_files:
        rel = str(hp.relative_to(target_path)).replace("\\", "/") if hp.is_relative_to(target_path) else hp.name
        htext = hp.read_text(encoding="utf-8", errors="replace")
        for raw_attr in _HTML_CLASS_ATTR_RE.findall(htext):
            for cls_name in raw_attr.split():
                if "{{" in cls_name or "{%" in cls_name:
                    continue
                if _is_layout_class(cls_name) and cls_name not in css_classes:
                    key = (cls_name, rel)
                    if key not in seen:
                        seen.add(key)
                        findings.append({"class": cls_name, "file": rel})
    return findings
