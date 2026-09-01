"""Shared test fixtures for InternetSpeedRu."""

from pathlib import Path

import pytest

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
