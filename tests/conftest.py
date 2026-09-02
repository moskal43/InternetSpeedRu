"""Shared test fixtures for InternetSpeedRu."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from custom_components.internet_speed_ru.catalog_runtime import CatalogProvider
from custom_components.internet_speed_ru.const import (
    DATA_CATALOG_PROVIDER,
    DATA_NOW,
    DATA_PROBE,
    DATA_RUNNER,
    DATA_SCHEDULER_FACTORY,
    DOMAIN,
)

pytest_plugins = ["pytest_homeassistant_custom_component"]

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def hass_config_dir(tmp_path: Path) -> str:
    """Expose this repository's custom integrations to Home Assistant."""
    (tmp_path / "custom_components").symlink_to(
        PROJECT_ROOT / "custom_components",
        target_is_directory=True,
    )
    return str(tmp_path)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations) -> None:
    """Allow Home Assistant to load the integration from this repository."""


@pytest.fixture(autouse=True)
def fake_runtime_catalog(hass) -> None:
    """Keep every integration test independent of GitHub and real storage."""

    class EmptyStore:
        async def async_load(self):
            return None

        async def async_save(self, value) -> None:
            return None

    async def unavailable() -> str:
        raise OSError("offline")

    hass.data.setdefault(DOMAIN, {})[DATA_CATALOG_PROVIDER] = CatalogProvider(
        unavailable,
        EmptyStore(),
        now=lambda: datetime(2026, 9, 2, tzinfo=UTC),
    )

    async def probe(server: str, port: int) -> float:
        return 12.0

    hass.data[DOMAIN][DATA_PROBE] = probe
    hass.data[DOMAIN][DATA_RUNNER] = lambda server, port, reverse: (
        75.0 if reverse else 25.0
    )

    class ImmediateOnlyScheduler:
        """Run initial work while leaving future timers inert in unrelated tests."""

        def now(self):
            return datetime(2026, 9, 2, tzinfo=UTC)

        def async_call_at(self, callback, when):
            if when <= self.now():
                task = hass.async_create_task(callback())
                return task.cancel
            return lambda: None

    scheduler = ImmediateOnlyScheduler()
    hass.data[DOMAIN][DATA_NOW] = scheduler.now
    hass.data[DOMAIN][DATA_SCHEDULER_FACTORY] = lambda hass: scheduler
