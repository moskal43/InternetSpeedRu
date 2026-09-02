"""Automatic catalog-server selection behavior."""

import asyncio

from custom_components.internet_speed_ru.catalog import CatalogServer, ServerCatalog
from custom_components.internet_speed_ru.selection import AutoServerSelector


async def test_auto_selects_lowest_stable_median_with_bounded_tcp_probes() -> None:
    """Slow, unstable, and unreachable servers cannot defeat a stable winner."""
    catalog = ServerCatalog(
        (
            CatalogServer("A", "Net", "fast.example.net", (5201,)),
            CatalogServer("B", "Net", "slow.example.net", (5201,)),
            CatalogServer("C", "Net", "unstable.example.net", (5201,)),
            CatalogServer("D", "Net", "unreachable.example.net", (5201,)),
        )
    )
    samples: dict[str, list[float | Exception]] = {
        "fast.example.net": [8.0, 7.0, 9.0],
        "slow.example.net": [50.0, 49.0, 51.0],
        "unstable.example.net": [5.0, OSError("dropped")],
        "unreachable.example.net": [OSError("offline")],
    }
    active = 0
    maximum_active = 0

    async def probe(server: str, port: int) -> float:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1
        result = samples[server].pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    selected = await AutoServerSelector(
        probe,
        concurrency=2,
        candidate_count=3,
    ).async_select(catalog)

    assert selected.server.hostname == "fast.example.net"
    assert selected.port == 5201
    assert selected.latency_ms == 8.0
    assert maximum_active == 2
