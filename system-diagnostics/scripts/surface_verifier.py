#!/usr/bin/env python3
"""Cross-contract surface verifier for system-diagnostics.

Cross-references:
1. JS fetch() paths vs backend FastAPI/Flask route patterns
2. JS window.* reader/writer symmetry
3. JS getElementById/querySelector('#id') vs HTML/template IDs
"""

import re
from pathlib import Path
from typing import Any

_JS_LINE_COMMENT_RE = re.compile(r"(?<!:)//[^\n]*")
_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_JS_FETCH_TPL_RE = re.compile(r"\bfetch\s*\(\s*`(/[^`\s]+)")
_JS_FETCH_STR_RE = re.compile(r"""\bfetch\s*\(\s*(['"])(/[^'"\s]+)\1(?:\s*\+\s*([^\n;]+))?""")
_JS_TPL_EXPR_RE = re.compile(r"\$\{[^}]+\}")
_JS_DYN_ID_RE = re.compile(r"""(?:\.id\s*=\s*|\bid\s*=\s*["'])([a-zA-Z0-9_\-]+)""")
_PY_PREFIX_RE = re.compile(r"""APIRouter\s*\((?:[^()]|\([^()]*\))*?\bprefix\s*=\s*['"]([^'"]+)['"]""")
_PY_MOUNT_RE = re.compile(r"""\.mount\s*\(\s*['"]([^'"]+)['"]""")

_BUILTIN_WINDOW_PROPS = frozenset({
    "location", "document", "navigator", "history", "console", "localStorage",
    "sessionStorage", "screen", "performance", "visualViewport", "crypto",
    "indexedDB", "customElements", "innerWidth", "innerHeight", "outerWidth",
    "outerHeight", "scrollX", "scrollY", "pageXOffset", "pageYOffset",
    "addEventListener", "removeEventListener", "dispatchEvent", "setTimeout",
    "clearTimeout", "setInterval", "clearInterval", "requestAnimationFrame",
    "cancelAnimationFrame", "fetch", "alert", "confirm", "prompt", "open",
    "close", "focus", "blur", "getComputedStyle", "matchMedia", "devicePixelRatio",
    "onload", "onbeforeunload", "onhashchange", "onresize", "WebSocket", "URL",
    "Blob", "File", "FormData", "Headers", "Request", "Response", "Event",
    "CustomEvent", "MutationObserver", "ResizeObserver", "IntersectionObserver",
    "AbortController", "TextDecoder", "TextEncoder", "Image", "Audio", "Option",
    "HTMLElement", "parent", "top", "self", "frames", "name", "closed", "opener",
    "atob", "btoa", "encodeURIComponent", "decodeURIComponent", "parseInt",
    "parseFloat", "isNaN", "isFinite", "structuredClone", "queueMicrotask",
    "reportError", "getSelection", "print", "stop", "scrollTo", "scrollBy",
    "postMessage", "URLSearchParams", "Intl", "Math", "JSON", "Object", "Array",
    "Number", "String", "Boolean", "Date", "RegExp", "Promise", "Map", "Set",
})


def _strip_js_comments(text: str) -> str:
    """Remove JS block and line comments while preserving http(s):// URLs."""
    return _JS_LINE_COMMENT_RE.sub("", _JS_BLOCK_COMMENT_RE.sub("", text))


def _slice_first_arg(expr: str) -> str:
    """Return concatenation expression up to the top-level comma or closing paren."""
    depth, in_quote = 0, ""
    for i, ch in enumerate(expr):
        if in_quote:
            if ch == in_quote and (i == 0 or expr[i - 1] != "\\"):
                in_quote = ""
        elif ch in ("'", '"', "`"):
            in_quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            if depth == 0:
                return expr[:i]
            depth -= 1
        elif ch == "," and depth == 0:
            return expr[:i]
    return expr


def _build_concat_path(base: str, tail: str) -> str:
    """Normalize a JS string-concatenated fetch() path into a parameterized route."""
    parts = [base]
    for seg in _slice_first_arg(tail).split("+"):
        lit = re.match(r"""^\s*(['"])([^'"]*)\1\s*$""", seg)
        if lit:
            parts.append(lit.group(2))
        else:
            if not parts[-1].endswith("/"):
                parts.append("/")
            parts.append("{param}")
    return "".join(parts).replace("//", "/").split("?", 1)[0].rstrip("/") or "/"


def extract_js_fetch_paths(text: str) -> list[str]:
    """Extract normalized API/relative paths from JS fetch() calls."""
    cleaned = _strip_js_comments(text)
    paths: set[str] = set()
    for raw in _JS_FETCH_TPL_RE.findall(cleaned):
        norm = _JS_TPL_EXPR_RE.sub("{param}", raw).split("?", 1)[0].rstrip("/") or "/"
        paths.add(norm)
    for m in _JS_FETCH_STR_RE.finditer(cleaned):
        base, tail = m.group(2), m.group(3)
        if tail is not None:
            paths.add(_build_concat_path(base, tail))
        else:
            paths.add(base.split("?", 1)[0].rstrip("/") or "/")
    return sorted(paths)


def extract_router_prefix(py_text: str) -> str:
    """Extract APIRouter(prefix=...) from a Python router module."""
    m = _PY_PREFIX_RE.search(py_text)
    return m.group(1).rstrip("/") if m else ""


def extract_mount_prefixes(py_text: str) -> list[str]:
    """Extract FastAPI .mount('/prefix', ...) prefixes."""
    return [m.rstrip("/") or "/" for m in _PY_MOUNT_RE.findall(py_text)]


def _compile_route_regex(route_path: str) -> re.Pattern[str]:
    """Convert FastAPI/Flask route pattern like /api/videos/{fn}/reports to regex."""
    norm = route_path.rstrip("/") or "/"
    parts = re.split(r"(\{[^}]+\}|<[^>]+>)", norm)
    regex_parts = [
        r"[^/]+" if ((p.startswith("{") and p.endswith("}")) or (p.startswith("<") and p.endswith(">"))) else re.escape(p)
        for p in parts
    ]
    return re.compile("^" + "".join(regex_parts) + "$")


def _route_matches(fetch_path: str, route_patterns: list[re.Pattern[str]], mount_prefixes: list[str]) -> bool:
    """Return True if fetch_path matches any declared route pattern or StaticFiles mount."""
    probe = re.sub(r"\{[^}]+\}", "__PARAM__", fetch_path.rstrip("/") or "/")
    if any(pat.match(probe) for pat in route_patterns):
        return True
    return any(probe == mp or probe.startswith(mp + "/") for mp in mount_prefixes if mp != "/")


def _rel_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/") if path.is_relative_to(root) else path.name


def _collect_py_contracts(target_path: Path, py_files: list[Path], scan_py_fn: Any) -> tuple[list[re.Pattern[str]], list[str]]:
    routes: list[dict[str, Any]] = []
    mount_prefixes: list[str] = []
    for pp in py_files:
        text = pp.read_text(encoding="utf-8", errors="replace")
        prefix = extract_router_prefix(text)
        mount_prefixes.extend(extract_mount_prefixes(text))
        for r in scan_py_fn(text, rel_path=_rel_path(pp, target_path)).routes:
            full_path = (prefix + r["path"]) if prefix and not r["path"].startswith(prefix) else r["path"]
            routes.append({**r, "path": full_path})
    return [_compile_route_regex(r["path"]) for r in routes], mount_prefixes


def _find_dead_window_reads(js_reads: list[dict[str, str]], js_writes: set[str]) -> list[dict[str, str]]:
    dead: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in js_reads:
        sym = item["symbol"]
        if sym not in js_writes and sym.split(".")[0] not in js_writes:
            key = (sym, item["file"])
            if key not in seen:
                seen.add(key)
                dead.append(item)
    return dead


def verify_surface_contracts(
    target_path: Path,
    files: dict[str, list[Path]],
    scan_html_fn: Any,
    scan_js_fn: Any,
    scan_py_fn: Any,
) -> dict[str, Any]:
    """Run cross-contract verification across HTML, JS, and Python files."""
    all_html_ids = {
        hid for hp in files["html"]
        for hid in scan_html_fn(hp.read_text(encoding="utf-8", errors="replace")).ids
    }
    route_patterns, mount_prefixes = _collect_py_contracts(target_path, files["py"], scan_py_fn)

    all_js_dyn_ids: set[str] = set()
    js_id_refs, js_fetches, js_reads = [], [], []
    js_writes: set[str] = set()
    for jp in files["js"]:
        text, rel = jp.read_text(encoding="utf-8", errors="replace"), _rel_path(jp, target_path)
        surf = scan_js_fn(text)
        all_js_dyn_ids.update(_JS_DYN_ID_RE.findall(text))
        js_id_refs.extend({"id": qid, "file": rel} for qid in surf.queried_ids)
        js_fetches.extend({"path": fpath, "file": rel} for fpath in extract_js_fetch_paths(text))
        js_writes.update(surf.global_exports)
        js_reads.extend(
            {"symbol": rsym, "file": rel} for rsym in surf.global_reads
            if rsym.split(".")[0] not in _BUILTIN_WINDOW_PROPS and rsym not in surf.global_exports
        )

    unmatched = [f for f in js_fetches if not _route_matches(f["path"], route_patterns, mount_prefixes)]
    dead_reads = _find_dead_window_reads(js_reads, js_writes)
    missing_ids = [ref for ref in js_id_refs if ref["id"] not in (all_html_ids | all_js_dyn_ids)]
    return {
        "unmatched_fetches": unmatched, "dead_window_reads": dead_reads, "missing_html_ids": missing_ids,
        "summary": {
            "unmatched_fetches": len(unmatched), "dead_window_reads": len(dead_reads),
            "missing_html_ids": len(missing_ids),
            "total_mismatches": len(unmatched) + len(dead_reads) + len(missing_ids),
        },
    }


def print_verification_report(verification: dict[str, Any]) -> None:
    """Print human-readable cross-contract verification summary."""
    s = verification["summary"]
    print(f"\n--- Contract Verification (Mismatches: {s['total_mismatches']}) ---")
    print(f"  Unmatched JS fetch(): {s['unmatched_fetches']} | Dead window.* reads: {s['dead_window_reads']} | Missing HTML IDs: {s['missing_html_ids']}")
    for f in verification["unmatched_fetches"][:15]:
        print(f"  [UNMATCHED_FETCH] {f['path']} ({f['file']})")
    for w in verification["dead_window_reads"][:15]:
        print(f"  [DEAD_WINDOW_READ] window.{w['symbol']} ({w['file']})")
    for m in verification["missing_html_ids"][:15]:
        print(f"  [MISSING_HTML_ID] #{m['id']} ({m['file']})")
