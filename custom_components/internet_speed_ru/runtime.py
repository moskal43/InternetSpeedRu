"""Measurement orchestration and runtime state for InternetSpeedRu."""

import asyncio
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from statistics import median
from time import monotonic
from typing import Any, Protocol, TypeVar

from homeassistant.core import callback

from .const import (
    IPERF3_PORT,
    IPERF3_SERVER,
    TCP_PROBE_COUNT,
    TCP_PROBE_TIMEOUT,
)
from .iperf import InvalidIperfResultError, IperfExecutionError, run_iperf_phase

_ResultT = TypeVar("_ResultT")
type RuntimeListener = Callable[[], None]
type LatencyProbe = Callable[[str, int], Awaitable[float]]
type IperfRunner = Callable[[str, int, bool], float]


class RunBlocking(Protocol):
    """Run blocking adapter work outside the Home Assistant event loop."""

    def __call__(
        self,
        target: Callable[..., _ResultT],
        *args: Any,
    ) -> Awaitable[_ResultT]:
        """Schedule blocking work and return its eventual result."""


class MeasurementStatus(StrEnum):
    """Observable state of the latest measurement attempt."""

    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


class MeasurementErrorCode(StrEnum):
    """Stable failure reasons exposed by the first measurement slice."""

    BUSY = "busy"
    CANCELLED = "cancelled"
    DNS = "dns"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    INVALID_RESULT = "invalid_result"
    IPERF = "iperf"
    UNEXPECTED = "unexpected"


class MeasurementError(Exception):
    """A measurement failed with a normalized reason."""

    def __init__(self, code: MeasurementErrorCode) -> None:
        super().__init__(code.value)
        self.code = code


class MeasurementBusyError(MeasurementError):
    """A measurement was requested while another one was running."""

    def __init__(self) -> None:
        super().__init__(MeasurementErrorCode.BUSY)


@dataclass(frozen=True, slots=True)
class Measurement:
    """One complete, atomically published connection measurement."""

    download_mbps: float
    upload_mbps: float
    latency_ms: float
    server: str
    port: int
    measured_at: datetime


async def async_tcp_latency_probe(server: str, port: int) -> float:
    """Measure the time required to establish one TCP connection."""
    started = monotonic()
    async with asyncio.timeout(TCP_PROBE_TIMEOUT):
        _, writer = await asyncio.open_connection(server, port)
    elapsed_ms = (monotonic() - started) * 1000
    writer.close()
    await writer.wait_closed()
    return elapsed_ms


class InternetSpeedRuRuntime:
    """Dependencies and observable state owned by one config entry."""

    def __init__(
        self,
        run_blocking: RunBlocking,
        *,
        probe: LatencyProbe = async_tcp_latency_probe,
        runner: IperfRunner = run_iperf_phase,
        server: str = IPERF3_SERVER,
        port: int = IPERF3_PORT,
    ) -> None:
        self.run_blocking = run_blocking
        self.probe = probe
        self.runner = runner
        self.server = server
        self.port = port

        self.measurement: Measurement | None = None
        self.status: MeasurementStatus | None = None
        self.error: MeasurementErrorCode | None = None
        self.last_attempt: datetime | None = None
        self.last_success: datetime | None = None

        self._listeners: set[RuntimeListener] = set()
        self._running = False
        self._generation = 0
        self._unloaded = False

    @property
    def running(self) -> bool:
        """Return whether a measurement owns the single execution slot."""
        return self._running

    @callback
    def async_add_listener(self, listener: RuntimeListener) -> Callable[[], None]:
        """Subscribe an entity to runtime state changes."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def _ensure_current(self, generation: int) -> None:
        if self._unloaded or generation != self._generation:
            raise MeasurementError(MeasurementErrorCode.CANCELLED)

    async def async_measure(self) -> Measurement:
        """Run and atomically publish one complete connection measurement."""
        if self._unloaded:
            raise MeasurementError(MeasurementErrorCode.CANCELLED)
        if self._running:
            raise MeasurementBusyError

        self._running = True
        generation = self._generation
        self.status = MeasurementStatus.RUNNING
        self.error = None
        self.last_attempt = datetime.now(UTC)
        self._notify()

        try:
            latency_samples = []
            for _ in range(TCP_PROBE_COUNT):
                latency_samples.append(await self.probe(self.server, self.port))
                self._ensure_current(generation)

            download_mbps = await self.run_blocking(
                self.runner, self.server, self.port, True
            )
            self._ensure_current(generation)
            upload_mbps = await self.run_blocking(
                self.runner, self.server, self.port, False
            )
            self._ensure_current(generation)

            completed = Measurement(
                download_mbps=download_mbps,
                upload_mbps=upload_mbps,
                latency_ms=median(latency_samples),
                server=self.server,
                port=self.port,
                measured_at=datetime.now(UTC),
            )
        except MeasurementError:
            raise
        except Exception as err:
            normalized = MeasurementError(self._normalize_error(err))
            if generation == self._generation and not self._unloaded:
                self.status = MeasurementStatus.ERROR
                self.error = normalized.code
                self._notify()
            raise normalized from err
        else:
            self.measurement = completed
            self.status = MeasurementStatus.SUCCESS
            self.error = None
            self.last_success = completed.measured_at
            self._notify()
            return completed
        finally:
            if generation == self._generation:
                self._running = False

    @staticmethod
    def _normalize_error(err: Exception) -> MeasurementErrorCode:
        if isinstance(err, InvalidIperfResultError):
            return MeasurementErrorCode.INVALID_RESULT
        if isinstance(err, IperfExecutionError):
            return MeasurementErrorCode.IPERF
        if isinstance(err, TimeoutError):
            return MeasurementErrorCode.TIMEOUT
        if isinstance(err, socket.gaierror):
            return MeasurementErrorCode.DNS
        if isinstance(err, OSError):
            return MeasurementErrorCode.UNREACHABLE
        return MeasurementErrorCode.UNEXPECTED

    @callback
    def async_cancel(self) -> None:
        """Logically cancel active work and reject every late adapter result."""
        self._unloaded = True
        self._generation += 1
        self._running = False
        self._listeners.clear()
