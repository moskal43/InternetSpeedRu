"""Config entry setup tests."""

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr

from custom_components.internet_speed_ru.const import (
    CONF_CITY,
    CONF_PROVIDER,
    CONF_SERVER,
)

DOMAIN = "internet_speed_ru"


async def test_config_entry_loads_and_registers_service_device(hass) -> None:
    """A configured integration is loaded and visible as a service device."""
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CITY: "Киров"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVIDER: "ЭР-Телеком"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: "st.kirov.ertelecom.ru"}
    )
    entry = result["result"]

    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, entry.entry_id)},
    )
    assert device is not None
    assert device.name == "InternetSpeedRu"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
