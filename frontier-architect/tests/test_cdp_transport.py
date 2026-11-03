#!/usr/bin/env python3
"""
Unit tests for scripts/cdp_transport.py.
Tests 100% of StdlibWSClient RFC 6455 and CDPSession logic using asyncio standard library,
with zero external network dependencies and zero requirement for third-party websockets package.
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cdp_transport
from cdp_transport import CDPSession, StdlibWSClient, connect_ws


def build_raw_frame(opcode: int, payload: bytes, fin: bool = True, mask: bytes | None = None) -> bytes:
    """Helper to construct raw RFC 6455 frames for testing client recv."""
    b1 = (0x80 if fin else 0x00) | (opcode & 0x0F)
    length = len(payload)
    has_mask = mask is not None
    mask_bit = 0x80 if has_mask else 0x00

    out = bytearray([b1])
    if length < 126:
        out.append(mask_bit | length)
    elif length < 65536:
        out.append(mask_bit | 126)
        out.extend(struct.pack("!H", length))
    else:
        out.append(mask_bit | 127)
        out.extend(struct.pack("!Q", length))

    if has_mask:
        out.extend(mask)
        masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        out.extend(masked_payload)
    else:
        out.extend(payload)
    return bytes(out)


def make_mock_writer():
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    return writer


class TestCDPTransport(unittest.TestCase):
    """Thorough unit tests for cdp_transport.py."""

    def test_cdp_session_call_formatting(self):
        session = CDPSession(ws=None)
        self.assertEqual(session.msg_id, 0)
        session.msg_id += 1
        msg = {"id": session.msg_id, "method": "Page.enable", "params": {}}
        self.assertEqual(msg["id"], 1)
        self.assertEqual(msg["method"], "Page.enable")

    def test_cdp_session_send_and_recv_success(self):
        async def _test():
            mock_ws = AsyncMock()
            response_json = json.dumps({"id": 1, "result": {"targetId": "ABC-123"}})
            mock_ws.recv.return_value = response_json

            session = CDPSession(mock_ws)
            res = await session.send("Target.createTarget", {"url": "http://localhost"}, session_id="SESS-1")

            self.assertEqual(res, {"targetId": "ABC-123"})
            mock_ws.send.assert_called_once()
            sent_payload = json.loads(mock_ws.send.call_args[0][0])
            self.assertEqual(sent_payload["id"], 1)
            self.assertEqual(sent_payload["sessionId"], "SESS-1")
            self.assertEqual(sent_payload["method"], "Target.createTarget")

        asyncio.run(_test())

    def test_cdp_session_send_runtime_error_on_cdp_failure(self):
        async def _test():
            mock_ws = AsyncMock()
            error_json = json.dumps({"id": 1, "error": {"code": -32000, "message": "Cannot navigate"}})
            mock_ws.recv.return_value = error_json

            session = CDPSession(mock_ws)
            with self.assertRaises(RuntimeError) as ctx:
                await session.send("Page.navigate", {"url": "invalid://"})
            self.assertIn("CDP error in Page.navigate", str(ctx.exception))

        asyncio.run(_test())

    def test_stdlib_ws_send_closed_raises_error(self):
        client = StdlibWSClient(reader=MagicMock(), writer=MagicMock())
        client._closed = True
        with self.assertRaises(ConnectionResetError):
            asyncio.run(client.send("hello"))

    def test_stdlib_ws_send_small_medium_large_payloads(self):
        async def _test():
            mock_writer = make_mock_writer()
            client = StdlibWSClient(reader=MagicMock(), writer=mock_writer)

            # Small payload (<126)
            await client.send("small payload")
            self.assertTrue(mock_writer.write.called)
            data1 = mock_writer.write.call_args[0][0]
            self.assertEqual(data1[0], 0x81)
            self.assertEqual(data1[1] & 0x7F, len("small payload"))

            # Medium payload (126 <= len < 65536)
            mock_writer.reset_mock()
            medium_str = "A" * 500
            await client.send(medium_str)
            data2 = mock_writer.write.call_args[0][0]
            self.assertEqual(data2[0], 0x81)
            self.assertEqual(data2[1] & 0x7F, 126)
            unpacked_len = struct.unpack("!H", data2[2:4])[0]
            self.assertEqual(unpacked_len, 500)

            # Large payload (>=65536)
            mock_writer.reset_mock()
            large_str = "B" * 70000
            await client.send(large_str)
            data3 = mock_writer.write.call_args[0][0]
            self.assertEqual(data3[0], 0x81)
            self.assertEqual(data3[1] & 0x7F, 127)
            unpacked_len_lg = struct.unpack("!Q", data3[2:10])[0]
            self.assertEqual(unpacked_len_lg, 70000)

        asyncio.run(_test())

    def test_stdlib_ws_recv_text_and_continuation_frames(self):
        async def _test():
            reader = asyncio.StreamReader()
            mock_writer = make_mock_writer()
            client = StdlibWSClient(reader=reader, writer=mock_writer)

            # 1. Unmasked single text frame
            reader.feed_data(build_raw_frame(opcode=0x1, payload=b"hello cdp", fin=True))
            msg = await client.recv(timeout=2.0)
            self.assertEqual(msg, "hello cdp")

            # 2. Masked single text frame
            mask = b"\x12\x34\x56\x78"
            reader.feed_data(build_raw_frame(opcode=0x1, payload=b"masked text", fin=True, mask=mask))
            msg2 = await client.recv(timeout=2.0)
            self.assertEqual(msg2, "masked text")

            # 3. Fragmented message: continuation frame (opcode 0x1 fin=False, then 0x0 fin=True)
            reader.feed_data(build_raw_frame(opcode=0x1, payload=b"chunk1_", fin=False))
            reader.feed_data(build_raw_frame(opcode=0x0, payload=b"chunk2", fin=True))
            msg3 = await client.recv(timeout=2.0)
            self.assertEqual(msg3, "chunk1_chunk2")

            # 4. Extended payload length 126 in recv
            long_payload = b"X" * 300
            reader.feed_data(build_raw_frame(opcode=0x1, payload=long_payload, fin=True))
            msg4 = await client.recv(timeout=2.0)
            self.assertEqual(msg4, "X" * 300)

        asyncio.run(_test())

    def test_stdlib_ws_recv_close_and_ping_pong_frames(self):
        async def _test():
            reader = asyncio.StreamReader()
            mock_writer = make_mock_writer()
            client = StdlibWSClient(reader=reader, writer=mock_writer)

            # Ping frame (opcode 0x9) echoes pong (0x8A) and continues to receive text
            reader.feed_data(build_raw_frame(opcode=0x9, payload=b"heartbeat", fin=True))
            reader.feed_data(build_raw_frame(opcode=0x1, payload=b"after ping", fin=True))
            msg = await client.recv(timeout=2.0)
            self.assertEqual(msg, "after ping")
            self.assertTrue(mock_writer.write.called)
            pong_written = mock_writer.write.call_args[0][0]
            self.assertEqual(pong_written[0], 0x8A)

            # Binary opcode (0x2) and unsolicited pong (0xA) skipped
            reader.feed_data(build_raw_frame(opcode=0x2, payload=b"bin", fin=True))
            reader.feed_data(build_raw_frame(opcode=0xA, payload=b"pong", fin=True))
            reader.feed_data(build_raw_frame(opcode=0x1, payload=b"after binary", fin=True))
            msg2 = await client.recv(timeout=2.0)
            self.assertEqual(msg2, "after binary")

            # Close frame (opcode 0x8) raises ConnectionResetError
            reader.feed_data(build_raw_frame(opcode=0x8, payload=b"", fin=True))
            with self.assertRaises(ConnectionResetError):
                await client.recv(timeout=2.0)
            self.assertTrue(client._closed)

        asyncio.run(_test())

    def test_stdlib_ws_close_and_context_manager(self):
        async def _test():
            mock_writer = make_mock_writer()
            client = StdlibWSClient(reader=MagicMock(), writer=mock_writer)
            self.assertFalse(client._closed)

            async with client as c:
                self.assertEqual(c, client)

            self.assertTrue(client._closed)
            self.assertTrue(mock_writer.close.called)
            self.assertTrue(mock_writer.wait_closed.called)

        asyncio.run(_test())

    def test_stdlib_connect_handshake_success(self):
        async def _test():
            reader = asyncio.StreamReader()
            reader.feed_data(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
            mock_writer = make_mock_writer()

            with patch("asyncio.open_connection", return_value=(reader, mock_writer)):
                client = await StdlibWSClient.connect("ws://127.0.0.1:9222/devtools/page/123", timeout=2.0)
                self.assertIsInstance(client, StdlibWSClient)
                self.assertFalse(client._closed)
                self.assertTrue(mock_writer.write.called)

        asyncio.run(_test())

    def test_stdlib_connect_handshake_rejected_raises_error(self):
        async def _test():
            reader = asyncio.StreamReader()
            reader.feed_data(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            mock_writer = make_mock_writer()

            with patch("asyncio.open_connection", return_value=(reader, mock_writer)):
                with self.assertRaises(ConnectionError) as ctx:
                    await StdlibWSClient.connect("ws://127.0.0.1:9222/devtools/page/123", timeout=2.0)
                self.assertIn("WebSocket upgrade rejected", str(ctx.exception))

        asyncio.run(_test())

    def test_connect_ws_delegation_and_fallback(self):
        async def _test():
            # Test when websockets package cannot be imported
            with patch.dict(sys.modules, {"websockets": None}):
                with patch.object(StdlibWSClient, "connect", new_callable=AsyncMock) as mock_std_connect:
                    mock_std_connect.return_value = "stdlib_instance"
                    res = await connect_ws("ws://localhost:9222/test")
                    self.assertEqual(res, "stdlib_instance")
                    mock_std_connect.assert_called_once_with("ws://localhost:9222/test", timeout=10.0)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
