"""Measurement sensors for InternetSpeedRu."""

from typing import ClassVar, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfDataRate, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import InternetSpeedRuConfigEntry
from .entity import InternetSpeedRuEntity
from .runtime import MeasurementStatus

SPEED_DESCRIPTIONS: Final = (
    SensorEntityDescription(
        key="download",
        translation_key="download",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="upload",
        translation_key="upload",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="latency",
        translation_key="latency",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the four measurement sensors."""
    async_add_entities(
        [
            InternetSpeedRuMeasurementSensor(entry, description)
            for description in SPEED_DESCRIPTIONS
        ]
        + [InternetSpeedRuStatusSensor(entry)]
    )


class InternetSpeedRuMeasurementSensor(InternetSpeedRuEntity, SensorEntity):
    """A metric from the last complete connection measurement."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        entry: InternetSpeedRuConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(entry, entry.runtime_data, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        """Return the metric without exposing partial results."""
        measurement = self.runtime.measurement
        if measurement is None:
            return None
        if self.entity_description.key == "download":
            return measurement.download_mbps
        if self.entity_description.key == "upload":
            return measurement.upload_mbps
        return measurement.latency_ms


class InternetSpeedRuStatusSensor(InternetSpeedRuEntity, SensorEntity):
    """Status of the latest connection measurement attempt."""

    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = [status.value for status in MeasurementStatus]

    def __init__(self, entry: InternetSpeedRuConfigEntry) -> None:
        super().__init__(entry, entry.runtime_data, "status")

    @property
    def native_value(self) -> str | None:
        """Return the latest attempt status."""
        return self.runtime.status

    @property
    def extra_state_attributes(self) -> dict[str, str | int | None]:
        """Return stable public context for the latest attempt."""
        measurement = self.runtime.measurement
        return {
            "server": measurement.server if measurement else self.runtime.server,
            "city": measurement.server_city
            if measurement
            else self.runtime.server_city,
            "provider": measurement.server_provider
            if measurement
            else self.runtime.server_provider,
            "port": measurement.port if measurement else self.runtime.port,
            "error": self.runtime.error,
            "last_attempt": self.runtime.last_attempt.isoformat()
            if self.runtime.last_attempt
            else None,
            "last_success": self.runtime.last_success.isoformat()
            if self.runtime.last_success
            else None,
        }
