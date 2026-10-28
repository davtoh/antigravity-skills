#!/usr/bin/env python3
"""
Frontier Architect - Cross-Platform, Project-Agnostic Docker Runtime & Sync Auditor.
Works on Windows, macOS, and Linux for any containerized project.

Capabilities:
1. Snapshot all running containers' CPU, Memory, Network I/O, and PIDs (`docker stats --no-stream`)
2. Inspect active processes inside a specific container (`docker top <container>`)
3. Verify MD5 file synchronization between host files and container files (`--sync-check`)
4. Scan recent container logs for unhandled Tracebacks/Exceptions (`--tail-errors`)

Usage:
  python docker_audit.py
  python docker_audit.py --container <container_name> --workdir /app --sync-check src/app.py static/styles.css
"""

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_cmd(cmd: list[str], timeout: float = 10.0) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return (res.stdout or "") + (res.stderr or "")
    except Exception as e:
        return f"Error: {e}"


def host_md5(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return "MISSING_ON_HOST"
    return hashlib.md5(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Frontier Architect Cross-Platform Docker CPU & Sync Auditor")
    parser.add_argument("--container", default=None, help="Target container name (optional; inspects top processes, sync, and logs)")
    parser.add_argument("--workdir", default="/app", help="Container working directory prefix for --sync-check (default: /app)")
    parser.add_argument("--sync-check", nargs="*", default=[], help="Relative host paths to compare MD5 against <workdir>/<path> in container")
    parser.add_argument("--tail-errors", type=int, default=150, help="Lines of container logs to scan for Tracebacks/Errors")
    args = parser.parse_args()

    print("=== 1. DOCKER STATS (CPU / MEM / NET I/O / PIDS) ===")
    print(run_cmd(["docker", "stats", "--no-stream", "--format", "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.PIDs}}"]).strip())

    if args.container:
        print(f"\n=== 2. CONTAINER PROCESSES ({args.container}) ===")
        print(run_cmd(["docker", "top", args.container]).strip())

    if args.sync_check and args.container:
        workdir = args.workdir.rstrip("/")
        print(f"\n=== 3. HOST vs CONTAINER FILE SYNC ({args.container}:{workdir}) ===")
        container_paths = [f"{workdir}/{p.replace(chr(92), '/')}" for p in args.sync_check]
        out = run_cmd(["docker", "exec", args.container, "md5sum", *container_paths])
        container_hashes = {}
        for line in out.splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                container_hashes[parts[1].strip()] = parts[0].strip().lower()

        for rel in args.sync_check:
            c_path = f"{workdir}/{rel.replace(chr(92), '/')}"
            h_hash = host_md5(rel).lower()
            c_hash = container_hashes.get(c_path, "MISSING_IN_CONTAINER")
            status = "IN_SYNC" if h_hash == c_hash else "STALE_IN_CONTAINER (Needs docker cp, volume mount, or rebuild!)"
            print(f"  {rel}: {status} (host={h_hash[:8]} vs container={c_hash[:8]})")

    if args.tail_errors > 0 and args.container:
        print(f"\n=== 4. RECENT CONTAINER EXCEPTIONS / ERRORS ({args.container}) ===")
        logs = run_cmd(["docker", "logs", "--tail", str(args.tail_errors), args.container])
        error_lines = [
            line for line in logs.splitlines()
            if any(k in line for k in ("Traceback", "Error:", "Exception", "CRITICAL", "ERROR", "panic:"))
        ]
        if error_lines:
            print("\n".join(error_lines[-20:]))
        else:
            print(f"  No recent Tracebacks/Errors in last {args.tail_errors} lines.")


if __name__ == "__main__":
    main()
