#!/usr/bin/env python3
"""Extended cross-contract verification & CLI formatting helpers for surface_scanners."""

import ast
import json
import re
from pathlib import Path
from typing import Any

_JS_FETCH_START_RE = re.compile(r"""\bfetch\s*\(""")
_JS_METHOD_OPT_RE = re.compile(r"""\bmethod\s*:\s*['"]([a-zA-Z]+)['"]""")
_JS_TPL_EXPR_RE = re.compile(r"\$\{[^}]+\}")
_JS_NON_FETCH_RE = re.compile(
    r"""(?:(?:\.src\s*=\s*|new\s+WebSocket\s*\(\s*|window\.open\s*\(\s*)(?:`(/[^`\s?]+)|(['"])(/[^'"\s?]+)\2))"""
)
_HTML_MEDIA_SRC_RE = re.compile(
    r"""<(?:img|video|source)\b[^>]*\b(?<!data-)src\s*=\s*['"](/[^'"\s?]+)['"]""",
    re.IGNORECASE,
)
_HTML_BUTTON_TAG_RE = re.compile(
    r"""<button\b([^>]*)>([\s\S]*?)</button>""",
    re.IGNORECASE,
)
_ATTR_ID_RE = re.compile(r"""\bid\s*=\s*['"]([a-zA-Z0-9_\-]+)['"]""", re.IGNORECASE)
_ATTR_ON_RE = re.compile(r"""\bon[a-z]+\s*=\s*['"]""", re.IGNORECASE)
_JS_WIN_OBJ_RE = re.compile(r"""\b(?:window|globalThis|self)\.([A-Z][a-zA-Z0-9_]*)\s*=\s*\{""")
_JS_WIN_CALL_RE = re.compile(r"""\bwindow\.([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*\(""")
_BUILTIN_HANDLER_ROOTS = frozenset({
    "this", "window", "document", "history", "location", "console",
    "alert", "confirm", "prompt", "navigator", "event",
})


def _norm_path(raw: str) -> str:
    norm = _JS_TPL_EXPR_RE.sub("{param}", raw).split("?", 1)[0].rstrip("/")
    return norm or "/"


def _split_call_args(expr: str) -> tuple[str, str]:
    """Split top-level first and second arguments of a JS fetch(...) call."""
    depth, in_quote, first_end = 0, "", -1
    for i, ch in enumerate(expr):
        if in_quote:
            if ch == in_quote and (i == 0 or expr[i - 1] != "\\"):
                in_quote = ""
        elif ch in ("'", '"', "`"):
            in_quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return (expr[:first_end].strip(), expr[first_end + 1:i].strip()) if first_end != -1 else (expr[:i].strip(), "")
            depth -= 1
        elif ch == "," and depth == 0 and first_end == -1:
            first_end = i
    return expr.strip(), ""


def _parse_fetch_url_arg(url_arg: str) -> str | None:
    """Normalize first arg of fetch() if it is a relative /path literal, template, or concat."""
    if url_arg.startswith("`/") and url_arg.endswith("`"):
        return _norm_path(url_arg[1:-1])
    m = re.match(r"""^(['"])(/[^'"\s]+)\1(?:\s*\+\s*(.+))?$""", url_arg, re.DOTALL)
    if not m:
        return None
    base, tail = m.group(2), m.group(3)
    if not tail:
        return _norm_path(base)
    parts = [base]
    for seg in tail.split("+"):
        lit = re.match(r"""^\s*(['"])([^'"]*)\1\s*$""", seg)
        parts.append(lit.group(2) if lit else ("{param}" if parts[-1].endswith("/") else "/{param}"))
    return re.sub(r"/+", "/", "".join(parts)).split("?", 1)[0].rstrip("/") or "/"


def extract_js_fetch_calls(cleaned_js: str) -> list[dict[str, str]]:
    """Extract normalized {path, method} dicts from JS fetch() calls."""
    calls: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in _JS_FETCH_START_RE.finditer(cleaned_js):
        url_arg, opts = _split_call_args(cleaned_js[m.end():m.end() + 500])
        path = _parse_fetch_url_arg(url_arg)
        if not path:
            continue
        method = "ANY"
        if opts:
            mm = _JS_METHOD_OPT_RE.search(opts)
            method = mm.group(1).upper() if mm else ("GET" if opts.startswith("{") else "ANY")
        if (method, path) not in seen:
            seen.add((method, path))
            calls.append({"method": method, "path": path})
    return calls


def extract_non_fetch_urls(cleaned_js: str, html_text: str = "") -> list[dict[str, str]]:
    """Extract relative /path URLs from img.src, video.src, WebSocket, window.open, and HTML media."""
    urls: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in _JS_NON_FETCH_RE.finditer(cleaned_js):
        raw = m.group(1) or m.group(3)
        if not raw or raw.startswith("/static/"):
            continue
        kind = "WEBSOCKET" if "WebSocket" in m.group(0) else "GET"
        norm = _norm_path(raw)
        if (kind, norm) not in seen:
            seen.add((kind, norm))
            urls.append({"method": kind, "path": norm})
    for raw in _HTML_MEDIA_SRC_RE.findall(html_text):
        if raw.startswith("/static/"):
            continue
        norm = _norm_path(raw)
        if ("GET", norm) not in seen:
            seen.add(("GET", norm))
            urls.append({"method": "GET", "path": norm})
    return urls


def extract_html_buttons(html_text: str, rel_file: str) -> list[dict[str, Any]]:
    """Extract <button> elements with id, inline handler flag, normalized label, and file."""
    buttons: list[dict[str, Any]] = []
    for attrs, body in _HTML_BUTTON_TAG_RE.findall(html_text):
        id_m = _ATTR_ID_RE.search(attrs)
        label = re.sub(r"<[^>]+>", " ", body)
        label = re.sub(r"\s+", " ", label).strip()
        buttons.append({
            "id": id_m.group(1) if id_m else "",
            "has_inline": bool(_ATTR_ON_RE.search(attrs)),
            "label": label,
            "file": rel_file,
        })
    return buttons


def check_inline_handlers(
    html_items: list[dict[str, str]],
    js_exports: set[str],
    js_es_exports: set[str],
) -> list[dict[str, str]]:
    """Flag inline HTML on* handler targets missing from JS global/ES exports."""
    known = js_exports | js_es_exports
    missing: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in html_items:
        target = item.get("target", "")
        if not target:
            continue
        clean = target[7:] if target.startswith("window.") else target
        root = clean.split(".")[0]
        if root in _BUILTIN_HANDLER_ROOTS:
            continue
        if clean not in known and root not in known:
            key = (target, item.get("file", ""))
            if key not in seen:
                seen.add(key)
                missing.append({"target": target, "file": item.get("file", "")})
    return missing


def check_dead_buttons_and_dupes(
    buttons: list[dict[str, Any]],
    js_queried_ids: set[str],
    js_dyn_ids: set[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return (dead_buttons, duplicate_button_labels) across HTML templates."""
    dead: list[dict[str, str]] = []
    dupes: list[dict[str, str]] = []
    labels_by_file: dict[tuple[str, str], int] = {}
    for btn in buttons:
        bid = btn["id"]
        if bid and not btn["has_inline"] and bid not in js_queried_ids and bid not in js_dyn_ids:
            dead.append({"id": bid, "file": btn["file"]})
        lbl = btn["label"]
        if lbl and len(lbl) > 1:
            k = (btn["file"], lbl.lower())
            labels_by_file[k] = labels_by_file.get(k, 0) + 1
            if labels_by_file[k] == 2:
                dupes.append({"label": lbl, "file": btn["file"]})
    return dead, dupes


def extract_window_object_members(cleaned_js: str) -> dict[str, set[str]]:
    """Extract method/property names defined inside `window.Obj = { ... }` literals."""
    members: dict[str, set[str]] = {}
    for m in _JS_WIN_OBJ_RE.finditer(cleaned_js):
        obj_name = m.group(1)
        start = m.end()
        depth, i = 1, start
        while i < len(cleaned_js) and depth > 0:
            if cleaned_js[i] == "{":
                depth += 1
            elif cleaned_js[i] == "}":
                depth -= 1
            i += 1
        body = cleaned_js[start:max(start, i - 1)]
        keys = set(re.findall(r"(?:^|[,{\n])\s*(?:async\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?::|\()", body))
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


def _extract_static_route_keys(py_text: str, scan_py_fn: Any, prefix: str) -> dict[str, set[str]]:
    """Collect static dict return keys per route path from Python AST."""
    out: dict[str, set[str]] = {}
    try:
        tree = ast.parse(py_text)
    except SyntaxError:
        return out
    surf = scan_py_fn(py_text)
    by_handler = {r.get("handler"): (prefix + r["path"] if prefix and not r["path"].startswith(prefix) else r["path"]) for r in surf.routes if r.get("handler")}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in by_handler:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                    keys = {k.value for k in sub.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                    if keys:
                        out.setdefault(by_handler[node.name], set()).update(keys)
    return out


def check_response_key_contracts(
    py_items: list[tuple[str, str]],
    js_texts: list[tuple[str, str]],
    scan_py_fn: Any,
    extract_prefix_fn: Any,
) -> list[dict[str, str]]:
    """Flag JS response property reads that are absent from static Python dict route returns."""
    route_keys: dict[str, set[str]] = {}
    for _, py_text in py_items:
        route_keys.update(_extract_static_route_keys(py_text, scan_py_fn, extract_prefix_fn(py_text)))
    if not route_keys:
        return []
    mismatches: list[dict[str, str]] = []
    pat = re.compile(r"""fetch\s*\(\s*['"](/[^'"\s?]+)['"][\s\S]{0,160}?\b(?:data|res|json|body)\.([a-zA-Z_][a-zA-Z0-9_]*)""")
    for rel, js_text in js_texts:
        for path, key in pat.findall(js_text):
            norm = path.rstrip("/") or "/"
            if norm in route_keys and key not in route_keys[norm]:
                mismatches.append({"path": norm, "key": key, "file": rel})
    return mismatches


def print_verification_report(verification: dict[str, Any]) -> None:
    """Print human-readable cross-contract verification summary."""
    s = verification["summary"]
    print(f"\n--- Contract Verification (Mismatches: {s['total_mismatches']}) ---")
    print(
        f"  Unmatched fetch/URLs: {s['unmatched_fetches']} | Dead window.*: {s['dead_window_reads']} "
        f"| Missing IDs: {s['missing_html_ids']} | Dead buttons: {s.get('dead_buttons', 0)} "
        f"| Dupe labels: {s.get('duplicate_button_labels', 0)}"
    )
    sections = (
        ("unmatched_fetches", "UNMATCHED_FETCH", lambda x: f"{x.get('method', 'GET')} {x['path']} ({x['file']})"),
        ("dead_window_reads", "DEAD_WINDOW_READ", lambda x: f"window.{x['symbol']} ({x['file']})"),
        ("missing_html_ids", "MISSING_HTML_ID", lambda x: f"#{x['id']} ({x['file']})"),
        ("missing_inline_handlers", "MISSING_HANDLER", lambda x: f"{x['target']} ({x['file']})"),
        ("dead_buttons", "DEAD_BUTTON", lambda x: f"#{x['id']} ({x['file']})"),
        ("duplicate_button_labels", "DUPE_BUTTON_LABEL", lambda x: f"'{x['label']}' ({x['file']})"),
        ("response_key_mismatches", "RESPONSE_KEY_MISMATCH", lambda x: f"{x['path']} missing .{x['key']} ({x['file']})"),
    )
    for key, tag, fmt in sections:
        for item in verification.get(key, [])[:10]:
            print(f"  [{tag}] {fmt(item)}")


def _print_surface_details(args: Any, ids: set[str], globs: set[str], routes: list[dict[str, Any]]) -> None:
    if getattr(args, "show_ids", False) and ids:
        print("\n--- Element IDs ---\n" + "\n".join(f"  #{i}" for i in sorted(ids)))
    if getattr(args, "show_globals", False) and globs:
        print("\n--- window.* Exports ---\n" + "\n".join(f"  {g}" for g in sorted(globs)))
    if getattr(args, "show_routes", False) and routes:
        print("\n--- Backend Routes ---\n" + "\n".join(f"  {r.get('method', 'GET')} {r.get('path', '')}" for r in routes))


def run_surface_cli(
    args: Any, walk_fn: Any, scan_html_fn: Any, scan_js_fn: Any,
    scan_py_fn: Any, scan_css_fn: Any, verify_fn: Any,
) -> int:
    """Execute surface scan CLI and optional cross-contract verification."""
    target = Path(args.path).resolve() if args.path else Path.cwd()
    is_verify = getattr(args, "verify", False)
    files = walk_fn(target, include_tests=(getattr(args, "include_tests", False) if is_verify else True))
    ids, selects, globs, routes, imp_cnt = set(), set(), set(), [], 0
    for hp in files["html"]:
        s = scan_html_fn(hp.read_text(encoding="utf-8", errors="replace"))
        ids.update(s.ids); selects.update(s.selects)
    for jp in files["js"]:
        globs.update(scan_js_fn(jp.read_text(encoding="utf-8", errors="replace")).global_exports)
    for pp in files["py"]:
        routes.extend(scan_py_fn(pp.read_text(encoding="utf-8", errors="replace")).routes)
    for cp in files["css"]:
        imp_cnt += scan_css_fn(cp.read_text(encoding="utf-8", errors="replace")).important_count
    data: dict[str, Any] = {
        "workspace": str(target), "total_html_files": len(files["html"]),
        "total_ids": len(ids), "ids": sorted(ids), "interactive_selects": sorted(selects),
        "global_window_exports": sorted(globs), "backend_routes": routes, "css_important_count": imp_cnt,
    }
    ver = verify_fn(target, files, scan_html_fn, scan_js_fn, scan_py_fn) if is_verify else None
    if ver is not None:
        data["verification"] = ver
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"=== Surface Inventory ({target}) ===\nHTML Files: {len(files['html'])} | Unique IDs: {len(ids)} | Selects: {len(selects)}")
        print(f"JS Files:   {len(files['js'])} | window.* Globals: {len(globs)}\nPython Files: {len(files['py'])} | API Routes: {len(routes)}\nCSS Files:  {len(files['css'])} | !important Count: {imp_cnt}")
        _print_surface_details(args, ids, globs, routes)
        if ver is not None:
            print_verification_report(ver)
    return 1 if (ver and getattr(args, "strict", False) and ver["summary"]["total_mismatches"] > 0) else 0
