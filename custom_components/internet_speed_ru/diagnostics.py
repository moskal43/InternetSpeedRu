"""Privacy-safe diagnostics for InternetSpeedRu."""

from datetime import datetime
from typing import Any

from homeassistant import loader
from homeassistant.core import HomeAssistant

from . import InternetSpeedRuConfigEntry


def _timestamp(value: datetime | None) -> str | None:
    """Serialize an optional datetime-like runtime value."""
    return value.isoformat() if value is not None else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: InternetSpeedRuConfigEntry,
) -> dict[str, Any]:
    """Return explicitly allowlisted support data for one loaded entry."""
    runtime = entry.runtime_data
    integration = await loader.async_get_integration(hass, entry.domain)
    return {
        "version": integration.version,
        "mode": "auto" if runtime.auto else "manual",
        "interval": runtime.interval,
        "server": {
            "hostname": runtime.server,
            "city": runtime.server_city,
            "provider": runtime.server_provider,
            "port": runtime.port,
        },
        "catalog": {
            "source": runtime.catalog_source.value
            if runtime.catalog_source is not None
            else None,
            "age_seconds": runtime.catalog_age_seconds,
        },
        "last_attempt": _timestamp(runtime.last_attempt),
        "last_success": _timestamp(runtime.last_success),
        "status": runtime.status.value if runtime.status is not None else None,
        "error": runtime.error.value if runtime.error is not None else None,
    }
