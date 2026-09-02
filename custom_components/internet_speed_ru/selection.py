"""Latency-based automatic server selection."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from statistics import median

from .catalog import CatalogServer, ServerCatalog
from .const import (
    AUTO_CANDIDATE_COUNT,
    AUTO_PROBE_CONCURRENCY,
    TCP_PROBE_COUNT,
)

type LatencyProbe = Callable[[str, int], Awaitable[float]]


class AutoSelectionUnavailableError(Exception):
    """Raised when no catalog server produces a stable latency sample."""


@dataclass(frozen=True, slots=True)
class SelectedServer:
    """The server and port selected by measured TCP latency."""

    server: CatalogServer
    port: int
    latency_ms: float


class AutoServerSelector:
    """Rank catalog servers through a bounded TCP-probe fan-out."""

    def __init__(
        self,
        probe: LatencyProbe,
        *,
        concurrency: int = AUTO_PROBE_CONCURRENCY,
        candidate_count: int = AUTO_CANDIDATE_COUNT,
    ) -> None:
        self._probe = probe
        self._semaphore = asyncio.Semaphore(concurrency)
        self._candidate_count = candidate_count

    async def _async_probe(self, server: CatalogServer, port: int) -> float:
        async with self._semaphore:
            return await self._probe(server.hostname, port)

    async def _async_find_responsive_port(
        self, server: CatalogServer
    ) -> tuple[CatalogServer, int, float] | None:
        for port in server.ports:
            try:
                return server, port, await self._async_probe(server, port)
            except Exception:
                continue
        return None

    async def _async_sample_candidate(
        self,
        candidate: tuple[CatalogServer, int, float],
    ) -> SelectedServer | None:
        server, port, first_sample = candidate
        samples = [first_sample]
        try:
            for _ in range(TCP_PROBE_COUNT - 1):
                samples.append(await self._async_probe(server, port))
        except Exception:
            return None
        return SelectedServer(server, port, median(samples))

    async def async_select(self, catalog: ServerCatalog) -> SelectedServer:
        """Return the responsive server with the lowest stable median latency."""
        responsive = tuple(
            result
            for result in await asyncio.gather(
                *(
                    self._async_find_responsive_port(server)
                    for server in catalog.servers
                )
            )
            if result is not None
        )
        candidates = sorted(
            responsive,
            key=lambda result: (result[2], result[0].hostname, result[1]),
        )[: self._candidate_count]
        sampled = tuple(
            result
            for result in await asyncio.gather(
                *(self._async_sample_candidate(candidate) for candidate in candidates)
            )
            if result is not None
        )
        if not sampled:
            raise AutoSelectionUnavailableError
        return min(
            sampled,
            key=lambda result: (
                result.latency_ms,
                result.server.hostname,
                result.port,
            ),
        )
