"""Config entry setup tests."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

from tests.helpers import async_configure_kirov_entry

DOMAIN = "internet_speed_ru"


async def test_config_entry_loads_and_registers_service_device(hass) -> None:
    """A configured integration is loaded and visible as a service device."""
    entry = await async_configure_kirov_entry(hass)

    assert entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, entry.entry_id)},
    )
    assert device is not None
    assert device.name == "InternetSpeedRu"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
