"""Measurement orchestration and runtime state for InternetSpeedRu."""

import asyncio
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from statistics import median
from time import monotonic
from typing import TYPE_CHECKING, Any, Protocol, TypeVar

from homeassistant.core import callback

from .catalog import FALLBACK_CATALOG, CatalogServer, ordered_ports
from .catalog_runtime import CatalogProviderProtocol, CatalogUnavailableError
from .const import (
    TCP_PROBE_COUNT,
    TCP_PROBE_TIMEOUT,
)
from .iperf import (
    InvalidIperfResultError,
    IperfExecutionError,
    IperfPreTransferError,
    run_iperf_phase,
)

if TYPE_CHECKING:
    from .scheduling import ClockScheduler, MeasurementSchedule

_ResultT = TypeVar("_ResultT")
type RuntimeListener = Callable[[], None]
type LatencyProbe = Callable[[str, int], Awaitable[float]]
type IperfRunner = Callable[[str, int, bool], float]
type Now = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    server_city: str
    server_provider: str
    port: int
    measured_at: datetime


@dataclass(frozen=True, slots=True)
class PersistedRuntimeState:
    """The bounded runtime state restored after a restart."""

    measurement: Measurement | None
    schedule_baseline: datetime | None
    last_attempt: datetime | None
    last_success: datetime | None
    status: MeasurementStatus | None
    error: MeasurementErrorCode | None


class RuntimeStateStore(Protocol):
    """Persist the latest runtime state for one config entry."""

    async def async_load(self) -> PersistedRuntimeState | None:
        """Load the latest compatible runtime state."""

    async def async_save(self, state: PersistedRuntimeState) -> None:
        """Replace the stored runtime state."""


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
        catalog_server: CatalogServer | None = None,
        configured_hostname: str | None = None,
        catalog_provider: CatalogProviderProtocol | None = None,
        state_store: RuntimeStateStore | None = None,
        now: Now = _utcnow,
    ) -> None:
        self.run_blocking = run_blocking
        self.probe = probe
        self.runner = runner
        if catalog_server is None and configured_hostname is None:
            catalog_server = FALLBACK_CATALOG.get("st.kirov.ertelecom.ru")
        self._selected_server = catalog_server
        self._configured_hostname = (
            catalog_server.hostname
            if catalog_server is not None
            else configured_hostname or ""
        )
        self.catalog_provider = catalog_provider
        self.port = self._selected_server.ports[0] if self._selected_server else 0
        self._last_good_ports: dict[str, int] = {}
        self._state_store = state_store
        self._now = now
        self._schedule: MeasurementSchedule | None = None

        self.measurement: Measurement | None = None
        self.schedule_baseline: datetime | None = None
        self.status: MeasurementStatus | None = None
        self.error: MeasurementErrorCode | None = None
        self.last_attempt: datetime | None = None
        self.last_success: datetime | None = None

        self._listeners: set[RuntimeListener] = set()
        self._running = False
        self._generation = 0
        self._unloaded = False

    async def async_restore(self) -> None:
        """Restore persisted values without performing network work."""
        if self._state_store is None:
            return
        state = await self._state_store.async_load()
        if state is None:
            return
        self.measurement = state.measurement
        self.schedule_baseline = state.schedule_baseline
        self.last_attempt = state.last_attempt
        self.last_success = state.last_success
        self.status = state.status
        self.error = state.error
        if state.measurement is not None:
            self._last_good_ports[state.measurement.server] = state.measurement.port
            if state.measurement.server == self.server:
                self.port = state.measurement.port

    async def _async_persist(self) -> None:
        if self._state_store is None:
            return
        await self._state_store.async_save(
            PersistedRuntimeState(
                measurement=self.measurement,
                schedule_baseline=self.schedule_baseline,
                last_attempt=self.last_attempt,
                last_success=self.last_success,
                status=self.status,
                error=self.error,
            )
        )

    async def async_set_schedule_baseline(self, baseline: datetime) -> None:
        """Persist the anchor for the next ordinary automatic attempt."""
        self.schedule_baseline = baseline
        await self._async_persist()

    def start_schedule(self, clock: ClockScheduler, interval: str) -> None:
        """Start automatic scheduling after the config entry is loaded."""
        from .scheduling import MeasurementSchedule

        self._schedule = MeasurementSchedule(self, clock, interval)
        self._schedule.start()

    def update_interval(self, interval: str) -> None:
        """Recalculate the automatic schedule for a changed preset."""
        if self._schedule is not None:
            self._schedule.update_interval(interval)

    @property
    def interval(self) -> str | None:
        """Return the active schedule preset."""
        return self._schedule.interval if self._schedule is not None else None

    @property
    def running(self) -> bool:
        """Return whether a measurement owns the single execution slot."""
        return self._running

    @property
    def server(self) -> str:
        """Return the currently selected manual server hostname."""
        return self._configured_hostname

    @property
    def server_city(self) -> str:
        """Return the city of the currently selected server."""
        if self._selected_server is not None:
            return self._selected_server.city
        if self.measurement is not None and self.measurement.server == self.server:
            return self.measurement.server_city
        return ""

    @property
    def server_provider(self) -> str:
        """Return the provider of the currently selected server."""
        if self._selected_server is not None:
            return self._selected_server.provider
        if self.measurement is not None and self.measurement.server == self.server:
            return self.measurement.server_provider
        return ""

    @callback
    def select_server(self, server: CatalogServer) -> None:
        """Change the server used by future measurements without queueing work."""
        self._selected_server = server
        self._configured_hostname = server.hostname
        self.port = self._last_good_ports.get(server.hostname, server.ports[0])

    async def async_select_server(self, hostname: str) -> None:
        """Select a hostname from the active validated runtime catalog."""
        if self.catalog_provider is None:
            self.select_server(FALLBACK_CATALOG.get(hostname))
            return
        selection = await self.catalog_provider.async_catalog()
        self.select_server(selection.catalog.get(hostname))

    async def async_refresh_catalog(self) -> None:
        """Refresh catalog metadata without changing observable measurement state."""
        if self.catalog_provider is None:
            return
        try:
            selection = await self.catalog_provider.async_catalog()
            server = selection.catalog.get(self.server)
        except CatalogUnavailableError, KeyError:
            return
        self.select_server(server)

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

        if self._selected_server is None:
            unavailable = MeasurementError(MeasurementErrorCode.UNREACHABLE)
            self.last_attempt = self._now()
            self.status = MeasurementStatus.ERROR
            self.error = unavailable.code
            self._notify()
            await self._async_persist()
            raise unavailable

        self._running = True
        generation = self._generation
        selected_server = self._selected_server
        self.status = MeasurementStatus.RUNNING
        self.error = None
        self.last_attempt = self._now()
        self._notify()
        await self._async_persist()

        try:
            latency_samples: list[float] | None = None
            last_port_error: Exception | None = None
            selected_port: int | None = None
            download_mbps: float | None = None
            upload_mbps: float | None = None
            for candidate_port in ordered_ports(
                selected_server,
                self._last_good_ports.get(selected_server.hostname),
            ):
                self.port = candidate_port
                try:
                    samples = []
                    for _ in range(TCP_PROBE_COUNT):
                        samples.append(
                            await self.probe(selected_server.hostname, candidate_port)
                        )
                        self._ensure_current(generation)
                except MeasurementError:
                    raise
                except Exception as err:
                    last_port_error = err
                    continue

                try:
                    download_mbps = await self.run_blocking(
                        self.runner,
                        selected_server.hostname,
                        candidate_port,
                        True,
                    )
                    self._ensure_current(generation)
                except IperfPreTransferError as err:
                    last_port_error = err
                    continue

                upload_mbps = await self.run_blocking(
                    self.runner,
                    selected_server.hostname,
                    candidate_port,
                    False,
                )
                self._ensure_current(generation)
                latency_samples = samples
                selected_port = candidate_port
                break

            if (
                latency_samples is None
                or selected_port is None
                or download_mbps is None
                or upload_mbps is None
            ):
                assert last_port_error is not None
                raise last_port_error

            completed = Measurement(
                download_mbps=download_mbps,
                upload_mbps=upload_mbps,
                latency_ms=median(latency_samples),
                server=selected_server.hostname,
                server_city=selected_server.city,
                server_provider=selected_server.provider,
                port=selected_port,
                measured_at=self._now(),
            )
        except MeasurementError:
            raise
        except Exception as err:
            normalized = MeasurementError(self._normalize_error(err))
            if generation == self._generation and not self._unloaded:
                self.status = MeasurementStatus.ERROR
                self.error = normalized.code
                self._notify()
                await self._async_persist()
            raise normalized from err
        else:
            self._last_good_ports[completed.server] = completed.port
            self.port = completed.port
            self.measurement = completed
            self.status = MeasurementStatus.SUCCESS
            self.error = None
            self.last_success = completed.measured_at
            self.schedule_baseline = completed.measured_at
            self._notify()
            await self._async_persist()
            if self._schedule is not None:
                self._schedule.recalculate()
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
        if self._schedule is not None:
            self._schedule.cancel()
        self._generation += 1
        self._running = False
        self._listeners.clear()
