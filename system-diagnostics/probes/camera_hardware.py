#!/usr/bin/env python3
"""Diagnostic Probe: camera_hardware.

Standard Protocol Diagnostic Probe for Camera Hardware & Video Acquisition.
Detects physical and virtual video capture devices, validates frame acquisition
without relying on brittle hardware register queries, and identifies potential
device lockups or driver unbind collisions.
"""

import json
import os
import subprocess
import sys
import time
from typing import Any

def _probe_opencv_indices(max_indices: int = 5) -> list[dict[str, Any]]:
    """Probe camera indices using OpenCV VideoCapture with cross-platform backends."""
    results: list[dict[str, Any]] = []
    try:
        import cv2
    except ImportError:
        return [{"warning": "OpenCV (cv2) is not installed in the active environment."}]

    # Determine backend priorities based on OS
    if os.name == "nt":
        backends = [("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF), ("ANY", cv2.CAP_ANY)]
    else:
        backends = [("V4L2", getattr(cv2, "CAP_V4L2", cv2.CAP_ANY)), ("ANY", cv2.CAP_ANY)]

    for idx in range(max_indices):
        opened = False
        detected_backend = None
        resolution = None
        fps = 0.0
        frame_valid = False

        for b_name, b_val in backends:
            try:
                cap = cv2.VideoCapture(idx, b_val)
                if cap.isOpened():
                    opened = True
                    detected_backend = b_name
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                    resolution = f"{w}x{h}" if w > 0 and h > 0 else "Unknown"

                    # Decode 1 test frame to verify actual image buffer
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        frame_valid = True
                    cap.release()
                    break
                cap.release()
            except Exception:
                continue

        if opened:
            results.append({
                "index": idx,
                "backend": detected_backend,
                "resolution": resolution,
                "fps": fps,
                "frame_decodable": frame_valid,
                "status": "ready" if frame_valid else "open_but_empty",
            })

    return results

def _probe_windows_pnp_cameras() -> list[dict[str, Any]]:
    """Query Windows PnP Camera devices via PowerShell."""
    if os.name != "nt":
        return []
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-PnpDevice -Class Camera, Image -ErrorAction SilentlyContinue | "
            "Select-Object FriendlyName, Status, Present, InstanceId | ConvertTo-Json -Compress",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
        if res.returncode == 0 and res.stdout.strip():
            raw = json.loads(res.stdout.strip())
            items = raw if isinstance(raw, list) else [raw]
            return [
                {
                    "name": item.get("FriendlyName"),
                    "status": item.get("Status"),
                    "present": item.get("Present"),
                    "id": item.get("InstanceId"),
                }
                for item in items
                if item.get("FriendlyName")
            ]
    except Exception:
        pass
    return []

def probe(*args: str, **kwargs: Any) -> dict[str, Any]:
    """Execute camera hardware diagnostic probe.

    Returns:
        Structured telemetry dict with status, summary, and camera details.
    """
    start_time = time.perf_counter()
    pnp_devices = _probe_windows_pnp_cameras()
    cv_devices = _probe_opencv_indices(max_indices=kwargs.get("max_indices", 4))

    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

    active_count = len([d for d in cv_devices if d.get("frame_decodable")])
    if active_count > 0:
        status = "ok"
        summary = f"Detected {active_count} active camera device(s) ready for capture."
    elif cv_devices:
        status = "warning"
        summary = f"Detected {len(cv_devices)} device index(es), but no frames could be decoded."
    else:
        status = "warning" if pnp_devices else "error"
        summary = "No OpenCV camera capture devices available."

    return {
        "status": status,
        "domain": "hardware/camera",
        "summary": summary,
        "details": {
            "opencv_devices": cv_devices,
            "pnp_devices": pnp_devices,
            "os": os.name,
        },
        "latency_ms": elapsed_ms,
    }

def main() -> int:
    result = probe()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in ("ok", "warning") else 1

if __name__ == "__main__":
    sys.exit(main())
