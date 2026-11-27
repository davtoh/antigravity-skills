"""Bundles the DevTools observation HUD (assets/hud_*.js) into one script.

The three asset files are plain ES5 fragments concatenated in a fixed order inside a wrapper that
enforces the gate: unless ``window.__FRONTIER_DEBUG__ === true`` the bundle returns immediately and
touches nothing (no listeners, DOM or timers). Python standard library only.
"""

from pathlib import Path

HUD_FILES = ("hud_core.js", "hud_picker.js", "hud_recorder.js", "hud_drawer.js")
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

_HEAD = (
    "(function (win) {\n'use strict';\n"
    "if (win.__FRONTIER_DEBUG__ !== true || win.__FRONTIER_HUD__) { return; }\n"
    "var H = {};\n"
)
_TAIL = "\n})(window);\n"


def hud_bundle(assets_dir: Path | None = None) -> str:
    """Return the gated HUD script (LF newlines, UTF-8)."""
    base = Path(assets_dir) if assets_dir else ASSETS_DIR
    parts = [(base / name).read_text(encoding="utf-8").replace("\r\n", "\n") for name in HUD_FILES]
    return _HEAD + "\n".join(parts) + _TAIL
