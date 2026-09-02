"""Connection measurement behavior tests."""

import asyncio

import pytest
from homeassistant.const import Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.internet_speed_ru import InternetSpeedRuConfigEntry
from custom_components.internet_speed_ru.const import DOMAIN
from custom_components.internet_speed_ru.runtime import (
    IperfPreTransferError,
    MeasurementBusyError,
    MeasurementError,
    MeasurementErrorCode,
)
from tests.helpers import async_configure_kirov_entry


async def _configured_entry(hass) -> InternetSpeedRuConfigEntry:
    """Create and load the integration through its public config flow."""
    return await async_configure_kirov_entry(hass)


def _button_entity_id(hass, entry: InternetSpeedRuConfigEntry) -> str:
    """Return the public run-measurement button for a loaded entry."""
    entity_id = er.async_get(hass).async_get_entity_id(
        Platform.BUTTON,
        DOMAIN,
        f"{entry.entry_id}_run_measurement",
    )
    assert entity_id is not None
    return entity_id


async def _press_run_measurement(hass, entry: InternetSpeedRuConfigEntry) -> None:
    """Trigger a measurement through the Home Assistant service seam."""
    await hass.services.async_call(
        Platform.BUTTON,
        "press",
        {"entity_id": _button_entity_id(hass, entry)},
        blocking=True,
    )


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
    await _press_run_measurement(hass, entry)

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
    await _press_run_measurement(hass, entry)
    with pytest.raises(HomeAssistantError):
        await _press_run_measurement(hass, entry)

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


async def test_last_good_port_is_preferred_before_ascending_fallbacks(hass) -> None:
    """A successful fallback port moves to the front of the next measurement."""
    entry = await _configured_entry(hass)
    runtime = entry.runtime_data
    probed_ports: list[int] = []
    reject_5201 = True

    async def probe(server: str, port: int) -> float:
        probed_ports.append(port)
        if port == 5201 and reject_5201:
            raise OSError
        return 10.0

    def runner(server: str, port: int, reverse: bool) -> float:
        return 50.0

    runtime.probe = probe
    runtime.runner = runner

    await _press_run_measurement(hass, entry)
    assert probed_ports == [5201, 5202, 5202, 5202]

    probed_ports.clear()
    reject_5201 = False
    await _press_run_measurement(hass, entry)
    assert probed_ports == [5202, 5202, 5202]


async def test_transfer_failure_does_not_retry_another_port(hass) -> None:
    """Once throughput starts, an error ends the attempt without heavy retry."""
    entry = await _configured_entry(hass)
    runtime = entry.runtime_data
    probed_ports: list[int] = []
    transfer_ports: list[int] = []

    async def probe(server: str, port: int) -> float:
        probed_ports.append(port)
        return 10.0

    def runner(server: str, port: int, reverse: bool) -> float:
        transfer_ports.append(port)
        raise OSError

    runtime.probe = probe
    runtime.runner = runner

    with pytest.raises(HomeAssistantError):
        await _press_run_measurement(hass, entry)

    assert probed_ports == [5201, 5201, 5201]
    assert transfer_ports == [5201]


async def test_control_failure_before_transfer_retries_next_port(hass) -> None:
    """A control failure before download data starts can use another port."""
    entry = await _configured_entry(hass)
    runtime = entry.runtime_data
    probed_ports: list[int] = []
    transfer_attempts: list[tuple[int, bool]] = []

    async def probe(server: str, port: int) -> float:
        probed_ports.append(port)
        return 10.0

    def runner(server: str, port: int, reverse: bool) -> float:
        transfer_attempts.append((port, reverse))
        if port == 5201:
            raise IperfPreTransferError
        return 50.0

    runtime.probe = probe
    runtime.runner = runner

    await _press_run_measurement(hass, entry)

    assert probed_ports == [5201, 5201, 5201, 5202, 5202, 5202]
    assert transfer_attempts == [(5201, True), (5202, True), (5202, False)]


async def test_manual_measurement_exhausts_only_the_selected_server(hass) -> None:
    """Manual mode reports failure instead of switching to a hidden server."""
    entry = await _configured_entry(hass)
    runtime = entry.runtime_data
    attempts: list[tuple[str, int]] = []

    async def probe(server: str, port: int) -> float:
        attempts.append((server, port))
        raise OSError

    runtime.probe = probe

    with pytest.raises(HomeAssistantError):
        await _press_run_measurement(hass, entry)

    assert attempts == [("st.kirov.ertelecom.ru", port) for port in range(5201, 5210)]


async def test_catalog_refresh_error_keeps_existing_entities_and_status(hass) -> None:
    """A background catalog failure never turns a successful measurement stale."""
    entry = await _configured_entry(hass)
    runtime = entry.runtime_data

    async def probe(server: str, port: int) -> float:
        return 12.0

    runtime.probe = probe
    runtime.runner = lambda server, port, reverse: 75.0 if reverse else 25.0
    await runtime.async_measure()

    class UnavailableCatalog:
        async def async_catalog(self):
            from custom_components.internet_speed_ru.catalog_runtime import (
                CatalogUnavailableError,
            )

            raise CatalogUnavailableError

    runtime.catalog_provider = UnavailableCatalog()
    before = {
        state.entity_id: (state.state, dict(state.attributes))
        for state in hass.states.async_all()
        if state.entity_id.startswith("sensor.internet_speed_ru")
    }

    await runtime.async_refresh_catalog()

    after = {
        state.entity_id: (state.state, dict(state.attributes))
        for state in hass.states.async_all()
        if state.entity_id.startswith("sensor.internet_speed_ru")
    }
    assert after == before
