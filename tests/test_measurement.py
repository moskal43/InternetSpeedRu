"""Connection measurement behavior tests."""

import asyncio

import pytest
from homeassistant import config_entries
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.internet_speed_ru import InternetSpeedRuConfigEntry
from custom_components.internet_speed_ru.const import DOMAIN
from custom_components.internet_speed_ru.runtime import (
    MeasurementBusyError,
    MeasurementError,
    MeasurementErrorCode,
)


async def _configured_entry(hass) -> InternetSpeedRuConfigEntry:
    """Create and load the integration through its public config flow."""
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    await hass.async_block_till_done()
    return result["result"]


async def test_manual_measurement_publishes_five_entities_atomically(hass) -> None:
    """A button press publishes one complete measurement from fake boundaries."""
    entry = await _configured_entry(hass)
    runtime = entry.runtime_data
    latency_samples = iter((30.0, 10.0, 20.0))
    directions: list[bool] = []

    async def probe(server: str, port: int) -> float:
        return next(latency_samples)

    def runner(server: str, port: int, reverse: bool) -> float:
        directions.append(reverse)
        return 75.0 if reverse else 25.0

    runtime.probe = probe
    runtime.runner = runner

    registry = er.async_get(hass)
    button_entity_id = registry.async_get_entity_id(
        Platform.BUTTON,
        DOMAIN,
        f"{entry.entry_id}_run_measurement",
    )
    assert button_entity_id is not None

    await hass.services.async_call(
        Platform.BUTTON,
        "press",
        {"entity_id": button_entity_id},
        blocking=True,
    )

    states = {
        key: hass.states.get(
            registry.async_get_entity_id(
                Platform.SENSOR,
                DOMAIN,
                f"{entry.entry_id}_{key}",
            )
        ).state
        for key in ("download", "upload", "latency", "status")
    }
    assert states == {
        "download": "75.0",
        "upload": "25.0",
        "latency": "20.0",
        "status": "success",
    }
    assert directions == [True, False]


async def test_partial_failure_keeps_last_complete_measurement(hass) -> None:
    """A failed upload never mixes new partial data into published entities."""
    entry = await _configured_entry(hass)
    runtime = entry.runtime_data

    async def probe(server: str, port: int) -> float:
        return 12.0

    outcomes: list[float | Exception] = [75.0, 25.0, 90.0, OSError()]

    def runner(server: str, port: int, reverse: bool) -> float:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    runtime.probe = probe
    runtime.runner = runner
    registry = er.async_get(hass)
    button_entity_id = registry.async_get_entity_id(
        Platform.BUTTON,
        DOMAIN,
        f"{entry.entry_id}_run_measurement",
    )
    assert button_entity_id is not None

    await hass.services.async_call(
        Platform.BUTTON,
        "press",
        {"entity_id": button_entity_id},
        blocking=True,
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            Platform.BUTTON,
            "press",
            {"entity_id": button_entity_id},
            blocking=True,
        )

    states = {
        key: hass.states.get(
            registry.async_get_entity_id(
                Platform.SENSOR,
                DOMAIN,
                f"{entry.entry_id}_{key}",
            )
        ).state
        for key in ("download", "upload", "latency", "status")
    }
    assert states == {
        "download": "75.0",
        "upload": "25.0",
        "latency": "12.0",
        "status": "error",
    }


async def test_repeated_manual_measurement_returns_busy_without_queueing(hass) -> None:
    """A second request fails immediately while the first keeps its slot."""
    entry = await _configured_entry(hass)
    runtime = entry.runtime_data
    started = asyncio.Event()
    release = asyncio.Event()

    async def probe(server: str, port: int) -> float:
        started.set()
        await release.wait()
        return 10.0

    def runner(server: str, port: int, reverse: bool) -> float:
        return 50.0

    runtime.probe = probe
    runtime.runner = runner

    active_measurement = asyncio.create_task(runtime.async_measure())
    await started.wait()

    with pytest.raises(MeasurementBusyError):
        await runtime.async_measure()

    release.set()
    await active_measurement


async def test_unload_rejects_a_late_blocking_adapter_result(hass) -> None:
    """An executor result arriving after unload is never published."""
    entry = await _configured_entry(hass)
    runtime = entry.runtime_data
    adapter_started = asyncio.Event()
    adapter_release = asyncio.Event()

    async def probe(server: str, port: int) -> float:
        return 10.0

    def runner(server: str, port: int, reverse: bool) -> float:
        return 50.0

    async def run_blocking(target, *args):
        adapter_started.set()
        await adapter_release.wait()
        return target(*args)

    runtime.probe = probe
    runtime.runner = runner
    runtime.run_blocking = run_blocking

    active_measurement = asyncio.create_task(runtime.async_measure())
    await adapter_started.wait()
    assert await hass.config_entries.async_unload(entry.entry_id)

    adapter_release.set()
    with pytest.raises(MeasurementError) as error:
        await active_measurement

    assert error.value.code is MeasurementErrorCode.CANCELLED
    assert runtime.measurement is None
