"""Config flow for InternetSpeedRu."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .catalog import FALLBACK_CATALOG
from .const import CONF_CITY, CONF_PROVIDER, CONF_SERVER, DOMAIN, NAME


class InternetSpeedRuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an InternetSpeedRu config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._city: str | None = None
        self._provider: str | None = None

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

        return await self.async_step_city()

    async def async_step_city(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select the server city."""
        if user_input is not None:
            self._city = user_input[CONF_CITY]
            return await self.async_step_provider()
        return self.async_show_form(
            step_id="city",
            data_schema=vol.Schema(
                {vol.Required(CONF_CITY): vol.In(FALLBACK_CATALOG.cities)}
            ),
        )

    async def async_step_provider(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select a provider available in the chosen city."""
        assert self._city is not None
        if user_input is not None:
            self._provider = user_input[CONF_PROVIDER]
            return await self.async_step_server()
        return self.async_show_form(
            step_id="provider",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROVIDER): vol.In(
                        FALLBACK_CATALOG.providers(self._city)
                    )
                }
            ),
        )

    async def async_step_server(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select a catalog server without accepting arbitrary endpoints."""
        assert self._city is not None
        assert self._provider is not None
        servers = FALLBACK_CATALOG.servers_for(self._city, self._provider)
        if user_input is not None:
            return self.async_create_entry(
                title=NAME,
                data={CONF_SERVER: user_input[CONF_SERVER]},
            )
        return self.async_show_form(
            step_id="server",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERVER): vol.In(
                        tuple(server.hostname for server in servers)
                    )
                }
            ),
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the manual server options flow."""
        return InternetSpeedRuOptionsFlow()


class InternetSpeedRuOptionsFlow(config_entries.OptionsFlow):
    """Change the manually selected catalog server."""

    def __init__(self) -> None:
        self._city: str | None = None
        self._provider: str | None = None

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Start the same city/provider/server cascade used at setup."""
        return await self.async_step_city(user_input)

    async def async_step_city(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select the new server city."""
        if user_input is not None:
            self._city = user_input[CONF_CITY]
            return await self.async_step_provider()
        return self.async_show_form(
            step_id="city",
            data_schema=vol.Schema(
                {vol.Required(CONF_CITY): vol.In(FALLBACK_CATALOG.cities)}
            ),
        )

    async def async_step_provider(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select a provider available in the new city."""
        assert self._city is not None
        if user_input is not None:
            self._provider = user_input[CONF_PROVIDER]
            return await self.async_step_server()
        return self.async_show_form(
            step_id="provider",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROVIDER): vol.In(
                        FALLBACK_CATALOG.providers(self._city)
                    )
                }
            ),
        )

    async def async_step_server(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select the new catalog server."""
        assert self._city is not None
        assert self._provider is not None
        servers = FALLBACK_CATALOG.servers_for(self._city, self._provider)
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={CONF_SERVER: user_input[CONF_SERVER]},
            )
        return self.async_show_form(
            step_id="server",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERVER): vol.In(
                        tuple(server.hostname for server in servers)
                    )
                }
            ),
        )
