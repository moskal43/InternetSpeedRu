"""Shared entity support for InternetSpeedRu."""

from homeassistant.helpers.entity import DeviceInfo, Entity

from . import InternetSpeedRuConfigEntry
from .const import DOMAIN
from .runtime import InternetSpeedRuRuntime


class InternetSpeedRuEntity(Entity):
    """Base for entities belonging to the InternetSpeedRu service device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: InternetSpeedRuConfigEntry,
        runtime: InternetSpeedRuRuntime,
        key: str,
    ) -> None:
        self.runtime = runtime
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        """Subscribe to atomically published runtime snapshots."""
        await super().async_added_to_hass()
        self.async_on_remove(self.runtime.async_add_listener(self.async_write_ha_state))
