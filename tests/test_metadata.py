"""Home Assistant and HACS metadata contract tests."""

import json
from pathlib import Path

from homeassistant import loader

DOMAIN = "internet_speed_ru"
PROJECT_ROOT = Path(__file__).parent.parent


async def test_home_assistant_manifest_contract(hass) -> None:
    """Home Assistant sees the intended custom integration metadata."""
    integration = await loader.async_get_integration(hass, DOMAIN)
    expected = {
        "codeowners": ["@moskal43"],
        "config_flow": True,
        "dependencies": [],
        "documentation": "https://github.com/moskal43/InternetSpeedRu",
        "domain": DOMAIN,
        "integration_type": "service",
        "iot_class": "local_polling",
        "issue_tracker": "https://github.com/moskal43/InternetSpeedRu/issues",
        "name": "InternetSpeedRu",
        "requirements": ["iperf3==0.1.11"],
        "single_config_entry": True,
        "version": "0.1.1",
    }

    assert {key: integration.manifest[key] for key in expected} == expected


def test_hacs_metadata_contract() -> None:
    """HACS sees the intended name, country, and minimum HA version."""
    metadata = json.loads((PROJECT_ROOT / "hacs.json").read_text(encoding="utf-8"))

    assert metadata == {
        "country": "RU",
        "homeassistant": "2026.8.0",
        "name": "InternetSpeedRu",
    }
