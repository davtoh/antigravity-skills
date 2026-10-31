#!/usr/bin/env python3
"""Cross-platform, standard-library static surface scanners for codebases.

Extracts DOM element IDs, interactive controls, inline event handlers,
JavaScript window.* exports, event listeners, Python routes, mutable globals,
and stylesheet custom properties from raw text without external dependencies.
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class HtmlSurface:
    """Extracted interactive surface of an HTML file or template."""
    ids: list[str] = field(default_factory=list)
    selects: list[str] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    modals: list[str] = field(default_factory=list)
    inline_handlers: list[dict[str, str]] = field(default_factory=list)
    script_srcs: list[str] = field(default_factory=list)
    stylesheet_hrefs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JsSurface:
    """Extracted DOM queries, globals, and event bindings of a JS/TS module."""
    queried_ids: list[str] = field(default_factory=list)
    global_exports: list[str] = field(default_factory=list)
    global_reads: list[str] = field(default_factory=list)
    event_listeners: list[str] = field(default_factory=list)
    es_exports: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PythonSurface:
    """Extracted public API symbols, routes, and mutable globals of a Python module."""
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    all_exports: list[str] = field(default_factory=list)
    routes: list[dict[str, str]] = field(default_factory=list)
    mutable_globals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CssSurface:
    """Extracted CSS custom properties, keyframes, and specificity invariants."""
    custom_properties: list[str] = field(default_factory=list)
    important_count: int = 0
    keyframes: list[str] = field(default_factory=list)
    fullscreen_rules: list[str] = field(default_factory=list)
    import_urls: list[str] = field(default_factory=list)
    important_occurrences: list[dict[str, Any]] = field(default_factory=list)
    section_banners: list[dict[str, Any]] = field(default_factory=list)
    has_crlf: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_HTML_ID_RE = re.compile(r'\bid=["\']([a-zA-Z0-9_\-]+)["\']')
_HTML_SELECT_RE = re.compile(r'<select[^>]*\bid=["\']([a-zA-Z0-9_\-]+)["\']', re.IGNORECASE)
_HTML_BUTTON_RE = re.compile(r'<button[^>]*\bid=["\']([a-zA-Z0-9_\-]+)["\']', re.IGNORECASE)
_HTML_MODAL_RE = re.compile(r'<div[^>]*\bclass=["\'][^"\']*\bmodal\b[^"\']*["\'][^>]*\bid=["\']([a-zA-Z0-9_\-]+)["\']', re.IGNORECASE)
_HTML_HANDLER_RE = re.compile(r'\b(on[a-z]+)\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_HTML_SCRIPT_RE = re.compile(r'<script[^>]*\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)
_HTML_LINK_CSS_RE = re.compile(r'<link[^>]*\brel=["\']stylesheet["\'][^>]*\bhref=["\']([^"\']+)["\']|<link[^>]*\bhref=["\']([^"\']+)["\'][^>]*\brel=["\']stylesheet["\']', re.IGNORECASE)


def scan_html_surface(text: str) -> HtmlSurface:
    """Extract interactive DOM elements, inline handlers, and asset sequences."""
    ids = sorted(set(_HTML_ID_RE.findall(text)))
    selects = sorted(set(_HTML_SELECT_RE.findall(text)))
    buttons = sorted(set(_HTML_BUTTON_RE.findall(text)))
    modals = sorted(set(_HTML_MODAL_RE.findall(text)))

    handlers: list[dict[str, str]] = []
    for ev_name, code in _HTML_HANDLER_RE.findall(text):
        m_fn = re.match(r'([a-zA-Z0-9_$.]+)\s*(?:\(|$)', code.strip())
        fn_name = m_fn.group(1) if m_fn else code.strip()
        handlers.append({"event": ev_name.lower(), "target": fn_name, "raw": code.strip()})

    scripts = _HTML_SCRIPT_RE.findall(text)
    styles: list[str] = []
    for m in _HTML_LINK_CSS_RE.findall(text):
        styles.append(m[0] or m[1])

    return HtmlSurface(
        ids=ids,
        selects=selects,
        buttons=buttons,
        modals=modals,
        inline_handlers=handlers,
        script_srcs=scripts,
        stylesheet_hrefs=styles,
    )


_JS_GET_ELEM_RE = re.compile(r'\b(?:document\.)?getElementById\s*\(\s*["\']([a-zA-Z0-9_\-]+)["\']\s*\)')
_JS_QUERY_SEL_RE = re.compile(r'\bquerySelector(?:All)?\s*\(\s*["\']#([a-zA-Z0-9_\-]+)["\']\s*\)')
_JS_GLOBAL_EXPORT_RE = re.compile(r'\b(?:window|globalThis)\.([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?)\s*=')
_JS_GLOBAL_READ_RE = re.compile(r'\b(?:window|globalThis)\.([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?)')
_JS_EVENT_LISTENER_RE = re.compile(r'\baddEventListener\s*\(\s*["\']([a-zA-Z0-9_\-]+)["\']')
_JS_ES_EXPORT_RE = re.compile(r'^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+([a-zA-Z0-9_]+)', re.MULTILINE)


def scan_js_surface(text: str) -> JsSurface:
    """Extract DOM queries, window exports/reads, and event listener attachments."""
    queried = set(_JS_GET_ELEM_RE.findall(text)) | set(_JS_QUERY_SEL_RE.findall(text))
    exports = set(_JS_GLOBAL_EXPORT_RE.findall(text))
    reads = set(_JS_GLOBAL_READ_RE.findall(text))
    events = set(_JS_EVENT_LISTENER_RE.findall(text))
    es_exp = set(_JS_ES_EXPORT_RE.findall(text))

    return JsSurface(
        queried_ids=sorted(queried),
        global_exports=sorted(exports),
        global_reads=sorted(reads),
        event_listeners=sorted(events),
        es_exports=sorted(es_exp),
    )


_HTTP_METHODS = frozenset({
    "get", "post", "put", "delete", "patch", "head", "options", "websocket", "route", "api_route"
})


def scan_python_surface(text: str, rel_path: str = "") -> PythonSurface:
    """Extract classes, functions, route decorators, and mutable globals using Python AST."""
    classes: list[str] = []
    functions: list[str] = []
    all_exports: list[str] = []
    routes: list[dict[str, Any]] = []
    mutable_globals: list[str] = []

    try:
        tree = ast.parse(textwrap.dedent(text))
    except (SyntaxError, ValueError):
        return PythonSurface()

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            for dec in node.decorator_list:
                parsed_routes = _parse_route_decorator(dec, node=node, rel_path=rel_path)
                if parsed_routes:
                    routes.extend(parsed_routes)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                all_exports.append(elt.value)
                    elif not target.id.startswith("_") and not target.id.isupper():
                        mutable_globals.append(target.id)

    return PythonSurface(
        classes=sorted(classes),
        functions=sorted(functions),
        all_exports=sorted(all_exports),
        routes=routes,
        mutable_globals=sorted(mutable_globals),
    )


def _extract_decorator_methods(dec: ast.Call, attr_name: str) -> list[str]:
    """Resolve HTTP methods from a route decorator call."""
    if attr_name not in {"route", "api_route"}:
        return [attr_name.upper()]

    methods: list[str] = []
    for kw in dec.keywords:
        if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
            for elt in kw.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    methods.append(elt.value.upper())
    return methods or ["GET"]


def _parse_route_decorator(
    dec: ast.expr,
    node: ast.FunctionDef | ast.AsyncFunctionDef | None = None,
    rel_path: str = "",
) -> list[dict[str, Any]]:
    """Detect FastAPI / Flask route decorators like @router.get('/path') with line locations."""
    if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
        return []

    attr_name = dec.func.attr.lower()
    if attr_name not in _HTTP_METHODS or not dec.args:
        return []

    first_arg = dec.args[0]
    if not (isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str)):
        return []

    path_str = first_arg.value
    line_no = getattr(dec, "lineno", None)
    end_line_no = getattr(node, "end_lineno", line_no) if node else line_no
    handler_name = node.name if node else ""
    methods = _extract_decorator_methods(dec, attr_name)

    results: list[dict[str, Any]] = []
    for m in methods:
        info: dict[str, Any] = {"method": m, "path": path_str}
        if line_no is not None:
            info["line"] = line_no
        if end_line_no is not None:
            info["end_line"] = end_line_no
        if handler_name:
            info["handler"] = handler_name
        if rel_path:
            info["file"] = rel_path
        results.append(info)

    return results


_CSS_VAR_RE = re.compile(r'(--[a-zA-Z0-9_\-]+)\s*:')
_CSS_IMPORTANT_RE = re.compile(r'!important\b', re.IGNORECASE)
_CSS_KEYFRAME_RE = re.compile(r'@keyframes\s+([a-zA-Z0-9_\-]+)', re.IGNORECASE)
_CSS_FULLSCREEN_RE = re.compile(r'([^{]*:fullscreen[^{]*)', re.IGNORECASE)
_CSS_IMPORT_RE = re.compile(r'@import\s+(?:url\s*\(\s*["\']?([^"\')]+)["\']?\s*\)|["\']([^"\']+)["\'])')


_CSS_BANNER_RE = re.compile(
    r'^\s*/\*+\s*(?:[=\-_*#~]{3,}\s*)?([A-Za-z0-9][A-Za-z0-9\s.,&/\(\)\'\"\-]{2,60}?)(?:\s*[=\-_*#~]{3,})?\*+/\s*$'
)


def scan_css_surface(text: str) -> CssSurface:
    """Extract custom properties, keyframes, fullscreen rules, and count !important."""
    vars_found = sorted(set(_CSS_VAR_RE.findall(text)))
    keyframes = sorted(set(_CSS_KEYFRAME_RE.findall(text)))
    fullscreen = [m.strip() for m in _CSS_FULLSCREEN_RE.findall(text)]
    imports: list[str] = []
    for m in _CSS_IMPORT_RE.findall(text):
        imports.append(m[0] or m[1])

    has_crlf = "\r\n" in text
    lines = text.splitlines()

    important_occurrences: list[dict[str, Any]] = []
    section_banners: list[dict[str, Any]] = []

    for idx, line in enumerate(lines, start=1):
        if _CSS_IMPORTANT_RE.search(line):
            important_occurrences.append({"line": idx, "content": line.strip()})
        m_banner = _CSS_BANNER_RE.match(line)
        if m_banner:
            title = m_banner.group(1).strip()
            if not title.startswith(("!", "TODO", "FIXME", "eslint", "stylelint", "http")):
                section_banners.append({"line": idx, "title": title})

    important_cnt = len(_CSS_IMPORTANT_RE.findall(text))

    return CssSurface(
        custom_properties=vars_found,
        important_count=important_cnt,
        keyframes=keyframes,
        fullscreen_rules=fullscreen,
        import_urls=imports,
        important_occurrences=important_occurrences,
        section_banners=section_banners,
        has_crlf=has_crlf,
    )
