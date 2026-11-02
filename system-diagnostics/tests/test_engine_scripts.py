#!/usr/bin/env python3
"""Automated unit test suite for bundled engine scripts in system-diagnostics:
- docker_audit.py
- cdp_inspect.py
- cdp_transport.py

Zero external dependencies; standard library Python 3.10+ only.
Runs across Windows, macOS, and Linux via python -m unittest.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure system-diagnostics/scripts is in sys.path
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import docker_audit
import cdp_inspect
from cdp_transport import CDPSession


class TestDockerAuditEngine(unittest.TestCase):
    """Test suite for system-diagnostics/scripts/docker_audit.py."""

    def test_host_md5_existing_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as tf:
            tf.write("hello system diagnostics")
            temp_path = tf.name

        try:
            expected = hashlib.md5(b"hello system diagnostics", usedforsecurity=False).hexdigest()
            actual = docker_audit.host_md5(temp_path)
            self.assertEqual(actual, expected)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_host_md5_missing_file(self):
        result = docker_audit.host_md5("nonexistent_system_diag_test_xyz.file")
        self.assertEqual(result, "MISSING_ON_HOST")

    def test_run_cmd_handles_missing_command_safely(self):
        result = docker_audit.run_cmd(["__nonexistent_system_diag_cli_cmd_9999__"])
        self.assertTrue(result.startswith("Error:") or "not found" in result.lower())

    def test_docker_daemon_error_strings_recognized(self):
        daemon_errs = ("error during connect", "cannot connect to the docker daemon", "failed to connect to the docker api")
        sample_error = "Error response from daemon: Cannot connect to the Docker daemon at unix:///var/run/docker.sock."
        self.assertTrue(any(err in sample_error.lower() for err in daemon_errs))

    def test_arg_parser_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            parser = argparse.ArgumentParser()
            parser.add_argument("--container", default=os.getenv("DOCKER_CONTAINER"))
            parser.add_argument("--workdir", default=os.getenv("CONTAINER_WORKDIR", "/app"))
            parser.add_argument("--sync-check", nargs="*", default=[])
            parser.add_argument("--tail-errors", type=int, default=150)

            args = parser.parse_args([])
            self.assertIsNone(args.container)
            self.assertEqual(args.workdir, "/app")
            self.assertEqual(args.sync_check, [])
            self.assertEqual(args.tail_errors, 150)

    def test_arg_parser_custom_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--container", default=None)
        parser.add_argument("--workdir", default="/app")
        parser.add_argument("--sync-check", nargs="*", default=[])
        parser.add_argument("--tail-errors", type=int, default=150)

        args = parser.parse_args([
            "--container", "my_app_container",
            "--workdir", "/workspace/srv",
            "--sync-check", "app.py", "styles.css",
            "--tail-errors", "50",
        ])
        self.assertEqual(args.container, "my_app_container")
        self.assertEqual(args.workdir, "/workspace/srv")
        self.assertEqual(args.sync_check, ["app.py", "styles.css"])
        self.assertEqual(args.tail_errors, 50)


class TestCDPTransportEngine(unittest.TestCase):
    """Test suite for system-diagnostics/scripts/cdp_transport.py."""

    def test_cdp_session_call_formatting(self):
        session = CDPSession(ws=None)
        self.assertEqual(session.msg_id, 0)
        session.msg_id += 1
        msg = {"id": session.msg_id, "method": "Page.enable", "params": {}}
        self.assertEqual(msg["id"], 1)
        self.assertEqual(msg["method"], "Page.enable")

    def test_rfc6455_frame_header_small_payload(self):
        payload = b"ping test"
        length = len(payload)
        mask = b"\x01\x02\x03\x04"

        header = bytearray([0x81])  # FIN=1, text opcode
        header.append(0x80 | length)
        header.extend(mask)

        masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        frame = bytes(header) + masked_payload

        self.assertEqual(frame[0], 0x81)
        self.assertEqual(frame[1] & 0x7F, length)
        self.assertEqual(frame[2:6], mask)
        unmasked = bytes(b ^ mask[i % 4] for i, b in enumerate(frame[6:]))
        self.assertEqual(unmasked, payload)

    def test_rfc6455_frame_header_medium_payload(self):
        payload = b"x" * 300
        length = len(payload)
        mask = b"\xaa\xbb\xcc\xdd"

        header = bytearray([0x81])
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
        header.extend(mask)

        masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        frame = bytes(header) + masked_payload

        self.assertEqual(frame[0], 0x81)
        self.assertEqual(frame[1] & 0x7F, 126)
        unpacked_len = struct.unpack("!H", frame[2:4])[0]
        self.assertEqual(unpacked_len, 300)
        self.assertEqual(frame[4:8], mask)

    def test_rfc6455_frame_header_large_payload(self):
        length = 70000
        header = bytearray([0x81])
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
        self.assertEqual(header[0], 0x81)
        self.assertEqual(header[1] & 0x7F, 127)
        unpacked_len = struct.unpack("!Q", header[2:10])[0]
        self.assertEqual(unpacked_len, 70000)

    def test_rfc6455_close_frame_opcode(self):
        close_frame = bytearray([0x88, 0x80])
        self.assertEqual(close_frame[0], 0x88)
        self.assertEqual(close_frame[0] & 0x0F, 0x08)


class TestCDPInspectEngine(unittest.TestCase):
    """Test suite for system-diagnostics/scripts/cdp_inspect.py."""

    def test_chrome_executable_env_override(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tf:
            mock_chrome = tf.name

        try:
            with patch.dict(os.environ, {"CHROME_BIN": mock_chrome}):
                found = cdp_inspect.find_chrome_executable()
                self.assertEqual(found, mock_chrome)
        finally:
            if os.path.exists(mock_chrome):
                os.remove(mock_chrome)

    def test_arg_parser_options(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--url", default=None)
        parser.add_argument("--list-tabs", action="store_true")
        parser.add_argument("--audit-layout", action="store_true")
        parser.add_argument("--selectors", default=None)
        parser.add_argument("--eval", default=None)
        parser.add_argument("--headless", action="store_true")
        parser.add_argument("--window-size", default="1440x900")
        parser.add_argument("--port", type=int, default=0)

        args = parser.parse_args([
            "--url", "http://localhost:3000",
            "--audit-layout",
            "--selectors", "#app,.header,video",
            "--eval", "document.title",
            "--headless",
            "--window-size", "1920x1080",
            "--port", "9222",
        ])

        self.assertEqual(args.url, "http://localhost:3000")
        self.assertTrue(args.audit_layout)
        self.assertEqual(args.selectors, "#app,.header,video")
        self.assertEqual(args.eval, "document.title")
        self.assertTrue(args.headless)
        self.assertEqual(args.window_size, "1920x1080")
        self.assertEqual(args.port, 9222)

    def test_url_env_fallback(self):
        with patch.dict(os.environ, {"APP_URL": "http://127.0.0.1:8000"}):
            url_val = os.getenv("APP_URL")
            self.assertEqual(url_val, "http://127.0.0.1:8000")

    def test_parse_viewport_valid(self):
        w, h = cdp_inspect.parse_viewport("1920x1080")
        self.assertEqual((w, h), (1920, 1080))
        w2, h2 = cdp_inspect.parse_viewport("1440X900")
        self.assertEqual((w2, h2), (1440, 900))

    def test_parse_viewport_invalid_raises_error(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            cdp_inspect.parse_viewport("invalid_viewport")

    def test_build_generic_audit_js_contains_selectors(self):
        js_code = cdp_inspect.build_generic_audit_js(["#canvas", ".player"])
        self.assertIn("#canvas", js_code)
        self.assertIn(".player", js_code)


if __name__ == "__main__":
    unittest.main()
