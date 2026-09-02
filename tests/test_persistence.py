"""Persistent runtime-state behavior tests."""

import pytest
from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from custom_components.internet_speed_ru import InternetSpeedRuConfigEntry
from custom_components.internet_speed_ru.const import DOMAIN
from custom_components.internet_speed_ru.runtime import MeasurementError
from custom_components.internet_speed_ru.storage import (
    STORAGE_VERSION,
    runtime_storage_key,
)
from tests.helpers import async_configure_kirov_entry


def _sensor_entity_id(hass, entry: InternetSpeedRuConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        Platform.SENSOR,
        DOMAIN,
        f"{entry.entry_id}_{key}",
    )
    assert entity_id is not None
    return entity_id


async def _measure_successfully(entry: InternetSpeedRuConfigEntry) -> None:
    async def probe(server: str, port: int) -> float:
        return 12.0

    entry.runtime_data.probe = probe
    entry.runtime_data.runner = lambda server, port, reverse: 75.0 if reverse else 25.0
    await entry.runtime_data.async_measure()


async def test_complete_snapshot_is_restored_before_network_after_reload(hass) -> None:
    """Reload immediately restores the full prior snapshot and its context."""
    entry = await async_configure_kirov_entry(hass)
    await _measure_successfully(entry)

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    states = {
        key: hass.states.get(_sensor_entity_id(hass, entry, key))
        for key in ("download", "upload", "latency", "status")
    }
    assert all(state is not None for state in states.values())
    assert {key: state.state for key, state in states.items()} == {
        "download": "75.0",
        "upload": "25.0",
        "latency": "12.0",
        "status": "success",
    }
    assert states["status"].attributes["server"] == "st.kirov.ertelecom.ru"
    assert states["status"].attributes["city"] == "Киров"
    assert states["status"].attributes["provider"] == "ЭР-Телеком"
    assert states["status"].attributes["port"] == 5201
    assert entry.runtime_data.last_attempt is not None
    assert entry.runtime_data.last_success is not None
    assert entry.runtime_data.schedule_baseline == entry.runtime_data.last_success


async def test_failed_attempt_keeps_snapshot_across_reload(hass) -> None:
    """A later error persists independently without erasing successful values."""
    entry = await async_configure_kirov_entry(hass)
    await _measure_successfully(entry)

    async def unavailable(server: str, port: int) -> float:
        raise OSError

    entry.runtime_data.probe = unavailable
    with pytest.raises(MeasurementError):
        await entry.runtime_data.async_measure()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    states = {
        key: hass.states.get(_sensor_entity_id(hass, entry, key))
        for key in ("download", "upload", "latency", "status")
    }
    assert all(state is not None for state in states.values())
    assert {key: state.state for key, state in states.items()} == {
        "download": "75.0",
        "upload": "25.0",
        "latency": "12.0",
        "status": "error",
    }
    assert states["status"].attributes["error"] == "unreachable"


async def test_entity_identity_stays_stable_when_server_changes(hass) -> None:
    """Changing the selected server preserves every existing entity identity."""
    entry = await async_configure_kirov_entry(hass)
    registry = er.async_get(hass)

    async def probe(server: str, port: int) -> float:
        return 8.0

    entry.runtime_data.probe = probe
    entry.runtime_data.runner = lambda server, port, reverse: 50.0
    before = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    hass.config_entries.async_update_entry(
        entry,
        options={"server": "spd-rudp.hostkey.ru"},
    )
    await hass.async_block_till_done()
    after = {
        item.unique_id: item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }

    assert after == before
    assert len(after) == 5
    assert all(
        value not in " ".join(after)
        for value in ("Москва", "HOSTKEY", "spd-rudp.hostkey.ru", "5201")
    )
    status = hass.states.get(_sensor_entity_id(hass, entry, "status"))
    assert status is not None
    assert status.attributes["server"] == "spd-rudp.hostkey.ru"
    assert status.attributes["city"] == "Москва"
    assert status.attributes["provider"] == "HOSTKEY"


@pytest.mark.parametrize("stored_version", [STORAGE_VERSION, STORAGE_VERSION + 1])
async def test_invalid_stored_state_does_not_block_config_entry(
    hass, stored_version: int
) -> None:
    """Malformed or incompatible persisted data is ignored safely on startup."""
    entry = await async_configure_kirov_entry(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    store: Store[dict[str, object]] = Store(
        hass,
        stored_version,
        runtime_storage_key(entry.entry_id),
    )
    await store.async_save({"measurement": {"download_mbps": "not-a-number"}})

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.measurement is not None
    assert entry.runtime_data.status.value == "success"
