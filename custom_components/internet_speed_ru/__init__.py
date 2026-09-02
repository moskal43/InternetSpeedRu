"""InternetSpeedRu integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .catalog import FALLBACK_CATALOG
from .const import CONF_SERVER, DOMAIN, NAME, PLATFORMS
from .runtime import InternetSpeedRuRuntime, MeasurementError
from .storage import HomeAssistantRuntimeStateStore

type InternetSpeedRuConfigEntry = ConfigEntry[InternetSpeedRuRuntime]


async def _async_measure_after_server_change(
    runtime: InternetSpeedRuRuntime,
) -> None:
    """Run an options-triggered measurement and retain failure in runtime state."""
    try:
        await runtime.async_measure()
    except MeasurementError:
        return


async def _async_options_updated(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
) -> None:
    """Apply a manual server change and trigger work only when idle."""
    hostname = entry.options.get(CONF_SERVER, entry.data[CONF_SERVER])
    runtime = entry.runtime_data
    changed = hostname != runtime.server
    runtime.select_server(FALLBACK_CATALOG.get(hostname))
    if changed and not runtime.running:
        entry.async_create_background_task(
            hass,
            _async_measure_after_server_change(runtime),
            "InternetSpeedRu measurement after server change",
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
) -> bool:
    """Set up InternetSpeedRu from a config entry."""
    entry.runtime_data = InternetSpeedRuRuntime(
        run_blocking=hass.async_add_executor_job,
        catalog_server=FALLBACK_CATALOG.get(
            entry.options.get(CONF_SERVER, entry.data[CONF_SERVER])
        ),
        state_store=HomeAssistantRuntimeStateStore(hass, entry.entry_id),
    )
    await entry.runtime_data.async_restore()
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        entry_type=dr.DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=NAME,
        model=NAME,
        name=NAME,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
) -> bool:
    """Unload InternetSpeedRu."""
    entry.runtime_data.async_cancel()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
