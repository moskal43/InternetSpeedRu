"""Public Home Assistant setup helpers used by behavior tests."""

from homeassistant import config_entries

from custom_components.internet_speed_ru import InternetSpeedRuConfigEntry
from custom_components.internet_speed_ru.const import (
    CONF_CITY,
    CONF_PROVIDER,
    CONF_SERVER,
    DOMAIN,
)


async def async_configure_kirov_entry(hass) -> InternetSpeedRuConfigEntry:
    """Create and load a manual Kirov entry through the public config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    for user_input in (
        {},
        {CONF_CITY: "Киров"},
        {CONF_PROVIDER: "ЭР-Телеком"},
        {CONF_SERVER: "st.kirov.ertelecom.ru"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )
    await hass.async_block_till_done()
    return result["result"]
