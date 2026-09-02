"""Persistent runtime-state adapter for InternetSpeedRu."""

import math
from collections.abc import Mapping
from datetime import datetime
from logging import getLogger

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .catalog import CatalogServer, ServerCatalog
from .const import DOMAIN
from .runtime import (
    Measurement,
    MeasurementErrorCode,
    MeasurementStatus,
    PersistedRuntimeState,
)
from .selection import SelectedServer

STORAGE_VERSION = 1

_LOGGER = getLogger(__name__)


def runtime_storage_key(entry_id: str) -> str:
    """Return the isolated storage key for one config entry."""
    return f"{DOMAIN}.{entry_id}"


class HomeAssistantRuntimeStateStore:
    """Store one bounded runtime snapshot using Home Assistant storage."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, object]] = Store(
            hass,
            STORAGE_VERSION,
            runtime_storage_key(entry_id),
        )

    async def async_load(self) -> PersistedRuntimeState | None:
        """Load valid state, ignoring corrupt or incompatible data safely."""
        try:
            raw = await self._store.async_load()
            return _deserialize_state(raw) if raw is not None else None
        except (HomeAssistantError, KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Ignoring invalid persisted runtime state: %s", err)
            return None

    async def async_save(self, state: PersistedRuntimeState) -> None:
        """Replace stored state without retaining measurement history."""
        await self._store.async_save(_serialize_state(state))


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _serialize_state(state: PersistedRuntimeState) -> dict[str, object]:
    measurement: dict[str, object] | None = None
    if state.measurement is not None:
        measurement = {
            "download_mbps": state.measurement.download_mbps,
            "upload_mbps": state.measurement.upload_mbps,
            "latency_ms": state.measurement.latency_ms,
            "server": {
                "city": state.measurement.server_city,
                "provider": state.measurement.server_provider,
                "hostname": state.measurement.server,
                "port": state.measurement.port,
            },
            "measured_at": state.measurement.measured_at.isoformat(),
        }
    return {
        "measurement": measurement,
        "schedule_baseline": _serialize_datetime(state.schedule_baseline),
        "last_attempt": _serialize_datetime(state.last_attempt),
        "last_success": _serialize_datetime(state.last_success),
        "status": state.status.value if state.status is not None else None,
        "error": state.error.value if state.error is not None else None,
        "last_ranking": _serialize_datetime(state.last_ranking),
        "ranked_servers": [
            {
                "city": ranked.server.city,
                "provider": ranked.server.provider,
                "hostname": ranked.server.hostname,
                "ports": list(ranked.server.ports),
                "port": ranked.port,
                "latency_ms": ranked.latency_ms,
            }
            for ranked in state.ranked_servers
        ],
    }


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("expected an object")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError("expected a non-empty string")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("expected a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("measurement value must be finite and non-negative")
    return number


def _port(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError("invalid server port")
    return value


def _ports(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise TypeError("expected a port list")
    return tuple(_port(port) for port in value)


def _datetime(value: object) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(_text(value))
    if parsed.tzinfo is None:
        raise ValueError("stored datetime must include a timezone")
    return parsed


def _deserialize_measurement(value: object) -> Measurement | None:
    if value is None:
        return None
    raw = _mapping(value)
    server = _mapping(raw["server"])
    measured_at = _datetime(raw["measured_at"])
    if measured_at is None:
        raise ValueError("measurement timestamp is required")
    return Measurement(
        download_mbps=_number(raw["download_mbps"]),
        upload_mbps=_number(raw["upload_mbps"]),
        latency_ms=_number(raw["latency_ms"]),
        server=_text(server["hostname"]),
        server_city=_text(server["city"]),
        server_provider=_text(server["provider"]),
        port=_port(server["port"]),
        measured_at=measured_at,
    )


def _optional_status(value: object) -> MeasurementStatus | None:
    if value is None:
        return None
    return MeasurementStatus(_text(value))


def _optional_error(value: object) -> MeasurementErrorCode | None:
    if value is None:
        return None
    return MeasurementErrorCode(_text(value))


def _deserialize_ranked_servers(value: object) -> tuple[SelectedServer, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError("expected a ranked server list")
    ranked: list[SelectedServer] = []
    for item in value:
        raw = _mapping(item)
        server = ServerCatalog(
            (
                CatalogServer(
                    city=_text(raw["city"]),
                    provider=_text(raw["provider"]),
                    hostname=_text(raw["hostname"]),
                    ports=_ports(raw["ports"]),
                ),
            )
        ).servers[0]
        port = _port(raw["port"])
        if port not in server.ports:
            raise ValueError("ranked port is not offered by its server")
        ranked.append(
            SelectedServer(
                server=server,
                port=port,
                latency_ms=_number(raw["latency_ms"]),
            )
        )
    return tuple(ranked)


def _deserialize_state(value: object) -> PersistedRuntimeState:
    raw = _mapping(value)
    return PersistedRuntimeState(
        measurement=_deserialize_measurement(raw["measurement"]),
        schedule_baseline=_datetime(raw["schedule_baseline"]),
        last_attempt=_datetime(raw["last_attempt"]),
        last_success=_datetime(raw["last_success"]),
        status=_optional_status(raw["status"]),
        error=_optional_error(raw["error"]),
        last_ranking=_datetime(raw.get("last_ranking")),
        ranked_servers=_deserialize_ranked_servers(raw.get("ranked_servers")),
    )
