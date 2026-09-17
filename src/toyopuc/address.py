"""
Address parsing and 32-bit logical address resolution for TOYOPUC 10GX.
Based on JTEKT TOYOPUC-Nano 2ET Manual, Section 3.4.2 & Document 8.
"""

from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum, auto
from toyopuc.exceptions import ToyopucAddressError


class DataType(Enum):
    BIT = auto()
    BYTE = auto()
    WORD = auto()
    LONG = auto()


@dataclass(frozen=True)
class ParsedAddress:
    raw: str
    program_no: int | None  # 1, 2, 3, or None
    device: str            # e.g. 'M', 'D', 'K', 'U', etc.
    index: int             # Numerical address index (hex in TOYOPUC convention)
    byte_part: str | None  # 'L' (low byte), 'H' (high byte), or None
    data_type: DataType    # BIT, BYTE, WORD, or LONG
    logical_address: int   # 32-bit address for PC10 commands (0xC4/0xC5)


# Program Ex No. mapping (Document 8)
EX_NO_PRG = {
    1: 0x0D,
    2: 0x0E,
    3: 0x0F,
}

# Bit device prefixes in P1/P2/P3 basic & PC10 extension
# Format: (device, start_idx, end_idx, base_byte, is_pc10_ext)
BIT_DEVICES = {
    'P': [
        (0x000, 0x1FF, 0x0000, False),    # Edge P000-1FF
        (0x1000, 0x17FF, 0xC000, True),   # Ext Edge P1000-17FF
    ],
    'K': [
        (0x000, 0x2FF, 0x0040, False),    # Keep relay K000-2FF
    ],
    'V': [
        (0x000, 0x0FF, 0x00A0, False),    # Special relay V000-0FF
        (0x1000, 0x17FF, 0xC100, True),   # Ext special relay V1000-17FF
    ],
    'TC': [
        (0x000, 0x1FF, 0x00C0, False),    # Timer/Counter contact TC000-1FF
        (0x1000, 0x17FF, 0xC200, True),   # Ext timer/counter contact TC1000-17FF
    ],
    'T': [
        (0x000, 0x1FF, 0x00C0, False),
        (0x1000, 0x17FF, 0xC200, True),
    ],
    'C': [
        (0x000, 0x1FF, 0x00C0, False),
        (0x1000, 0x17FF, 0xC200, True),
    ],
    'L': [
        (0x000, 0x7FF, 0x0100, False),    # Link relay L000-7FF
        (0x1000, 0x2FFF, 0xC400, True),   # Ext link relay L1000-2FFF
    ],
    'X': [
        (0x000, 0x7FF, 0x0200, False),    # Input relay X000-7FF
    ],
    'Y': [
        (0x000, 0x7FF, 0x0280, False),    # Output relay Y000-7FF
    ],
    'M': [
        (0x000, 0x7FF, 0x0300, False),    # Internal relay M000-7FF
        (0x1000, 0x17FF, 0xC300, True),   # Ext internal relay M1000-17FF
    ],
}

# Extended bit devices (Ex No = 0x01)
EXT_BIT_DEVICES_1 = {
    'EP': (0x000, 0xFFF, 0x0000),         # Ext Edge EP000-FFF
    'EK': (0x000, 0xFFF, 0x0200),         # Ext Keep Relay EK000-FFF
    'EV': (0x000, 0xFFF, 0x0400),         # Ext Special Relay EV000-FFF
    'ETC': (0x000, 0x7FF, 0x0600),        # Ext Timer/Counter contact
    'ET': (0x000, 0x7FF, 0x0600),
    'EC': (0x000, 0x7FF, 0x0600),
    'EL': (0x0000, 0x1FFF, 0x0700),       # Ext Link Relay EL0000-1FFF
    'EX': (0x000, 0x7FF, 0x0B00),         # Ext Input EX000-7FF
    'EY': (0x000, 0x7FF, 0x0B80),         # Ext Output EY000-7FF
    'EM': (0x0000, 0x1FFF, 0x0C00),       # Ext Internal Relay EM0000-1FFF
}

# Extended bit devices (Ex No = 0x02)
EXT_BIT_DEVICES_2 = {
    'GX': (0x0000, 0xFFFF, 0xC000),       # GXY0000-FFFF
    'GY': (0x0000, 0xFFFF, 0xC800),
    'GM': (0x0000, 0xFFFF, 0xE000),       # GM0000-FFFF
}

# Word devices in P1/P2/P3 basic & PC10 extension
# Format: (device, start_idx, end_idx, base_byte)
WORD_DEVICES = {
    'S': [
        (0x0000, 0x03FF, 0x0400),         # Special register S0000-03FF
        (0x1000, 0x13FF, 0xC800),         # Ext special register S1000-13FF
    ],
    'N': [
        (0x0000, 0x01FF, 0x0C00),         # Current value register N0000-01FF
        (0x1000, 0x17FF, 0xD000),         # Ext current value register N1000-17FF
    ],
    'R': [
        (0x0000, 0x07FF, 0x1000),         # Link register R0000-07FF
    ],
    'D': [
        (0x0000, 0x0FFF, 0x2000),         # Data register 1 D0000-0FFF (byte 0x2000-0x3FFF)
        (0x1000, 0x2FFF, 0x4000),         # Data register 2 D1000-2FFF (byte 0x4000-0x7FFF)
    ],
    'B': [
        (0x0000, 0x1FFF, 0xC000),         # File register B0000-1FFF (byte 0xC000-0xFFFF)
    ],
}

# Extended word devices (Ex No = 0x01)
EXT_WORD_DEVICES_1 = {
    'ES': (0x000, 0x07FF, 0x1000),        # Ext special register ES000-07FF
    'EN': (0x0000, 0x07FF, 0x2000),       # Ext current value register EN0000-07FF
    'H': (0x0000, 0x07FF, 0x3000),        # Ext preset value register H0000-07FF
}


ADDR_REGEX = re.compile(
    r'^(?:P(?P<prg>[1-3])-)?(?P<dev>[A-Z]{1,3})(?P<idx>[0-9A-Fa-f]+)(?P<part>[LH])?$',
    re.IGNORECASE
)


def parse_address(addr_str: str, default_data_type: DataType = DataType.WORD) -> ParsedAddress:
    """
    Parse an address string (e.g. 'P1-M100', 'P2-D2000L', 'D100')
    and calculate its 32-bit logical address for PC10 commands.
    """
    raw = addr_str.strip()
    match = ADDR_REGEX.match(raw)
    if not match:
        raise ToyopucAddressError(f"Invalid address format: '{raw}'")

    prg_str = match.group('prg')
    dev = match.group('dev').upper()
    idx_str = match.group('idx')
    part = match.group('part').upper() if match.group('part') else None

    prg_no = int(prg_str) if prg_str else 1  # Default to Program 1
    idx = int(idx_str, 16)  # TOYOPUC addresses are hexadecimal

    # Determine requested data type
    if part in ('L', 'H'):
        actual_type = DataType.BYTE
    elif default_data_type == DataType.BIT:
        actual_type = DataType.BIT
    elif default_data_type == DataType.BYTE:
        actual_type = DataType.BYTE
    elif default_data_type == DataType.LONG:
        actual_type = DataType.LONG
    else:
        # Check if device is inherently a bit device
        if dev in BIT_DEVICES or dev in EXT_BIT_DEVICES_1 or dev in EXT_BIT_DEVICES_2:
            actual_type = DataType.BIT
        else:
            actual_type = DataType.WORD

    logical_addr = _calculate_logical_address(prg_no, dev, idx, part, actual_type)

    return ParsedAddress(
        raw=raw,
        program_no=prg_no if prg_str else None,
        device=dev,
        index=idx,
        byte_part=part,
        data_type=actual_type,
        logical_address=logical_addr
    )


def _calculate_logical_address(prg_no: int, dev: str, idx: int, part: str | None, data_type: DataType) -> int:
    # 1. Check U (Extended Data Register)
    if dev == 'U':
        block = idx // 0x8000
        offset = (idx % 0x8000) * 2
        if part == 'H':
            offset += 1
        ex_no = 0x03 + block
        if ex_no > 0x06:
            raise ToyopucAddressError(f"U register address out of range: U{idx:X}")
        return (ex_no << 16) | (offset & 0xFFFF)

    # 2. Check EB (Extended Buffer Register)
    if dev == 'EB':
        block = idx // 0x8000
        offset = (idx % 0x8000) * 2
        if part == 'H':
            offset += 1
        ex_no = 0x10 + block
        if ex_no > 0x17:
            raise ToyopucAddressError(f"EB register address out of range: EB{idx:X}")
        return (ex_no << 16) | (offset & 0xFFFF)

    # 3. Check Extended devices Group 1 (Ex No = 0x01)
    if dev in EXT_BIT_DEVICES_1:
        start, end, base_byte = EXT_BIT_DEVICES_1[dev]
        if not (start <= idx <= end):
            raise ToyopucAddressError(f"Address out of range for {dev}: {idx:X} (expected {start:X}-{end:X})")
        ex_no = 0x01
        if data_type == DataType.BIT:
            bit_addr = (base_byte * 8) + (idx - start)
            return (ex_no << 19) | (bit_addr & 0x7FFFF)
        else:
            byte_addr = base_byte + ((idx - start) // 8)
            return (ex_no << 16) | (byte_addr & 0xFFFF)

    if dev in EXT_WORD_DEVICES_1:
        start, end, base_byte = EXT_WORD_DEVICES_1[dev]
        if not (start <= idx <= end):
            raise ToyopucAddressError(f"Address out of range for {dev}: {idx:X} (expected {start:X}-{end:X})")
        ex_no = 0x01
        byte_addr = base_byte + (idx - start) * 2
        if part == 'H':
            byte_addr += 1
        return (ex_no << 16) | (byte_addr & 0xFFFF)

    # 4. Check Extended devices Group 2 (Ex No = 0x02)
    if dev in EXT_BIT_DEVICES_2:
        start, end, base_byte = EXT_BIT_DEVICES_2[dev]
        if not (start <= idx <= end):
            raise ToyopucAddressError(f"Address out of range for {dev}: {idx:X}")
        ex_no = 0x02
        if data_type == DataType.BIT:
            bit_addr = (base_byte * 8) + (idx - start)
            return (ex_no << 19) | (bit_addr & 0x7FFFF)
        else:
            byte_addr = base_byte + ((idx - start) // 8)
            return (ex_no << 16) | (byte_addr & 0xFFFF)

    # 5. Program-dependent devices (P1, P2, P3 -> Ex No 0x0D, 0x0E, 0x0F)
    if prg_no not in EX_NO_PRG:
        raise ToyopucAddressError(f"Invalid program number: P{prg_no}")
    ex_no = EX_NO_PRG[prg_no]

    # Check Bit Devices (M, K, V, L, X, Y, T, C, P)
    if dev in BIT_DEVICES:
        ranges = BIT_DEVICES[dev]
        for start, end, base_byte, is_pc10_ext in ranges:
            if start <= idx <= end:
                if data_type == DataType.BIT:
                    bit_addr = (base_byte * 8) + (idx - start)
                    return (ex_no << 19) | (bit_addr & 0x7FFFF)
                else:
                    byte_addr = base_byte + ((idx - start) // 8)
                    return (ex_no << 16) | (byte_addr & 0xFFFF)
        raise ToyopucAddressError(f"Address index out of range for {dev}: {idx:X}")

    # Check Word Devices (D, R, S, N, B)
    if dev in WORD_DEVICES:
        ranges = WORD_DEVICES[dev]
        for start, end, base_byte in ranges:
            if start <= idx <= end:
                byte_addr = base_byte + (idx - start) * 2
                if part == 'H':
                    byte_addr += 1
                return (ex_no << 16) | (byte_addr & 0xFFFF)
        raise ToyopucAddressError(f"Address index out of range for {dev}: {idx:X}")

    raise ToyopucAddressError(f"Unsupported device type: '{dev}'")
