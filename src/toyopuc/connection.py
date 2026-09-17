"""
TCP connection manager for TOYOPUC Computer Link.
Thread-safe with automatic reconnection and exact frame reception.
"""

from __future__ import annotations
import socket
import struct
import threading
import time
from toyopuc.exceptions import ToyopucConnectionError


class TcpConnection:
    """Manages the TCP socket connection to the TOYOPUC PLC."""

    def __init__(
        self,
        host: str,
        port: int = 1025,
        timeout: float = 3.0,
        auto_reconnect: bool = True,
        reconnect_interval: float = 1.0,
        max_reconnect_attempts: int | None = None,
    ):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts

        self._socket: socket.socket | None = None
        self._lock = threading.RLock()
        self._is_closing = False

    @property
    def is_connected(self) -> bool:
        return self._socket is not None

    def connect(self) -> None:
        """Establish connection to the PLC."""
        with self._lock:
            if self._socket is not None:
                return

            attempts = 0
            while not self._is_closing:
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.settimeout(self.timeout)
                    sock.connect((self.host, self.port))
                    self._socket = sock
                    return
                except (socket.error, OSError) as e:
                    if sock:
                        sock.close()
                    attempts += 1
                    if not self.auto_reconnect or (
                        self.max_reconnect_attempts is not None and attempts >= self.max_reconnect_attempts
                    ):
                        raise ToyopucConnectionError(
                            f"Failed to connect to TOYOPUC PLC at {self.host}:{self.port}: {e}"
                        ) from e
                    time.sleep(self.reconnect_interval)

    def disconnect(self) -> None:
        """Close the socket connection."""
        self._is_closing = True
        with self._lock:
            if self._socket is not None:
                try:
                    self._socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None

    def send_and_receive(self, request_bytes: bytes) -> bytes:
        """
        Send a command frame and receive the complete response frame.
        Thread-safe under `self._lock`.
        """
        with self._lock:
            if not self.is_connected:
                self.connect()

            while True:
                try:
                    assert self._socket is not None
                    self._socket.sendall(request_bytes)

                    # Read 5-byte response header: [FT(2B)] [TransferCount(2B LE)] [CMD(1B)]
                    header = self._recv_exact(5)
                    ft, rc, transfer_count, cmd = struct.unpack("<BBHB", header)

                    # Remaining payload length = transfer_count - 1 (since CMD was included)
                    remaining = transfer_count - 1
                    payload = self._recv_exact(remaining) if remaining > 0 else b""

                    return header + payload
                except (socket.error, OSError, ToyopucConnectionError) as e:
                    self._socket = None
                    if not self.auto_reconnect or self._is_closing:
                        raise ToyopucConnectionError(
                            f"Communication error with TOYOPUC PLC at {self.host}:{self.port}: {e}"
                        ) from e
                    # Reconnect and retry
                    time.sleep(self.reconnect_interval)
                    self.connect()

    def _recv_exact(self, num_bytes: int) -> bytes:
        """Receive exactly `num_bytes` from socket, handling fragmentation."""
        buf = bytearray()
        while len(buf) < num_bytes:
            if self._socket is None:
                raise ToyopucConnectionError("Socket disconnected during receive.")
            chunk = self._socket.recv(num_bytes - len(buf))
            if not chunk:
                raise ToyopucConnectionError("Connection closed by peer while receiving data.")
            buf.extend(chunk)
        return bytes(buf)

    def __enter__(self) -> TcpConnection:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
