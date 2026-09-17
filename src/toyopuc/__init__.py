"""
TOYOPUC 10GX PLC Communication Library.
"""

from toyopuc.client import ToyopucClient
from toyopuc.exceptions import (
    ToyopucAddressError,
    ToyopucConnectionError,
    ToyopucError,
    ToyopucResponseError,
)
from toyopuc.poller import BackgroundPoller

__version__ = "0.1.0"


def connect(
    ip: str,
    port: int = 1025,
    timeout: float = 3.0,
    auto_reconnect: bool = True,
) -> ToyopucClient:
    """
    Connect to a TOYOPUC 10GX PLC via Ethernet Computer Link.

    Args:
        ip: Target PLC IP address (e.g. '192.168.1.1').
        port: TCP port number (default: 1025).
        timeout: Socket communication timeout in seconds (default: 3.0).
        auto_reconnect: Whether to automatically reconnect on connection loss (default: True).

    Returns:
        ToyopucClient connected to the target PLC.
    """
    client = ToyopucClient(host=ip, port=port, timeout=timeout, auto_reconnect=auto_reconnect)
    return client.connect()


__all__ = [
    "connect",
    "ToyopucClient",
    "BackgroundPoller",
    "ToyopucError",
    "ToyopucConnectionError",
    "ToyopucResponseError",
    "ToyopucAddressError",
    "__version__",
]
