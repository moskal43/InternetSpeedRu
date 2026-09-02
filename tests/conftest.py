"""Shared test fixtures for InternetSpeedRu."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from custom_components.internet_speed_ru.catalog_runtime import CatalogProvider
from custom_components.internet_speed_ru.const import DATA_CATALOG_PROVIDER, DOMAIN

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
