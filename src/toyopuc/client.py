"""
Main client interface for TOYOPUC 10GX PLC.
Provides bit_read, bit_write, byte_read, byte_write, word_read, word_write,
long_read, long_write, and background polling.
"""

from __future__ import annotations
from typing import Any, Mapping, Sequence
from toyopuc.address import DataType, ParsedAddress, parse_address
from toyopuc.connection import TcpConnection
from toyopuc.exceptions import ToyopucAddressError
from toyopuc.poller import BackgroundPoller
from toyopuc.protocol import (
    CMD_PC10_MULTI_READ,
    CMD_PC10_MULTI_WRITE,
    MAX_POINTS_PER_COMMAND,
    build_pc10_multi_read_request,
    build_pc10_multi_write_request,
    parse_pc10_multi_read_response,
    parse_response_frame,
)


class ToyopucClient:
    """Client for communicating with JTEKT TOYOPUC 10GX PLC."""

    def __init__(
        self,
        host: str,
        port: int = 1025,
        timeout: float = 3.0,
        auto_reconnect: bool = True,
    ):
        self.host = host
        self.port = port
        self.connection = TcpConnection(
            host=host,
            port=port,
            timeout=timeout,
            auto_reconnect=auto_reconnect,
        )
        self._active_pollers: list[BackgroundPoller] = []

    @property
    def is_connected(self) -> bool:
        """Check if TCP socket is currently connected."""
        return self.connection.is_connected

    def connect(self) -> ToyopucClient:
        """Connect to the PLC."""
        self.connection.connect()
        return self

    def disconnect(self) -> None:
        """Disconnect from the PLC (alias for close)."""
        self.close()

    def close(self) -> None:
        """Stop all active pollers and close the socket connection."""
        self.stop_polling()
        self.connection.disconnect()

    def __enter__(self) -> ToyopucClient:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # -------------------------------------------------------------------------
    # Read Methods (always return list[int])
    # -------------------------------------------------------------------------
    def bit_read(self, *addresses: str | Sequence[str]) -> list[int]:
        """
        Read one or more bit addresses.
        Returns a list of integer values (0 or 1).
        Single address: plc.bit_read("P1-M100")[0]
        Multiple addresses: plc.bit_read("P1-M100", "P1-M108") -> [1, 0]
        """
        flattened = self._flatten_addresses(addresses)
        parsed = [parse_address(a, default_data_type=DataType.BIT) for a in flattened]
        return self._execute_multi_read(parsed)

    def byte_read(self, *addresses: str | Sequence[str]) -> list[int]:
        """
        Read one or more byte addresses.
        Returns a list of integer values (0 - 255).
        """
        flattened = self._flatten_addresses(addresses)
        parsed = [parse_address(a, default_data_type=DataType.BYTE) for a in flattened]
        return self._execute_multi_read(parsed)

    def word_read(self, *addresses: str | Sequence[str]) -> list[int]:
        """
        Read one or more word addresses (16-bit).
        Returns a list of integer values (0 - 65535).
        Single address: plc.word_read("P1-D100")[0]
        Multiple addresses: plc.word_read("P1-D100", "P1-D200") -> [1234, 5678]
        """
        flattened = self._flatten_addresses(addresses)
        parsed = [parse_address(a, default_data_type=DataType.WORD) for a in flattened]
        return self._execute_multi_read(parsed)

    def long_read(self, *addresses: str | Sequence[str]) -> list[int]:
        """
        Read one or more double-word (32-bit long) addresses.
        Returns a list of integer values (0 - 4294967295).
        """
        flattened = self._flatten_addresses(addresses)
        parsed = [parse_address(a, default_data_type=DataType.LONG) for a in flattened]
        return self._execute_multi_read(parsed)

    def read_mixed(self, addresses: Sequence[str]) -> dict[str, int]:
        """
        Read mixed bit, byte, and word addresses in one command.
        Returns a dictionary mapping {address_str: value}.
        """
        parsed = [parse_address(a) for a in addresses]
        values = self._execute_multi_read(parsed)
        return dict(zip(addresses, values))

    # -------------------------------------------------------------------------
    # Write Methods (accept dict[str, int] or (address, value))
    # -------------------------------------------------------------------------
    def bit_write(
        self,
        data: Mapping[str, int | bool] | str,
        value: int | bool | None = None,
    ) -> int:
        """
        Write bit values using dictionary format: {"P1-M100": 1, "P1-M108": 0}.
        Also supports single write: plc.bit_write("P1-M100", 1).
        Returns number of written items.
        """
        write_dict = self._normalize_write_input(data, value)
        items = [
            (parse_address(addr, default_data_type=DataType.BIT), 1 if val else 0)
            for addr, val in write_dict.items()
        ]
        return self._execute_multi_write(items)

    def byte_write(
        self,
        data: Mapping[str, int] | str,
        value: int | None = None,
    ) -> int:
        """
        Write byte values using dictionary format: {"P1-D100L": 0x12}.
        """
        write_dict = self._normalize_write_input(data, value)
        items = [
            (parse_address(addr, default_data_type=DataType.BYTE), int(val) & 0xFF)
            for addr, val in write_dict.items()
        ]
        return self._execute_multi_write(items)

    def word_write(
        self,
        data: Mapping[str, int] | str,
        value: int | None = None,
    ) -> int:
        """
        Write word values using dictionary format: {"P1-D100": 1234, "P1-D200": 5678}.
        Also supports single write: plc.word_write("P1-D100", 1234).
        Returns number of written items.
        """
        write_dict = self._normalize_write_input(data, value)
        items = [
            (parse_address(addr, default_data_type=DataType.WORD), int(val) & 0xFFFF)
            for addr, val in write_dict.items()
        ]
        return self._execute_multi_write(items)

    def long_write(
        self,
        data: Mapping[str, int] | str,
        value: int | None = None,
    ) -> int:
        """
        Write 32-bit double-word values using dictionary format: {"P1-D100": 100000}.
        Returns number of written items.
        """
        write_dict = self._normalize_write_input(data, value)
        items = [
            (parse_address(addr, default_data_type=DataType.LONG), int(val) & 0xFFFFFFFF)
            for addr, val in write_dict.items()
        ]
        return self._execute_multi_write(items)

    # -------------------------------------------------------------------------
    # Background Polling
    # -------------------------------------------------------------------------
    def start_polling(self, addresses: Sequence[str], interval: float = 1.0) -> BackgroundPoller:
        """
        Start periodic background reading of specified addresses.
        Returns a BackgroundPoller instance to query latest values.
        """
        poller = BackgroundPoller(client=self, addresses=list(addresses), interval=interval)
        poller.start()
        self._active_pollers.append(poller)
        return poller

    def stop_polling(self, poller: BackgroundPoller | None = None) -> None:
        """
        Stop background polling.
        If `poller` is given, stops that specific poller.
        If `poller` is None, stops all currently active pollers.
        """
        if poller is not None:
            poller.stop()
            if poller in self._active_pollers:
                self._active_pollers.remove(poller)
        else:
            for p in self._active_pollers:
                p.stop()
            self._active_pollers.clear()

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------
    def _flatten_addresses(self, addresses: tuple[Any, ...]) -> list[str]:
        flattened: list[str] = []
        for item in addresses:
            if isinstance(item, (list, tuple)):
                flattened.extend(str(x) for x in item)
            else:
                flattened.append(str(item))
        if not flattened:
            raise ToyopucAddressError("No address specified.")
        return flattened

    def _normalize_write_input(
        self,
        data: Mapping[str, Any] | str,
        value: Any | None,
    ) -> dict[str, Any]:
        if isinstance(data, Mapping):
            return dict(data)
        if isinstance(data, str):
            if value is None:
                raise ValueError(f"Value must be provided for single address write: '{data}'")
            return {data: value}
        raise ValueError(f"Invalid write data format: expected dict or (address, value), got {type(data)}")

    def _execute_multi_read(self, parsed_addrs: Sequence[ParsedAddress]) -> list[int]:
        """Execute multi-read with automatic chunking up to 127 points."""
        results: list[int] = []
        for i in range(0, len(parsed_addrs), MAX_POINTS_PER_COMMAND):
            chunk = parsed_addrs[i: i + MAX_POINTS_PER_COMMAND]
            req = build_pc10_multi_read_request(chunk)
            resp = self.connection.send_and_receive(req)
            payload = parse_response_frame(resp, expected_cmd=CMD_PC10_MULTI_READ)
            chunk_vals = parse_pc10_multi_read_response(payload, chunk)
            results.extend(chunk_vals)
        return results

    def _execute_multi_write(self, items: Sequence[tuple[ParsedAddress, int]]) -> int:
        """Execute multi-write with automatic chunking up to 127 points."""
        total_written = 0
        for i in range(0, len(items), MAX_POINTS_PER_COMMAND):
            chunk = items[i: i + MAX_POINTS_PER_COMMAND]
            req = build_pc10_multi_write_request(chunk)
            resp = self.connection.send_and_receive(req)
            parse_response_frame(resp, expected_cmd=CMD_PC10_MULTI_WRITE)
            total_written += len(chunk)
        return total_written
