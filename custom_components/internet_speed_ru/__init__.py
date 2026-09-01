"""InternetSpeedRu integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, NAME
from .runtime import InternetSpeedRuRuntime

type InternetSpeedRuConfigEntry = ConfigEntry[InternetSpeedRuRuntime]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
) -> bool:
    """Set up InternetSpeedRu from a config entry."""
    entry.runtime_data = InternetSpeedRuRuntime(
        run_blocking=hass.async_add_executor_job,
    )

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        entry_type=dr.DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=NAME,
        model=NAME,
        name=NAME,
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
) -> bool:
    """Unload InternetSpeedRu."""
    return True
