"""Manual measurement button for InternetSpeedRu."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import InternetSpeedRuConfigEntry
from .const import DOMAIN
from .entity import InternetSpeedRuEntity
from .runtime import MeasurementBusyError, MeasurementError


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the manual measurement button."""
    async_add_entities([InternetSpeedRuRunButton(entry)])


class InternetSpeedRuRunButton(InternetSpeedRuEntity, ButtonEntity):
    """Start one connection measurement without queueing."""

    _attr_translation_key = "run_measurement"
    _attr_icon = "mdi:speedometer"

    def __init__(self, entry: InternetSpeedRuConfigEntry) -> None:
        super().__init__(entry, entry.runtime_data, "run_measurement")

    async def async_press(self) -> None:
        """Run a connection measurement."""
        try:
            await self.runtime.async_measure()
        except MeasurementBusyError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="measurement_busy",
            ) from err
        except MeasurementError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=f"measurement_{err.code.value}",
            ) from err
