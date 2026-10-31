#!/usr/bin/env python3
"""Cross-platform line-ending normalizer, robust file patcher, and HTML script injector.

Solves Windows CRLF line-ending mismatches where tools like edit_file fail due to
\\r\\n vs \\n differences. Provides deterministic search/replace and HTML script injection
without requiring brittle inline PowerShell or ad-hoc Python scripts.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Common text file extensions safe for line-ending normalization
TEXT_EXTENSIONS = frozenset({
    ".py", ".js", ".mjs", ".ts", ".html", ".htm", ".css", ".scss",
    ".json", ".md", ".rst", ".txt", ".yaml", ".yml", ".toml", ".ini",
    ".sh", ".bash", ".bat", ".ps1", ".cmd", ".xml", ".svg", ".dart",
    ".go", ".rs", ".cs",
})


def detect_file_eol(path: Path) -> str:
    """Detect whether a file uses CRLF (\\r\\n) or LF (\\n)."""
    try:
        raw = path.read_bytes()
        return "\r\n" if b"\r\n" in raw else "\n"
    except Exception:
        return "\n"


def normalize_file_eol(path: Path, target_eol: str = "\n") -> tuple[bool, str]:
    """Convert line endings in a single text file to target_eol (\\n or \\r\\n)."""
    try:
        raw = path.read_bytes()
        # Binary check (contains null bytes)
        if b"\x00" in raw[:8000]:
            return False, f"Skipped binary file: {path.name}"

        text = raw.decode("utf-8", errors="replace")
        current_eol = "\r\n" if "\r\n" in text else "\n"
        if current_eol == target_eol:
            return False, f"Already using {('CRLF' if target_eol == '\r\n' else 'LF')}: {path.name}"

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if target_eol == "\r\n":
            normalized = normalized.replace("\n", "\r\n")

        path.write_bytes(normalized.encode("utf-8"))
        return True, f"Normalized {path.name} to {('CRLF' if target_eol == '\r\n' else 'LF')}"
    except Exception as err:
        return False, f"Error normalizing {path.name}: {err}"


def cmd_normalize_eol(target: Path, to_eol: str = "lf") -> int:
    """Recursively normalize line endings across text files in target."""
    eol_char = "\r\n" if to_eol.lower() == "crlf" else "\n"
    eol_name = "CRLF" if eol_char == "\r\n" else "LF"
    paths_to_check: list[Path] = []

    if target.is_file():
        paths_to_check = [target]
    elif target.is_dir():
        for root, dirs, files in os.walk(target):
            # Prune hidden or build dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", "dist", "build")]
            for f in files:
                p = Path(root) / f
                if p.suffix.lower() in TEXT_EXTENSIONS:
                    paths_to_check.append(p)

    converted, skipped = 0, 0
    for p in paths_to_check:
        ok, msg = normalize_file_eol(p, target_eol=eol_char)
        if ok:
            converted += 1
        else:
            skipped += 1

    print(f"=== EOL Normalization to {eol_name} ===")
    print(f"  Converted: {converted} file(s)")
    print(f"  Unchanged/Skipped: {skipped} file(s)")
    return 0


def patch_file_content(file_path: Path, target: str, replacement: str, count: int = 1) -> tuple[bool, str]:
    """Replace target text with replacement text, ignoring CRLF vs LF differences."""
    if not file_path.is_file():
        return False, f"File not found: {file_path}"

    raw = file_path.read_bytes()
    file_eol = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8", errors="replace")

    # Normalize both content and target to LF for line-ending-agnostic matching
    norm_text = text.replace("\r\n", "\n").replace("\r", "\n")
    norm_target = target.replace("\r\n", "\n").replace("\r", "\n")
    norm_replacement = replacement.replace("\r\n", "\n").replace("\r", "\n")

    if norm_target not in norm_text:
        # Fallback: line-trimmed match
        target_lines = [l.strip() for l in norm_target.splitlines() if l.strip()]
        if not target_lines:
            return False, f"Target text is empty."
        return False, f"Target content not found in {file_path.name} (checked both LF and CRLF forms)."

    # Perform replacement in normalized space
    if count > 0:
        patched = norm_text.replace(norm_target, norm_replacement, count)
    else:
        patched = norm_text.replace(norm_target, norm_replacement)

    # Restore the file's original line endings
    if file_eol == "\r\n":
        patched = patched.replace("\n", "\r\n")

    file_path.write_bytes(patched.encode("utf-8"))
    return True, f"Successfully patched {file_path.name} (preserved {('CRLF' if file_eol == '\r\n' else 'LF')})."


def _filter_new_scripts(text: str, script_srcs: list[str]) -> list[str]:
    """Return only those scripts whose filenames are not already referenced in text."""
    scripts_to_add: list[str] = []
    for s in script_srcs:
        s_clean = s.strip()
        if not s_clean:
            continue
        pattern = re.compile(rf'src=["\'][^"\']*{re.escape(Path(s_clean).name)}["\']', re.IGNORECASE)
        if not pattern.search(text):
            scripts_to_add.append(s_clean)
    return scripts_to_add


def _find_html_insertion_point(lines: list[str], before_script: str) -> tuple[int, str]:
    """Find the line index and indentation where new <script> tags should be inserted."""
    if before_script:
        b_name = Path(before_script).name
        for i, line in enumerate(lines):
            if re.search(rf'src=["\'][^"\']*{re.escape(b_name)}["\']', line, re.IGNORECASE):
                match = re.match(r"^(\s*)", line)
                return i, match.group(1) if match else "  "

    # Fallback: search backwards for </body> or </script>
    for i in range(len(lines) - 1, -1, -1):
        if "</body>" in lines[i].lower() or "</script>" in lines[i].lower():
            match = re.match(r"^(\s*)", lines[i])
            return i, match.group(1) if match else "  "

    return len(lines), "  "


def inject_html_scripts(html_path: Path, script_srcs: list[str], before_script: str = "") -> tuple[bool, str]:
    """Inject <script src="..."> tags into an HTML file with correct indentation and EOL."""
    if not html_path.is_file():
        return False, f"HTML file not found: {html_path}"

    raw = html_path.read_bytes()
    file_eol = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8", errors="replace")

    scripts_to_add = _filter_new_scripts(text, script_srcs)
    if not scripts_to_add:
        return True, f"All requested scripts are already present in {html_path.name}."

    lines = text.splitlines()
    insert_idx, indent = _find_html_insertion_point(lines, before_script)
    new_tags = [f'{indent}<script src="{s}"></script>' for s in scripts_to_add]
    lines[insert_idx:insert_idx] = new_tags

    updated_text = file_eol.join(lines) + (file_eol if raw.endswith(b"\n") or raw.endswith(b"\r") else "")
    html_path.write_bytes(updated_text.encode("utf-8"))
    return True, f"Injected {len(scripts_to_add)} script tag(s) into {html_path.name} (before '{before_script or 'end'}')."
