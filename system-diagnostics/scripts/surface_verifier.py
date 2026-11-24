#!/usr/bin/env python3
"""Cross-contract surface verifier for system-diagnostics.

Cross-references:
1. JS fetch() & non-fetch URLs (img.src, video.src, WebSocket, window.open) vs backend routes & HTTP methods
2. JS window.* reader/writer symmetry & window.<Obj>.<method>() calls
3. JS getElementById/querySelector('#id') & inline HTML onclick vs HTML/JS contracts
4. Dead <button id="..."> elements, duplicate button labels, & static JSON response keys
"""

import re
from pathlib import Path
from typing import Any

try:
    from surface_contracts import (
        check_dead_buttons_and_dupes, check_inline_handlers, check_response_key_contracts,
        extract_html_buttons, extract_js_fetch_calls, extract_non_fetch_urls,
    )
    from surface_layout_checks import check_undefined_layout_classes
except ImportError:
    from .surface_contracts import (  # type: ignore[no-redef]
        check_dead_buttons_and_dupes, check_inline_handlers, check_response_key_contracts,
        extract_html_buttons, extract_js_fetch_calls, extract_non_fetch_urls,
    )
    from .surface_layout_checks import check_undefined_layout_classes  # type: ignore[no-redef]

_JS_WIN_OBJ_RE = re.compile(r"""\b(?:window|globalThis|self)\.([A-Z][a-zA-Z0-9_]*)\s*=\s*\{""")
_JS_WIN_CALL_RE = re.compile(r"""\bwindow\.([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*\(""")

_JS_LINE_COMMENT_RE = re.compile(r"(?<!:)//[^\n]*")
_JS_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_JS_DYN_ID_RE = re.compile(r"""(?:\.id\s*=\s*|\bid\s*=\s*["']|\[id=["'])([a-zA-Z0-9_\-]+)""")
_JS_TAB_DELEGATE_RE = re.compile(r"""querySelector(?:All)?\s*\([^)]*\.(?:nav-tab|drawer-tab)\b""")
_JS_FALLBACK_ID_RE = re.compile(
    r"""\b(?:document\.getElementById|el)\s*\(\s*['"]([a-zA-Z0-9_\-]+)['"]\s*\)\s*\|\|\s*(?:document\.getElementById|el)\s*\(\s*['"]([a-zA-Z0-9_\-]+)['"]\s*\)"""
)
_PY_PREFIX_RE = re.compile(r"""APIRouter\s*\((?:[^()]|\([^()]*\))*?\bprefix\s*=\s*['"]([^'"]+)['"]""")
_PY_MOUNT_RE = re.compile(r"""\.mount\s*\(\s*['"]([^'"]+)['"]""")


def _strip_js_comments(text: str) -> str:
    """Remove JS block and line comments while preserving http(s):// URLs."""
    return _JS_LINE_COMMENT_RE.sub("", _JS_BLOCK_COMMENT_RE.sub("", text))


def extract_js_fetch_paths(text: str) -> list[str]:
    """Extract normalized API/relative paths from JS fetch() calls."""
    return sorted({c["path"] for c in extract_js_fetch_calls(_strip_js_comments(text))})


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


def _route_matches(
    fetch_path: str,
    method: str,
    route_specs: list[tuple[str, re.Pattern[str], str]],
    mount_prefixes: list[str],
) -> bool:
    """Return True if fetch_path + method matches any declared route or StaticFiles mount."""
    probe = re.sub(r"\{[^}]+\}", "__PARAM__", fetch_path.rstrip("/") or "/")
    probe_pat = (
        re.compile("^" + "".join(r"[^/]+" if part == "__PARAM__" else re.escape(part) for part in re.split(r"(__PARAM__)", probe)) + "$")
        if "__PARAM__" in probe
        else None
    )
    for r_method, pat, sample_path in route_specs:
        if method == "ANY" or r_method == method:
            if pat.match(probe) or (probe_pat and probe_pat.match(sample_path)):
                return True
    return method in ("GET", "ANY") and any(probe == mp or probe.startswith(mp + "/") for mp in mount_prefixes if mp != "/")


def _rel_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/") if path.is_relative_to(root) else path.name


def _collect_py_contracts(
    target_path: Path, py_files: list[Path], scan_py_fn: Any
) -> tuple[list[tuple[str, re.Pattern[str], str]], list[str], list[tuple[str, str]]]:
    specs: list[tuple[str, re.Pattern[str], str]] = []
    mount_prefixes: list[str] = []
    py_items: list[tuple[str, str]] = []
    for pp in py_files:
        text = pp.read_text(encoding="utf-8", errors="replace")
        rel = _rel_path(pp, target_path)
        py_items.append((rel, text))
        prefix = extract_router_prefix(text)
        mount_prefixes.extend(extract_mount_prefixes(text))
        for r in scan_py_fn(text, rel_path=rel).routes:
            full_path = (prefix + r["path"]) if prefix and not r["path"].startswith(prefix) else r["path"]
            sample_path = re.sub(r"\{[^}]+\}|<[^>]+>", "__PARAM__", full_path.rstrip("/") or "/")
            specs.append((r.get("method", "GET").upper(), _compile_route_regex(full_path), sample_path))
    return specs, mount_prefixes, py_items


def _top_level_obj_text(body: str) -> str:
    """Keep only depth-0 characters of a JS object literal body."""
    out, depth, in_q = [], 0, ""
    for i, ch in enumerate(body):
        if in_q:
            if ch == in_q and (i == 0 or body[i - 1] != "\\"):
                in_q = ""
            out.append(" ")
        elif ch in ("'", '"', "`"):
            in_q = ch
            out.append(" ")
        elif ch in "([{":
            depth += 1
            out.append(" ")
        elif ch in ")]}":
            depth = max(0, depth - 1)
            out.append(" ")
        else:
            out.append(ch if depth == 0 else " ")
    return "".join(out)


def extract_window_object_members(cleaned_js: str) -> dict[str, set[str]]:
    """Extract method/property/shorthand names defined inside `window.Obj = { ... }`."""
    members: dict[str, set[str]] = {}
    for m in _JS_WIN_OBJ_RE.finditer(cleaned_js):
        obj_name, start, depth, i = m.group(1), m.end(), 1, m.end()
        while i < len(cleaned_js) and depth > 0:
            depth += 1 if cleaned_js[i] == "{" else (-1 if cleaned_js[i] == "}" else 0)
            i += 1
        top_text = _top_level_obj_text(cleaned_js[start:max(start, i - 1)])
        keys = set(re.findall(r"(?:^|[,;\n])\s*(?:async\s+|get\s+|set\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?=[:(,\n}]|$)", top_text))
        members.setdefault(obj_name, set()).update(keys)
    return members


def check_window_method_calls(
    js_texts: list[tuple[str, str]],
    js_exports: set[str],
    obj_members: dict[str, set[str]],
) -> list[dict[str, str]]:
    """Flag `window.<Obj>.<method>()` calls where `<Obj>` is defined in JS without `<method>`."""
    missing: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for rel, cleaned in js_texts:
        for obj, meth in _JS_WIN_CALL_RE.findall(cleaned):
            if obj in obj_members:
                full = f"{obj}.{meth}"
                if meth not in obj_members[obj] and full not in js_exports:
                    if (full, rel) not in seen:
                        seen.add((full, rel))
                        missing.append({"symbol": full, "file": rel})
    return missing


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


_BUILTIN_WINDOW_PROPS = frozenset(
    "location document navigator history console localStorage sessionStorage screen performance visualViewport "
    "crypto indexedDB customElements innerWidth innerHeight outerWidth outerHeight scrollX scrollY pageXOffset "
    "pageYOffset addEventListener removeEventListener dispatchEvent setTimeout clearTimeout setInterval "
    "clearInterval requestAnimationFrame cancelAnimationFrame fetch alert confirm prompt open close focus blur "
    "getComputedStyle matchMedia devicePixelRatio onload onbeforeunload onhashchange onresize WebSocket URL Blob "
    "File FormData Headers Request Response Event CustomEvent MutationObserver ResizeObserver IntersectionObserver "
    "AbortController TextDecoder TextEncoder Image Audio Option HTMLElement parent top self frames name closed "
    "opener atob btoa encodeURIComponent decodeURIComponent parseInt parseFloat isNaN isFinite structuredClone "
    "queueMicrotask reportError getSelection print stop scrollTo scrollBy postMessage URLSearchParams Intl Math "
    "JSON Object Array Number String Boolean Date RegExp Promise Map Set".split()
)


def _scan_html_contracts(target_path: Path, html_files: list[Path], scan_html_fn: Any) -> tuple[set[str], list[dict[str, str]], list[dict[str, Any]], list[dict[str, str]]]:
    all_ids: set[str] = set()
    handlers: list[dict[str, str]] = []
    buttons: list[dict[str, Any]] = []
    media_urls: list[dict[str, str]] = []
    for hp in html_files:
        text, rel = hp.read_text(encoding="utf-8", errors="replace"), _rel_path(hp, target_path)
        surf = scan_html_fn(text)
        all_ids.update(surf.ids)
        handlers.extend({**h, "file": rel} for h in surf.inline_handlers)
        buttons.extend(extract_html_buttons(text, rel))
        media_urls.extend({**u, "file": rel} for u in extract_non_fetch_urls("", text))
    return all_ids, handlers, buttons, media_urls


def _collect_js_contracts(
    target_path: Path, js_files: list[Path], scan_js_fn: Any, html_urls: list[dict[str, str]]
) -> dict[str, Any]:
    all_dyn_ids, writes, es_exp, queried = set(), set(), set(), set()
    fallback_pairs: set[tuple[str, str]] = set()
    obj_members: dict[str, set[str]] = {}
    id_refs: list[dict[str, str]] = []
    calls = list(html_urls)
    reads: list[dict[str, str]] = []
    texts: list[tuple[str, str]] = []
    has_tab_delegation = False
    for jp in js_files:
        text, rel = jp.read_text(encoding="utf-8", errors="replace"), _rel_path(jp, target_path)
        cleaned = _strip_js_comments(text)
        texts.append((rel, cleaned))
        if _JS_TAB_DELEGATE_RE.search(cleaned):
            has_tab_delegation = True
        surf = scan_js_fn(text)
        all_dyn_ids.update(_JS_DYN_ID_RE.findall(text))
        fallback_pairs.update(_JS_FALLBACK_ID_RE.findall(cleaned))
        queried.update(surf.queried_ids)
        id_refs.extend({"id": qid, "file": rel} for qid in surf.queried_ids)
        calls.extend({**c, "file": rel} for c in extract_js_fetch_calls(cleaned) + extract_non_fetch_urls(cleaned))
        writes.update(surf.global_exports)
        es_exp.update(surf.es_exports)
        for obj, mems in extract_window_object_members(cleaned).items():
            obj_members.setdefault(obj, set()).update(mems)
        reads.extend({"symbol": r, "file": rel} for r in surf.global_reads if r.split(".")[0] not in _BUILTIN_WINDOW_PROPS and r not in surf.global_exports)
    return {
        "dyn_ids": all_dyn_ids, "fallback_pairs": fallback_pairs, "writes": writes, "es_exports": es_exp, "queried": queried,
        "obj_members": obj_members, "id_refs": id_refs, "calls": calls, "reads": reads,
        "texts": texts, "has_tab_delegation": has_tab_delegation,
    }


_HTML_SCRIPT_SRC_RE = re.compile(r"""<script\b[^>]*\bsrc\s*=\s*['"]([^'"]+)['"]""", re.IGNORECASE)
_JS_WIN_ASSIGN_RE = re.compile(r"""\bwindow\.([a-zA-Z0-9_]+)\s*=""")
_JS_WIN_READ_RE = re.compile(r"""\b(?:const|let|var)\s+[a-zA-Z0-9_]+\s*=\s*window\.([a-zA-Z0-9_]+)\s*[;\n]""")
_JS_QUERY_URL_RE = re.compile(r"""['"`](/[^'"`\s?]+)\?([a-zA-Z0-9_&=]+)""" )
_PY_ROUTE_DEF_RE = re.compile(
    r"""@router\.(?:get|post|put|delete|patch)\(\s*['"]([^'"]+)['"][^)]*\)\s*(?:async\s+)?def\s+[a-zA-Z0-9_]+\s*\(([^)]*)\)""",
    re.DOTALL,
)


def _check_script_wrap_order(
    html_files: list[Path], js_texts: list[tuple[str, str]], target_path: Path
) -> list[dict[str, str]]:
    """Verify JS files wrapping `window.<fn>` load after the JS file that defines it."""
    definers: dict[str, str] = {}
    wrappers: list[tuple[str, str]] = []
    for rel, cleaned in js_texts:
        name = Path(rel).name
        assigned, read_before = set(_JS_WIN_ASSIGN_RE.findall(cleaned)), set(_JS_WIN_READ_RE.findall(cleaned))
        for fn in assigned - read_before:
            definers.setdefault(fn, name)
        wrappers.extend((fn, name) for fn in assigned & read_before)
    warnings: list[dict[str, str]] = []
    for hp in html_files:
        order = [Path(s.split("?", 1)[0]).name for s in _HTML_SCRIPT_SRC_RE.findall(hp.read_text(encoding="utf-8", errors="replace"))]
        pos, hrel = {n: i for i, n in enumerate(order)}, _rel_path(hp, target_path)
        for fn, wrap_js in wrappers:
            def_js = definers.get(fn)
            if def_js and def_js in pos and wrap_js in pos and pos[wrap_js] < pos[def_js]:
                warnings.append({"symbol": fn, "wrapper": wrap_js, "definer": def_js, "file": hrel})
    return warnings


def _check_query_param_parity(py_items: list[tuple[str, str]], js_texts: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Warn when JS query-string params do not match any parameter on the backend route handler."""
    route_params: list[tuple[re.Pattern[str], set[str], bool]] = []
    for _, py_text in py_items:
        prefix = extract_router_prefix(py_text)
        for raw_p, raw_args in _PY_ROUTE_DEF_RE.findall(py_text):
            full = (prefix + raw_p) if prefix and not raw_p.startswith(prefix) else raw_p
            names = {a.strip().split(":")[0].split("=")[0].lstrip("*") for a in raw_args.split(",") if a.strip()}
            route_params.append((_compile_route_regex(full), names, "**" in raw_args))
    warnings: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for rel, cleaned in js_texts:
        for path, qs in _JS_QUERY_URL_RE.findall(cleaned):
            norm = path.rstrip("/") or "/"
            matched = [(n, kw) for pat, n, kw in route_params if pat.match(norm)]
            if not matched or any(kw for _, kw in matched):
                continue
            accepted = set().union(*(n for n, _ in matched))
            for qp in (kv.split("=", 1)[0] for kv in qs.split("&") if kv):
                if qp not in accepted and qp != "t" and (norm, qp, rel) not in seen:
                    seen.add((norm, qp, rel))
                    warnings.append({"path": norm, "param": qp, "file": rel})
    return warnings


def verify_surface_contracts(
    target_path: Path,
    files: dict[str, list[Path]],
    scan_html_fn: Any,
    scan_js_fn: Any,
    scan_py_fn: Any,
) -> dict[str, Any]:
    """Run cross-contract verification across HTML, JS, and Python files."""
    all_html_ids, html_handlers, html_buttons, html_urls = _scan_html_contracts(target_path, files["html"], scan_html_fn)
    route_specs, mount_prefixes, py_items = _collect_py_contracts(target_path, files["py"], scan_py_fn)
    js = _collect_js_contracts(target_path, files["js"], scan_js_fn, html_urls)
    unmatched = [c for c in js["calls"] if not _route_matches(c["path"], c["method"], route_specs, mount_prefixes)]
    dead_reads = _find_dead_window_reads(js["reads"], js["writes"]) + check_window_method_calls(js["texts"], js["writes"], js["obj_members"])
    known_ids = all_html_ids | js["dyn_ids"]
    satisfied_fallbacks = {fb for pri, fb in js["fallback_pairs"] if pri in known_ids}
    missing_ids = [ref for ref in js["id_refs"] if ref["id"] not in (known_ids | satisfied_fallbacks)]
    missing_handlers = check_inline_handlers(html_handlers, js["writes"], js["es_exports"])
    dead_btns, dupe_labels = check_dead_buttons_and_dupes(
        html_buttons, js["queried"], js["dyn_ids"], js_has_tab_delegation=js["has_tab_delegation"]
    )
    resp_mismatches = check_response_key_contracts(py_items, js["texts"], scan_py_fn, extract_router_prefix)
    script_warns = _check_script_wrap_order(files["html"], js["texts"], target_path)
    qp_warns = _check_query_param_parity(py_items, js["texts"])
    undef_layout = check_undefined_layout_classes(files["html"], files.get("css", []), target_path)
    total = len(unmatched) + len(dead_reads) + len(missing_ids) + len(missing_handlers) + len(dead_btns) + len(dupe_labels) + len(resp_mismatches) + len(script_warns) + len(undef_layout)
    return {
        "unmatched_fetches": unmatched, "dead_window_reads": dead_reads, "missing_html_ids": missing_ids,
        "missing_inline_handlers": missing_handlers, "dead_buttons": dead_btns,
        "duplicate_button_labels": dupe_labels, "response_key_mismatches": resp_mismatches,
        "script_order_warnings": script_warns, "query_param_warnings": qp_warns,
        "undefined_layout_classes": undef_layout,
        "summary": {
            "unmatched_fetches": len(unmatched), "dead_window_reads": len(dead_reads),
            "missing_html_ids": len(missing_ids), "missing_inline_handlers": len(missing_handlers),
            "dead_buttons": len(dead_btns), "duplicate_button_labels": len(dupe_labels),
            "response_key_mismatches": len(resp_mismatches), "script_order_warnings": len(script_warns),
            "query_param_warnings": len(qp_warns), "undefined_layout_classes": len(undef_layout),
            "total_mismatches": total,
        },
    }
