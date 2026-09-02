"""InternetSpeedRu integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from .catalog import FALLBACK_CATALOG
from .catalog_runtime import (
    CatalogSelection,
    CatalogSource,
    CatalogUnavailableError,
    catalog_provider,
)
from .const import (
    CATALOG_REFRESH_INTERVAL,
    CONF_SERVER,
    DATA_NOW,
    DATA_PROBE,
    DATA_RUNNER,
    DATA_SCHEDULER_FACTORY,
    DATA_STATE_STORE_FACTORY,
    DOMAIN,
    NAME,
    PLATFORMS,
    effective_auto,
    effective_interval,
)
from .runtime import InternetSpeedRuRuntime, MeasurementError
from .scheduling import HomeAssistantClockScheduler
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
    auto = effective_auto(entry)
    hostname = entry.options.get(CONF_SERVER, entry.data.get(CONF_SERVER, ""))
    interval = effective_interval(entry)
    runtime = entry.runtime_data
    mode_changed = auto != runtime.auto
    server_changed = hostname != runtime.server
    runtime.update_interval(interval)
    if not mode_changed and (auto or not server_changed):
        return
    runtime.set_auto(auto)
    if not auto:
        try:
            await runtime.async_select_server(hostname)
        except CatalogUnavailableError, KeyError:
            return
    if not runtime.running:
        entry.async_create_background_task(
            hass,
            _async_measure_after_server_change(runtime),
            "InternetSpeedRu measurement after selection change",
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
) -> bool:
    """Set up InternetSpeedRu from a config entry."""
    auto = effective_auto(entry)
    hostname = entry.options.get(CONF_SERVER, entry.data.get(CONF_SERVER, ""))
    provider = catalog_provider(hass)
    dependencies = hass.data.get(DOMAIN, {})
    state_store_factory = dependencies.get(
        DATA_STATE_STORE_FACTORY, HomeAssistantRuntimeStateStore
    )
    state_store = state_store_factory(hass, entry.entry_id)
    selected_server = None
    active_catalog_selection = None
    try:
        selection = await provider.async_catalog()
        active_catalog_selection = selection
        if not auto:
            selected_server = selection.catalog.get(hostname)
    except (CatalogUnavailableError, KeyError) as err:
        if auto:
            raise ConfigEntryNotReady(
                "No validated catalog is available for automatic selection"
            ) from err
        try:
            selected_server = FALLBACK_CATALOG.get(hostname)
            active_catalog_selection = CatalogSelection(
                FALLBACK_CATALOG,
                CatalogSource.FALLBACK,
                None,
            )
        except KeyError as err:
            persisted = await state_store.async_load()
            measurement = persisted.measurement if persisted is not None else None
            if measurement is None or measurement.server != hostname:
                raise ConfigEntryNotReady(
                    "Selected server is unavailable in every validated catalog"
                ) from err
    runtime_args = {}
    if DATA_PROBE in dependencies:
        runtime_args["probe"] = dependencies[DATA_PROBE]
    if DATA_RUNNER in dependencies:
        runtime_args["runner"] = dependencies[DATA_RUNNER]
    if DATA_NOW in dependencies:
        runtime_args["now"] = dependencies[DATA_NOW]
    scheduler_factory = dependencies.get(
        DATA_SCHEDULER_FACTORY, HomeAssistantClockScheduler
    )
    scheduler = scheduler_factory(hass)
    if DATA_NOW not in dependencies:
        runtime_args["now"] = scheduler.now
    entry.runtime_data = InternetSpeedRuRuntime(
        run_blocking=hass.async_add_executor_job,
        catalog_server=selected_server,
        configured_hostname=hostname,
        catalog_provider=provider,
        catalog_selection=active_catalog_selection,
        auto=auto,
        state_store=state_store,
        **runtime_args,
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

    entry.runtime_data.start_schedule(
        scheduler,
        effective_interval(entry),
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
) -> bool:
    """Unload InternetSpeedRu."""
    entry.runtime_data.async_cancel()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
