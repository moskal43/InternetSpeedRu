"""Config flow for InternetSpeedRu."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .const import DOMAIN, NAME


class InternetSpeedRuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an InternetSpeedRu config flow."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Create the only InternetSpeedRu config entry."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
            )

        return self.async_create_entry(title=NAME, data={})
