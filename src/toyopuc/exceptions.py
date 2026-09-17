"""
Exceptions for toyopuc library.
"""

ERROR_CODES = {
    0x10: "General error response",
    0x11: "CPU module hardware error / unable to process",
    0x20: "Relay command ENQ code is not 0x05",
    0x21: "Transfer count error in relay command",
    0x23: "Invalid command code",
    0x24: "Invalid sub-command code",
    0x25: "Invalid data byte in command format",
    0x26: "Invalid number of operands for function call",
    0x31: "Writing to protected area prohibited during sequence execution",
    0x32: "Command disabled during scan stop",
    0x33: "Debug function call attempted outside debug mode",
    0x34: "Access prohibited by security/access settings",
    0x35: "Execution restricted by execution rights setting",
    0x36: "Execution restricted by another device",
    0x39: "I/O count parameter write error",
    0x3C: "Command cannot be executed during fatal fault",
    0x3D: "Command conflicting with other active operations",
    0x3E: "Command cannot be executed during CPU reset",
    0x3F: "Command cannot be executed while CPU is stopped",
    0x40: "Address out of range or address + count exceeds range",
    0x41: "Word count or byte count out of range",
    0x42: "Unexpected / out-of-specification data received",
    0x43: "Operand error in function call",
    0x52: "Timer/counter not used but read/write commanded",
    0x66: "No response from relay link module or node",
    0x70: "Relay link module is unavailable",
    0x72: "No response from relay link module or node",
    0x73: "Duplicate relay commands to same link module in CPU",
}


class ToyopucError(Exception):
    """Base exception for all Toyopuc library errors."""
    pass


class ToyopucConnectionError(ToyopucError):
    """Raised when connection to PLC fails, times out, or is lost."""
    pass


class ToyopucResponseError(ToyopucError):
    """Raised when PLC returns an error response code."""

    def __init__(self, response_code: int, error_code: int | None = None, message: str | None = None):
        self.response_code = response_code
        self.error_code = error_code
        desc = message or ERROR_CODES.get(error_code or response_code, "Unknown PLC error")
        detail = f"PLC error (RC=0x{response_code:02X}"
        if error_code is not None:
            detail += f", ErrorCode=0x{error_code:02X}"
        detail += f"): {desc}"
        super().__init__(detail)


class ToyopucAddressError(ToyopucError):
    """Raised when an address string is malformed or unsupported."""
    pass
