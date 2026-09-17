"""
Background periodic poller for TOYOPUC 10GX.
Periodically fetches data from PLC in a background thread and keeps a local cache.
"""

from __future__ import annotations
import threading
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from toyopuc.client import ToyopucClient


class BackgroundPoller:
    """
    Periodically reads specified PLC addresses in a background thread.
    Allows the main thread to query the latest values without blocking.
    """

    def __init__(
        self,
        client: ToyopucClient,
        addresses: Sequence[str],
        interval: float = 1.0,
    ):
        self.client = client
        self._addresses = list(addresses)
        self.interval = max(0.001, float(interval))

        self._cache: dict[str, int] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error: Exception | None = None

    @property
    def addresses(self) -> list[str]:
        """Get the current list of polled addresses."""
        with self._lock:
            return list(self._addresses)

    def set_addresses(self, addresses: Sequence[str]) -> None:
        """Update the list of polled addresses while running."""
        with self._lock:
            self._addresses = list(addresses)

    def set_interval(self, interval: float) -> None:
        """Update the polling interval in seconds."""
        self.interval = max(0.001, float(interval))

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ToyopucPollerThread")
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        """Stop the background polling thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def get(self, address: str, default: Any = None) -> int | None:
        """Get the latest cached value for an address without blocking."""
        with self._lock:
            return self._cache.get(address, default)

    def get_latest(self) -> dict[str, int]:
        """Get a copy of all latest cached data."""
        with self._lock:
            return dict(self._cache)

    @property
    def is_running(self) -> bool:
        """Check if background thread is actively running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> Exception | None:
        """Get the last encountered exception, if any."""
        return self._last_error

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    addrs_to_read = list(self._addresses)

                if addrs_to_read:
                    results = self.client.read_mixed(addrs_to_read)
                    with self._lock:
                        self._cache.update(results)
                    self._last_error = None
            except Exception as e:
                self._last_error = e

            # Wait for interval or stop event
            self._stop_event.wait(self.interval)
