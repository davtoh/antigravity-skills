#!/usr/bin/env python3
"""
Frontier Architect - Cross-Platform, Project-Agnostic CDP Browser Inspector.
Zero-dependency inspection engine supporting Windows, macOS, Linux, and WSL.

Connection Cascade:
1. Attaches to the user's LIVE running Chrome/Chromium/Edge instance via `DevToolsActivePort`
   (enabled at `chrome://inspect/#remote-debugging` or `edge://inspect/#remote-debugging`).
2. Or connects to an existing remote debugging port.
3. Or launches an isolated, auto-cleaned temporary headless Chrome instance (`--headless`).

Generic Capabilities:
  --list-tabs                  List open tabs in live browser
  --audit-layout               Generic DOM/viewport overflow scan + <video>, <img>, <canvas> states
  --selectors "#app,.card"     Inspect specific CSS selectors (bounding boxes, styles, media state)
  --click "#submit-btn"        Click an element before auditing/evaluating
  --eval "document.title"      Evaluate arbitrary JS expression and print JSON result
  --screenshot out.jpg         Capture JPEG screenshot of the viewport
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Local modular zero-dependency transport
try:
    from cdp_transport import CDPSession, connect_ws
except ImportError:
    from scripts.cdp_transport import CDPSession, connect_ws

# Ensure UTF-8 output across Windows, macOS, and Linux terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def find_chrome_executable() -> str:
    """Locate Chrome, Chromium, or Edge binary across Windows, macOS, Linux, and WSL."""
    env_bin = os.environ.get("CHROME_BIN") or os.environ.get("CHROME_PATH")
    if env_bin and os.path.exists(env_bin):
        return env_bin

    system = platform.system().lower()
    candidates = []
    if system == "windows":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        ]
    elif system == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:  # Linux / WSL (install a Linux Chromium inside WSL for headless runs)
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
            found = shutil.which(name)
            if found:
                return found

    for c in candidates:
        if os.path.exists(c):
            return c

    return shutil.which("chrome") or shutil.which("google-chrome") or "google-chrome"


def find_devtools_active_port() -> tuple[int, str] | None:
    """Locate browser DevToolsActivePort file across Windows, macOS, Linux, and WSL."""
    system = platform.system().lower()
    home = Path.home()
    candidates: list[Path] = []

    if system == "windows":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        candidates = [
            local_app_data / "Google" / "Chrome" / "User Data" / "DevToolsActivePort",
            local_app_data / "Microsoft" / "Edge" / "User Data" / "DevToolsActivePort",
            local_app_data / "Chromium" / "User Data" / "DevToolsActivePort",
        ]
    elif system == "darwin":
        app_support = home / "Library" / "Application Support"
        candidates = [
            app_support / "Google" / "Chrome" / "DevToolsActivePort",
            app_support / "Microsoft Edge" / "DevToolsActivePort",
            app_support / "Chromium" / "DevToolsActivePort",
        ]
    else:  # Linux / WSL
        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
        candidates = [
            config_dir / "google-chrome" / "DevToolsActivePort",
            config_dir / "chromium" / "DevToolsActivePort",
            home / "snap" / "chromium" / "common" / "chromium" / "DevToolsActivePort",
        ]
        # WSL host probe: a Windows-side live Chrome is only reachable from WSL2 when
        # networking is mirrored; otherwise the live attempt fails and headless is used.
        if Path("/mnt/c/Users").exists():
            for p in Path("/mnt/c/Users").glob("*/AppData/Local/Google/Chrome/User Data/DevToolsActivePort"):
                candidates.append(p)

    for path in candidates:
        if path.exists():
            try:
                lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                if len(lines) >= 2:
                    return int(lines[0]), lines[1]
            except Exception:
                pass
    return None


def build_generic_audit_js(custom_selectors: list[str]) -> str:
    js_path = Path(__file__).parent / "audit_layout.js"
    base_js = js_path.read_text(encoding="utf-8")
    return f"window.__FRONTIER_SELECTORS__ = {json.dumps(custom_selectors)};\n{base_js}"


async def evaluate(cdp: CDPSession, session_id: str | None, expression: str):
    """Evaluate JS and surface page-side exceptions instead of silently printing null."""
    res = await cdp.send(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        session_id=session_id,
    )
    if "exceptionDetails" in res:
        details = res["exceptionDetails"]
        text = details.get("exception", {}).get("description") or details.get("text", "Unknown JS exception")
        return {"jsException": text.splitlines()[0] if text else "Unknown JS exception"}
    return res.get("result", {}).get("value", res.get("result"))


async def run_against_target(cdp: CDPSession, session_id: str | None, args) -> int:
    await cdp.send("Page.enable", session_id=session_id)
    await cdp.send("Runtime.enable", session_id=session_id)

    if args.navigate and args.target_url:
        await cdp.send("Page.navigate", {"url": args.target_url}, session_id=session_id)
    if args.wait > 0:
        await asyncio.sleep(args.wait)
    exit_code = 0

    if args.click:
        click_js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(args.click)});
            if (!el) return {{ clicked: false, reason: 'Selector not found' }};
            el.click();
            return {{ clicked: true, text: el.textContent?.trim() }};
        }})()
        """
        print(json.dumps({"click": await evaluate(cdp, session_id, click_js)}, indent=2, ensure_ascii=False))
        await asyncio.sleep(0.5)

    custom_sels = [s.strip() for s in args.selectors.split(",") if s.strip()] if args.selectors else []
    if args.audit_layout or custom_sels:
        result = await evaluate(cdp, session_id, build_generic_audit_js(custom_sels))
        print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.eval:
        eval_result = await evaluate(cdp, session_id, args.eval)
        print(json.dumps(eval_result, indent=2, ensure_ascii=False))
        if isinstance(eval_result, dict) and "jsException" in eval_result:
            exit_code = 3  # Non-zero so agents/CI can't mistake a thrown error for a pass

    if args.screenshot:
        shot = await cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 85}, session_id=session_id)
        data = shot.get("data")
        if data:
            out_path = Path(args.screenshot)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(base64.b64decode(data))
            print(f"[CDP] Saved screenshot to {out_path.resolve()}")

    return exit_code


async def pick_page_target(cdp: CDPSession, target_url: str) -> str:
    """Return a targetId, never silently auditing an unrelated tab: use the tab matching
    target_url, else open a new tab at target_url, else (no URL) use the first non-internal tab.
    """
    targets_res = await cdp.send("Target.getTargets", timeout=15.0)
    pages = [t for t in targets_res.get("targetInfos", []) if t.get("type") == "page"]
    internal = ("chrome://", "edge://", "devtools://", "about:")

    if target_url:
        wanted = target_url.rstrip("/")
        match = next((p for p in pages if wanted in p.get("url", "")), None)
        if match:
            print(f"[CDP] Attached to tab: {match.get('title')} ({match.get('url')})", file=sys.stderr)
            return match["targetId"]
        print(f"[CDP] No open tab matches {target_url}; opening a new tab.", file=sys.stderr)
        return (await cdp.send("Target.createTarget", {"url": target_url}))["targetId"]

    candidates = [p for p in pages if not p.get("url", "").startswith(internal)]
    if not candidates:
        raise RuntimeError("No inspectable tab open and no --url / APP_URL provided.")
    chosen = candidates[0]
    print(f"[CDP] No --url given; using first tab: {chosen.get('title')} ({chosen.get('url')})", file=sys.stderr)
    return chosen["targetId"]


async def attach_and_run(browser_ws_url: str, args, viewport: tuple[int, int] | None = None) -> int:
    """Connect to a browser-level endpoint, select a page, attach, and run the audit."""
    async with await connect_ws(browser_ws_url, timeout=10.0) as ws:
        cdp = CDPSession(ws)
        if args.list_tabs:
            targets = await cdp.send("Target.getTargets", timeout=15.0)
            pages = [t for t in targets.get("targetInfos", []) if t.get("type") == "page"]
            print(json.dumps(pages, indent=2, ensure_ascii=False))
            return 0
        target_id = await pick_page_target(cdp, args.target_url)
        session_id = (await cdp.send("Target.attachToTarget", {"targetId": target_id, "flatten": True}))["sessionId"]
        if viewport:
            width, height = viewport
            await cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                session_id=session_id,
            )
        return await run_against_target(cdp, session_id, args)


async def read_port_file(profile_dir: Path, timeout_s: float = 10.0) -> tuple[int, str] | None:
    """Wait for Chrome to write DevToolsActivePort into an isolated profile dir."""
    port_file = profile_dir / "DevToolsActivePort"
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        if port_file.exists():
            lines = [ln.strip() for ln in port_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if len(lines) >= 2:
                return int(lines[0]), lines[1]
        await asyncio.sleep(0.2)
    return None


async def run_live(args) -> int | None:
    """Try the user's live browser. Returns None to signal 'fall back to headless'."""
    active_port = find_devtools_active_port()
    if not active_port:
        return None
    port, ws_path = active_port
    browser_ws_url = f"ws://127.0.0.1:{port}{ws_path}"
    try:
        print(f"[CDP] Connecting to live browser ({browser_ws_url})...", file=sys.stderr)
        print("[CDP] If the browser shows an 'Allow remote debugging?' prompt, click 'Allow'.", file=sys.stderr)
        return await attach_and_run(browser_ws_url, args)
    except Exception as e:
        reason = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        print(
            f"[CDP] Live connection failed ({reason}). Likely causes: the 'Allow remote debugging?' prompt "
            "was not accepted, or DevToolsActivePort is stale from an earlier session.",
            file=sys.stderr,
        )
        return None if args.fallback_headless else 2


async def run_headless(args) -> int:
    """Launch an isolated, auto-cleaned headless browser on an OS-assigned free port."""
    if not args.target_url and not args.list_tabs:
        print("[CDP] Error: headless mode needs a page to inspect. Pass --url or set APP_URL.", file=sys.stderr)
        return 2
    chrome_exe = find_chrome_executable()
    if not (os.path.exists(chrome_exe) or shutil.which(chrome_exe)):
        print("[CDP] Error: no Chrome/Chromium/Edge found. Set CHROME_BIN to the browser executable.", file=sys.stderr)
        return 1
    width, height = args.viewport
    with tempfile.TemporaryDirectory(prefix="agy_cdp_") as tmp_profile:
        cmd = [
            chrome_exe, "--headless=new",
            # Port 0 = OS picks a free port (avoids clashing with Node's 9229 or a user's 9222).
            f"--remote-debugging-port={args.port}",
            f"--user-data-dir={tmp_profile}", f"--window-size={width},{height}",
            "--autoplay-policy=no-user-gesture-required", "--disable-gpu", "--no-sandbox",
            "--no-first-run", "--no-default-browser-check", "about:blank",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            active = await read_port_file(Path(tmp_profile))
            if not active:
                print("[CDP] Error: headless browser did not expose a debugging endpoint.", file=sys.stderr)
                return 1
            port, ws_path = active
            return await attach_and_run(f"ws://127.0.0.1:{port}{ws_path}", args, viewport=(width, height))
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


async def main_async(args) -> int:
    if not args.headless:
        live_result = await run_live(args)
        if live_result is not None:
            return live_result
    return await run_headless(args)


def parse_viewport(value: str) -> tuple[int, int]:
    try:
        width, height = (int(x) for x in value.lower().split("x"))
        return width, height
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--window-size must look like 1440x900, got '{value}'") from exc


def main():
    parser = argparse.ArgumentParser(description="Frontier Architect Cross-Platform CDP Browser Inspector")
    parser.add_argument("--url", default=None, help="Target URL to match or open (defaults to $APP_URL if set)")
    parser.add_argument("--list-tabs", action="store_true", help="List open tabs in live browser")
    parser.add_argument("--audit-layout", action="store_true", help="Run generic DOM/viewport overflow and media audit")
    parser.add_argument("--selectors", default=None, help="Comma-separated CSS selectors (e.g. '#app,.player,video')")
    parser.add_argument("--eval", default=None, help="JavaScript expression to evaluate in target page")
    parser.add_argument("--click", default=None, help="CSS selector to click before auditing/evaluating")
    parser.add_argument("--screenshot", default=None, help="Path to save JPEG screenshot")
    parser.add_argument("--navigate", action="store_true", help="Force (re)navigation to target URL, e.g. a hard reload after a fix")
    parser.add_argument("--wait", type=float, default=1.5, help="Seconds to wait before inspection")
    parser.add_argument("--headless", action="store_true", help="Use isolated auto-cleaned headless browser")
    parser.add_argument("--no-fallback-headless", dest="fallback_headless", action="store_false", help="Fail if live browser unreachable")
    parser.set_defaults(fallback_headless=True)
    parser.add_argument("--window-size", dest="viewport", type=parse_viewport, default=(1440, 900), help="Headless viewport (default: 1440x900)")
    parser.add_argument("--port", type=int, default=0, help="Headless debugging port (default: 0 = OS-assigned free port)")
    args = parser.parse_args()
    args.target_url = args.url or os.getenv("APP_URL", "")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
