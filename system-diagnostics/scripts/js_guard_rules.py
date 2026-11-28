#!/usr/bin/env python3
"""JavaScript runtime & SPA lifecycle AST/lexer guard rules (system-diagnostics)."""

import re
from typing import Any

_RAF_RE = re.compile(r"\brequestAnimationFrame\s*\(")
_DPR_RE = re.compile(r"\bsyncCanvasDpr\s*\(")
_TIMEUPDATE_RE = re.compile(r"\baddEventListener\s*\(\s*(['\"])timeupdate\1\s*,")
_LOCALSTORAGE_RE = re.compile(r"\blocalStorage\.(?:setItem|getItem|removeItem)\s*\(")
_TIMER_WRAP_RE = re.compile(r"\b(?:setTimeout|requestIdleCallback)\s*\(")
_NAVTAB_FOREACH_RE = re.compile(
    r"(?:\bnavTabs|document\.querySelectorAll\s*\(\s*(['\"])\.nav-tab\1\s*\))\s*\.forEach\s*\("
)
_NAVTAB_DIRECT_RE = re.compile(r"\bnavTab\w*\.addEventListener\s*\(\s*(['\"])click\1\s*,")
_PRIVATE_SWITCH_TAB_RE = re.compile(r"(?<![.\w$])switchTab\s*\(")


def _strip_js_comments(text: str) -> str:
    """Replace JS line/block comments with spaces while preserving line numbers."""
    out: list[str] = []
    i, n = 0, len(text)
    quote = ""
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
        elif ch in ("'", '"', "`"):
            quote = ch
            out.append(ch)
            i += 1
        elif ch == "/" and nxt == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
        elif ch == "/" and nxt == "*":
            out.extend((" ", " "))
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i + 1 < n:
                out.extend((" ", " "))
                i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _find_paren_span(clean_text: str, open_idx: int) -> tuple[int, int] | None:
    """Return (open_idx + 1, close_idx) for balanced parentheses starting at open_idx."""
    depth, n = 0, len(clean_text)
    quote = ""
    i = open_idx
    while i < n:
        ch = clean_text[i]
        if quote:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return open_idx + 1, i
        i += 1
    return None


def _collect_timer_spans(body: str) -> list[tuple[int, int]]:
    """Collect argument spans for setTimeout/requestIdleCallback calls inside a handler."""
    spans: list[tuple[int, int]] = []
    for m in _TIMER_WRAP_RE.finditer(body):
        if span := _find_paren_span(body, m.end() - 1):
            spans.append(span)
    return spans


def _make_finding(
    rule_id: str, severity: str, clean_text: str, pos: int, msg: str, fix: str
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "category": "BAD_LOGIC",
        "severity": severity,
        "track": "architectural",
        "line": clean_text.count("\n", 0, pos) + 1,
        "message": msg,
        "suggested_fix": fix,
    }


def _scan_raf_dpr(clean_text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for m in _RAF_RE.finditer(clean_text):
        span = _find_paren_span(clean_text, m.end() - 1)
        if not span:
            continue
        s, e = span
        for hit in _DPR_RE.finditer(clean_text[s:e]):
            findings.append(_make_finding(
                "JS_RAF_DPR_RESIZE", "HIGH", clean_text, s + hit.start(),
                "Calling syncCanvasDpr() inside requestAnimationFrame() mutates canvas dimensions every frame and causes layout reflow/playback stalls.",
                "Resize canvas DPR only on ResizeObserver/load/video metadata changes, outside requestAnimationFrame().",
            ))
    return findings


def _scan_timeupdate_storage(clean_text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for m in _TIMEUPDATE_RE.finditer(clean_text):
        open_idx = clean_text.find("(", m.start())
        span = _find_paren_span(clean_text, open_idx) if open_idx >= 0 else None
        if not span:
            continue
        s, e = span
        body = clean_text[s:e]
        timer_spans = _collect_timer_spans(body)
        for hit in _LOCALSTORAGE_RE.finditer(body):
            if any(ts <= hit.start() <= te for ts, te in timer_spans):
                continue
            findings.append(_make_finding(
                "JS_HOT_EVENT_LOCALSTORAGE", "MEDIUM", clean_text, s + hit.start(),
                "Synchronous localStorage access inside a 'timeupdate' listener causes main-thread thrash at high playback speeds.",
                "Debounce or defer localStorage persistence via setTimeout() outside the hot timeupdate path.",
            ))
    return findings


def _scan_private_switch_tab(clean_text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen_lines: set[int] = set()
    for regex in (_NAVTAB_FOREACH_RE, _NAVTAB_DIRECT_RE):
        for m in regex.finditer(clean_text):
            open_idx = clean_text.rfind("(", m.start(), m.end())
            span = _find_paren_span(clean_text, open_idx) if open_idx >= 0 else None
            if not span:
                continue
            s, e = span
            body = clean_text[s:e]
            if regex is _NAVTAB_FOREACH_RE and "addEventListener" not in body:
                continue
            for hit in _PRIVATE_SWITCH_TAB_RE.finditer(body):
                finding = _make_finding(
                    "JS_PRIVATE_SWITCH_TAB_BINDING", "HIGH", clean_text, s + hit.start(),
                    "Binding .nav-tab click to private switchTab() bypasses window.switchTab wrappers (e.g., nav_tabs_manager.js tab-changed events).",
                    "Invoke window.switchTab(...) inside .nav-tab click handlers instead of a closure-local switchTab.",
                )
                if finding["line"] not in seen_lines:
                    seen_lines.add(finding["line"])
                    findings.append(finding)
    return findings


def scan_js_runtime_guards(rel_path: str, text: str) -> list[dict[str, Any]]:
    """Scan JavaScript source for SPA runtime/playback anti-patterns."""
    clean_text = _strip_js_comments(text)
    return (
        _scan_raf_dpr(clean_text)
        + _scan_timeupdate_storage(clean_text)
        + _scan_private_switch_tab(clean_text)
    )
