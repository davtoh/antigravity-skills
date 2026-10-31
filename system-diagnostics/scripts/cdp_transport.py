#!/usr/bin/env python3
"""
Frontier Architect - Zero-Dependency Cross-Platform CDP WebSocket Transport.
Provides pure-Python RFC 6455 client via asyncio standard library,
with seamless fallback/delegation if third-party `websockets` is installed.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import struct
import sys
import time
from urllib.parse import urlparse


class StdlibWSClient:
    """Zero-dependency RFC 6455 WebSocket client using asyncio standard library."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self._closed = False

    @classmethod
    async def connect(cls, url: str, timeout: float = 10.0) -> StdlibWSClient:
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")

        ssl_ctx = None
        if parsed.scheme == "wss":
            import ssl
            ssl_ctx = ssl.create_default_context()

        coro = asyncio.open_connection(host, port, ssl=ssl_ctx)
        reader, writer = await asyncio.wait_for(coro, timeout=timeout)

        # Handshake
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        headers = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
            "\r\n",
        ]
        writer.write("\r\n".join(headers).encode("latin1"))
        await writer.drain()

        # Read handshake response
        status_line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if b"101" not in status_line:
            writer.close()
            await writer.wait_closed()
            raise ConnectionError(f"WebSocket upgrade rejected: {status_line.decode('latin1', errors='replace').strip()}")

        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=timeout)
            if line in (b"\r\n", b"\n", b""):
                break

        return cls(reader, writer)

    async def send(self, data: str) -> None:
        if self._closed:
            raise ConnectionResetError("WebSocket is closed")
        payload = data.encode("utf-8")
        length = len(payload)
        mask = os.urandom(4)

        header = bytearray([0x81])  # FIN=1, opcode=0x1 (text)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))

        header.extend(mask)
        masked_payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.writer.write(bytes(header) + masked_payload)
        await self.writer.drain()

    async def recv(self, timeout: float = 30.0) -> str:
        deadline = time.time() + timeout
        fragments = []

        while True:
            remaining = max(0.1, deadline - time.time())
            header_bytes = await asyncio.wait_for(self.reader.readexactly(2), timeout=remaining)
            b1, b2 = header_bytes[0], header_bytes[1]
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            has_mask = bool(b2 & 0x80)
            length = b2 & 0x7F

            if length == 126:
                ext = await asyncio.wait_for(self.reader.readexactly(2), timeout=remaining)
                (length,) = struct.unpack("!H", ext)
            elif length == 127:
                ext = await asyncio.wait_for(self.reader.readexactly(8), timeout=remaining)
                (length,) = struct.unpack("!Q", ext)

            mask = await asyncio.wait_for(self.reader.readexactly(4), timeout=remaining) if has_mask else None
            data = await asyncio.wait_for(self.reader.readexactly(length), timeout=remaining)
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

            if opcode == 0x8:  # Close
                self._closed = True
                self.writer.close()
                await self.writer.wait_closed()
                raise ConnectionResetError("WebSocket closed by peer")
            elif opcode == 0x9:  # Ping -> Pong (RFC 6455 §5.5.3: must echo the ping payload)
                pong_mask = os.urandom(4)
                pong_payload = bytes(b ^ pong_mask[i % 4] for i, b in enumerate(data[:125]))
                self.writer.write(bytes([0x8A, 0x80 | len(pong_payload)]) + pong_mask + pong_payload)
                await self.writer.drain()
                continue
            elif opcode in (0x2, 0xA):  # Binary / unsolicited pong: CDP never needs these
                continue
            elif opcode in (0x1, 0x0):  # Text or continuation
                fragments.append(data)
                if fin:
                    return b"".join(fragments).decode("utf-8", errors="replace")

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                # Send close frame
                close_frame = bytearray([0x88, 0x80]) + os.urandom(4)
                self.writer.write(close_frame)
                await self.writer.drain()
            except Exception:
                pass
            finally:
                self.writer.close()
                await self.writer.wait_closed()

    async def __aenter__(self) -> StdlibWSClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class CDPSession:
    """CDP session wrapping either websockets package or StdlibWSClient."""

    def __init__(self, ws):
        self.ws = ws
        self.msg_id = 0

    async def send(self, method: str, params: dict | None = None, session_id: str | None = None, timeout: float = 15.0) -> dict:
        self.msg_id += 1
        call_id = self.msg_id
        payload = {"id": call_id, "method": method, "params": params or {}}
        if session_id:
            payload["sessionId"] = session_id
        await self.ws.send(json.dumps(payload))

        deadline = time.time() + timeout
        while True:
            remaining = max(0.1, deadline - time.time())
            raw = await asyncio.wait_for(self.ws.recv(), timeout=remaining)
            msg = json.loads(raw)
            if msg.get("id") == call_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP error in {method}: {msg['error']}")
                return msg.get("result", {})


async def connect_ws(url: str, timeout: float = 10.0):
    """Connect to WebSocket URL using websockets library if available, else pure stdlib."""
    try:
        import websockets  # type: ignore
        return await websockets.connect(url, max_size=50 * 1024 * 1024, open_timeout=timeout)
    except ImportError:
        return await StdlibWSClient.connect(url, timeout=timeout)
