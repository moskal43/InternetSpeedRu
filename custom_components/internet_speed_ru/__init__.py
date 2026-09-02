"""InternetSpeedRu integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from .catalog import FALLBACK_CATALOG
from .catalog_runtime import CatalogUnavailableError, catalog_provider
from .const import CATALOG_REFRESH_INTERVAL, CONF_SERVER, DOMAIN, NAME, PLATFORMS
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
    try:
        await runtime.async_select_server(hostname)
    except CatalogUnavailableError, KeyError:
        return
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
    hostname = entry.options.get(CONF_SERVER, entry.data[CONF_SERVER])
    provider = catalog_provider(hass)
    try:
        selection = await provider.async_catalog()
        selected_server = selection.catalog.get(hostname)
    except CatalogUnavailableError, KeyError:
        selected_server = FALLBACK_CATALOG.get(hostname)
    entry.runtime_data = InternetSpeedRuRuntime(
        run_blocking=hass.async_add_executor_job,
        catalog_server=selected_server,
        catalog_provider=provider,
        state_store=HomeAssistantRuntimeStateStore(hass, entry.entry_id),
    )
    await entry.runtime_data.async_restore()
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    entry.async_on_unload(
        async_track_time_interval(
            hass,
            lambda _now: entry.runtime_data.async_refresh_catalog(),
            CATALOG_REFRESH_INTERVAL,
        )
    )

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
