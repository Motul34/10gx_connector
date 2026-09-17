"""
In-memory Mock PLC Server for TOYOPUC 10GX Computer Link.
Used for local testing and CI without requiring physical PLC hardware.
"""

from __future__ import annotations
import math
import socket
import socketserver
import struct
import threading
from toyopuc.protocol import (
    CMD_PC10_MULTI_READ,
    CMD_PC10_MULTI_WRITE,
    build_frame,
)


class MockToyopucServer:
    """Mock TCP Server emulating TOYOPUC-Nano 2ET Ethernet Computer Link."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.requested_port = port
        self.port: int = 0
        self._server: socketserver.TCPServer | None = None
        self._thread: threading.Thread | None = None

        # Internal memory map: {logical_address: byte_value}
        self.memory: dict[int, int] = {}
        # Bit memory map: {logical_bit_address: bit_value (0 or 1)}
        self.bit_memory: dict[int, int] = {}
        self.lock = threading.Lock()

    def start(self) -> int:
        """Start the server in background thread and return the bound port."""
        outer = self

        class RequestHandler(socketserver.BaseRequestHandler):
            def handle(self):
                while True:
                    try:
                        header = self._recv_exact(5)
                        if not header:
                            break
                        ft, rc, transfer_count, cmd = struct.unpack("<BBHB", header)
                        remaining = transfer_count - 1
                        payload = self._recv_exact(remaining) if remaining > 0 else b""
                        resp = outer._handle_command(cmd, payload)
                        self.request.sendall(resp)
                    except (ConnectionResetError, BrokenPipeError, socket.error):
                        break

            def _recv_exact(self, count: int) -> bytes:
                buf = bytearray()
                while len(buf) < count:
                    chunk = self.request.recv(count - len(buf))
                    if not chunk:
                        return b""
                    buf.extend(chunk)
                return bytes(buf)

        self._server = socketserver.TCPServer(
            (self.host, self.requested_port),
            RequestHandler,
            bind_and_activate=True
        )
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        """Stop the server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _handle_command(self, cmd: int, payload: bytes) -> bytes:
        with self.lock:
            if cmd == CMD_PC10_MULTI_READ:
                return self._handle_multi_read(payload)
            elif cmd == CMD_PC10_MULTI_WRITE:
                return self._handle_multi_write(payload)
            else:
                # Return error 0x23 (invalid command)
                # Format: 80 10 01 00 23
                return struct.pack("<BBHBB", 0x80, 0x10, 0x0001, 0x23, 0x00)

    def _handle_multi_read(self, payload: bytes) -> bytes:
        n_bit, n_byte, n_word, n_long = struct.unpack_from("<BBBB", payload, 0)
        offset = 4

        bit_addrs = []
        for _ in range(n_bit):
            bit_addrs.append(struct.unpack_from("<I", payload, offset)[0])
            offset += 4

        byte_addrs = []
        for _ in range(n_byte):
            byte_addrs.append(struct.unpack_from("<I", payload, offset)[0])
            offset += 4

        word_addrs = []
        for _ in range(n_word):
            word_addrs.append(struct.unpack_from("<I", payload, offset)[0])
            offset += 4

        long_addrs = []
        for _ in range(n_long):
            long_addrs.append(struct.unpack_from("<I", payload, offset)[0])
            offset += 4

        # Read bit data (packed 8 bits per byte)
        num_bit_bytes = (n_bit + 7) // 8
        bit_bytes = bytearray(num_bit_bytes)
        for i, addr in enumerate(bit_addrs):
            val = self.bit_memory.get(addr, 0) & 1
            if val:
                bit_bytes[i // 8] |= (1 << (i % 8))

        # Read byte data
        byte_data = bytearray()
        for addr in byte_addrs:
            byte_data.append(self.memory.get(addr, 0) & 0xFF)

        # Read word data (2 bytes LE per point)
        word_data = bytearray()
        for addr in word_addrs:
            lo = self.memory.get(addr, 0) & 0xFF
            hi = self.memory.get(addr + 1, 0) & 0xFF
            word_data.extend(struct.pack("<H", lo | (hi << 8)))

        # Read long data (4 bytes LE per point)
        long_data = bytearray()
        for addr in long_addrs:
            b0 = self.memory.get(addr, 0) & 0xFF
            b1 = self.memory.get(addr + 1, 0) & 0xFF
            b2 = self.memory.get(addr + 2, 0) & 0xFF
            b3 = self.memory.get(addr + 3, 0) & 0xFF
            long_data.extend(struct.pack("<I", b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)))

        resp_payload = bytearray()
        resp_payload.extend(struct.pack("<BBBB", n_bit, n_byte, n_word, n_long))
        resp_payload.extend(bit_bytes)
        resp_payload.extend(byte_data)
        resp_payload.extend(word_data)
        resp_payload.extend(long_data)

        # Response format: 80 RC(00) LL LH CMD(C4) Payload...
        transfer_count = 1 + len(resp_payload)
        header = struct.pack("<BBHB", 0x80, 0x00, transfer_count, CMD_PC10_MULTI_READ)
        return header + bytes(resp_payload)

    def _handle_multi_write(self, payload: bytes) -> bytes:
        n_bit, n_byte, n_word, n_long = struct.unpack_from("<BBBB", payload, 0)
        offset = 4

        for _ in range(n_bit):
            addr, val = struct.unpack_from("<IB", payload, offset)
            self.bit_memory[addr] = 1 if (val & 1) else 0
            offset += 5

        for _ in range(n_byte):
            addr, val = struct.unpack_from("<IB", payload, offset)
            self.memory[addr] = val & 0xFF
            offset += 5

        for _ in range(n_word):
            addr, val = struct.unpack_from("<IH", payload, offset)
            self.memory[addr] = val & 0xFF
            self.memory[addr + 1] = (val >> 8) & 0xFF
            offset += 6

        for _ in range(n_long):
            addr, val = struct.unpack_from("<II", payload, offset)
            self.memory[addr] = val & 0xFF
            self.memory[addr + 1] = (val >> 8) & 0xFF
            self.memory[addr + 2] = (val >> 16) & 0xFF
            self.memory[addr + 3] = (val >> 24) & 0xFF
            offset += 8

        # Response: 80 00 01 00 C5
        header = struct.pack("<BBHB", 0x80, 0x00, 0x0001, CMD_PC10_MULTI_WRITE)
        return header
