"""User-facing configuration flow tests."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

DOMAIN = "internet_speed_ru"


async def test_user_can_configure_integration_once(hass) -> None:
    """A user can create the only InternetSpeedRu config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "InternetSpeedRu"
    assert result["data"] == {}

    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert duplicate["type"] is FlowResultType.ABORT
    assert duplicate["reason"] == "single_instance_allowed"
