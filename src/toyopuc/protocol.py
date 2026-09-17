"""
Binary protocol encoding and decoding for TOYOPUC 10GX Computer Link.
Supports PC10 Multi-point Read (0xC4) and Multi-point Write (0xC5).
"""

from __future__ import annotations
import math
import struct
from dataclasses import dataclass
from typing import Sequence
from toyopuc.address import DataType, ParsedAddress
from toyopuc.exceptions import ToyopucResponseError, ToyopucError

# Commands
CMD_PC10_MULTI_READ = 0xC4
CMD_PC10_MULTI_WRITE = 0xC5
CMD_PC10_BYTE_READ = 0xC2
CMD_PC10_BYTE_WRITE = 0xC3

MAX_POINTS_PER_COMMAND = 127
MAX_WRITE_BYTES = 500


def build_frame(cmd: int, payload: bytes) -> bytes:
    """
    Build a standard TOYOPUC Computer Link Ethernet frame.
    Format: [FT(2B)=00 00] [TransferCount(2B LE)] [CMD(1B)] [Payload...]
    Transfer count = 1 (CMD) + len(payload)
    """
    transfer_count = 1 + len(payload)
    header = struct.pack("<HHB", 0x0000, transfer_count, cmd)
    return header + payload


def parse_response_frame(raw_data: bytes, expected_cmd: int | None = None) -> bytes:
    """
    Validate and parse a TOYOPUC response frame.
    Format: [FT=0x80, RC] [TransferCount(2B LE)] [CMD(1B)] [Payload...]
    Returns the payload bytes.
    """
    if len(raw_data) < 5:
        raise ToyopucError(f"Response frame too short: {len(raw_data)} bytes")

    ft, rc, transfer_count, cmd_or_err = struct.unpack_from("<BBHB", raw_data, 0)

    if ft != 0x80:
        raise ToyopucError(f"Invalid frame type in response: 0x{ft:02X} (expected 0x80)")

    if rc != 0x00:
        # Error response format from Manual 3.7.5.2:
        # "80 10 01 00 [error_code]" -> 5th byte (cmd_or_err) is error code.
        # Or standard frame "80 RC LL LH CMD [error_code]..." -> 6th byte.
        if len(raw_data) > 5:
            error_code = raw_data[5]
        else:
            error_code = cmd_or_err
        raise ToyopucResponseError(response_code=rc, error_code=error_code)

    if expected_cmd is not None and cmd_or_err != expected_cmd:
        raise ToyopucError(f"Unexpected response command code: 0x{cmd_or_err:02X} (expected 0x{expected_cmd:02X})")

    payload = raw_data[5: 4 + transfer_count]
    return payload


def build_pc10_multi_read_request(addresses: Sequence[ParsedAddress]) -> bytes:
    """
    Build PC10 Multi-point Read (CMD=0xC4) payload.
    Header: [bit_count(1B)] [byte_count(1B)] [word_count(1B)] [long_count(1B)]
    Addresses:
      - bit addresses (4B LE each)
      - byte addresses (4B LE each)
      - word addresses (4B LE each, byte addressing as per manual)
      - long addresses (4B LE each)
    """
    bit_addrs = [a for a in addresses if a.data_type == DataType.BIT]
    byte_addrs = [a for a in addresses if a.data_type == DataType.BYTE]
    word_addrs = [a for a in addresses if a.data_type == DataType.WORD]
    long_addrs = [a for a in addresses if a.data_type == DataType.LONG]

    total_pts = len(bit_addrs) + len(byte_addrs) + len(word_addrs) + len(long_addrs)
    if total_pts > MAX_POINTS_PER_COMMAND:
        raise ToyopucError(f"Multi-read point count ({total_pts}) exceeds maximum ({MAX_POINTS_PER_COMMAND})")

    payload = bytearray()
    payload.extend(struct.pack("<BBBB", len(bit_addrs), len(byte_addrs), len(word_addrs), len(long_addrs)))

    for a in bit_addrs:
        payload.extend(struct.pack("<I", a.logical_address))
    for a in byte_addrs:
        payload.extend(struct.pack("<I", a.logical_address))
    for a in word_addrs:
        payload.extend(struct.pack("<I", a.logical_address))
    for a in long_addrs:
        payload.extend(struct.pack("<I", a.logical_address))

    return build_frame(CMD_PC10_MULTI_READ, bytes(payload))


def parse_pc10_multi_read_response(payload: bytes, addresses: Sequence[ParsedAddress]) -> list[int]:
    """
    Parse PC10 Multi-point Read (CMD=0xC4) response payload.
    Payload:
      [bit_count(1B)] [byte_count(1B)] [word_count(1B)] [long_count(1B)]
      [bit_data...] (8 points per byte, bit 0 to bit 7)
      [byte_data...] (1 byte per point)
      [word_data...] (2 bytes per point, LE)
      [long_data...] (4 bytes per point, LE)
    Returns list of values in the same order as `addresses`.
    """
    if len(payload) < 4:
        raise ToyopucError(f"Multi-read payload too short: {len(payload)} bytes")

    n_bit, n_byte, n_word, n_long = struct.unpack_from("<BBBB", payload, 0)
    offset = 4

    # 1. Parse Bit values
    bit_values = []
    num_bit_bytes = (n_bit + 7) // 8
    bit_bytes = payload[offset: offset + num_bit_bytes]
    offset += num_bit_bytes
    for i in range(n_bit):
        byte_idx = i // 8
        bit_idx = i % 8
        val = (bit_bytes[byte_idx] >> bit_idx) & 1
        bit_values.append(val)

    # 2. Parse Byte values
    byte_values = []
    for _ in range(n_byte):
        val = payload[offset]
        offset += 1
        byte_values.append(val)

    # 3. Parse Word values
    word_values = []
    for _ in range(n_word):
        val = struct.unpack_from("<H", payload, offset)[0]
        offset += 2
        word_values.append(val)

    # 4. Parse Long values
    long_values = []
    for _ in range(n_long):
        val = struct.unpack_from("<I", payload, offset)[0]
        offset += 4
        long_values.append(val)

    # Reconstruct in original order
    results = []
    bit_iter = iter(bit_values)
    byte_iter = iter(byte_values)
    word_iter = iter(word_values)
    long_iter = iter(long_values)

    for a in addresses:
        if a.data_type == DataType.BIT:
            results.append(next(bit_iter))
        elif a.data_type == DataType.BYTE:
            results.append(next(byte_iter))
        elif a.data_type == DataType.WORD:
            results.append(next(word_iter))
        elif a.data_type == DataType.LONG:
            results.append(next(long_iter))

    return results


def build_pc10_multi_write_request(items: Sequence[tuple[ParsedAddress, int]]) -> bytes:
    """
    Build PC10 Multi-point Write (CMD=0xC5) payload.
    Format:
      [bit_count(1B)] [byte_count(1B)] [word_count(1B)] [long_count(1B)]
      Bit writes:  [address(4B LE) + val(1B, bit0)] * bit_count
      Byte writes: [address(4B LE) + val(1B)] * byte_count
      Word writes: [address(4B LE) + val(2B LE)] * word_count
      Long writes: [address(4B LE) + val(4B LE)] * long_count
    """
    bit_items = [item for item in items if item[0].data_type == DataType.BIT]
    byte_items = [item for item in items if item[0].data_type == DataType.BYTE]
    word_items = [item for item in items if item[0].data_type == DataType.WORD]
    long_items = [item for item in items if item[0].data_type == DataType.LONG]

    payload = bytearray()
    payload.extend(struct.pack("<BBBB", len(bit_items), len(byte_items), len(word_items), len(long_items)))

    for addr, val in bit_items:
        payload.extend(struct.pack("<IB", addr.logical_address, 1 if val else 0))
    for addr, val in byte_items:
        payload.extend(struct.pack("<IB", addr.logical_address, val & 0xFF))
    for addr, val in word_items:
        payload.extend(struct.pack("<IH", addr.logical_address, val & 0xFFFF))
    for addr, val in long_items:
        payload.extend(struct.pack("<II", addr.logical_address, val & 0xFFFFFFFF))

    return build_frame(CMD_PC10_MULTI_WRITE, bytes(payload))
