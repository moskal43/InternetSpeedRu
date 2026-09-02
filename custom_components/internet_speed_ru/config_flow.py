"""Config flow for InternetSpeedRu."""

from typing import Any, ClassVar, cast

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .catalog import ServerCatalog
from .catalog_runtime import (
    CatalogSource,
    CatalogUnavailableError,
    catalog_provider,
)
from .const import (
    CONF_CITY,
    CONF_PROVIDER,
    CONF_SERVER,
    DOMAIN,
    NAME,
)


class _ManualServerCascade:
    """Shared city/provider/server steps for setup and options flows."""

    _entry_title: ClassVar[str]

    def __init__(self) -> None:
        self._city: str | None = None
        self._provider: str | None = None
        self._catalog: ServerCatalog | None = None
        self._catalog_source: CatalogSource | None = None

    async def _async_load_catalog(self) -> bool:
        try:
            selection = await catalog_provider(cast(Any, self).hass).async_catalog()
        except CatalogUnavailableError:
            return False
        self._catalog = selection.catalog
        self._catalog_source = selection.source
        return True

    async def async_step_city(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select the server city."""
        flow = cast(Any, self)
        if self._catalog is None and not await self._async_load_catalog():
            return flow.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                errors={"base": "catalog_unavailable"},
            )
        assert self._catalog is not None
        if user_input is not None:
            self._city = user_input[CONF_CITY]
            return await self.async_step_provider()
        return flow.async_show_form(
            step_id="city",
            data_schema=vol.Schema(
                {vol.Required(CONF_CITY): vol.In(self._catalog.cities)}
            ),
            description_placeholders={
                "catalog_source": (
                    self._catalog_source.value
                    if self._catalog_source is not None
                    else CatalogSource.FALLBACK.value
                )
            },
        )

    async def async_step_provider(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select a provider available in the chosen city."""
        flow = cast(Any, self)
        assert self._catalog is not None
        assert self._city is not None
        if user_input is not None:
            self._provider = user_input[CONF_PROVIDER]
            return await self.async_step_server()
        return flow.async_show_form(
            step_id="provider",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROVIDER): vol.In(
                        self._catalog.providers(self._city)
                    )
                }
            ),
        )

    async def async_step_server(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select a catalog server without accepting arbitrary endpoints."""
        flow = cast(Any, self)
        assert self._catalog is not None
        assert self._city is not None
        assert self._provider is not None
        servers = self._catalog.servers_for(self._city, self._provider)
        if user_input is not None:
            return flow.async_create_entry(
                title=self._entry_title,
                data={CONF_SERVER: user_input[CONF_SERVER]},
            )
        return flow.async_show_form(
            step_id="server",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERVER): vol.In(
                        tuple(server.hostname for server in servers)
                    )
                }
            ),
        )


class InternetSpeedRuConfigFlow(
    _ManualServerCascade,
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle an InternetSpeedRu config flow."""

    VERSION = 1
    _entry_title = NAME

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

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the manual server options flow."""
        return InternetSpeedRuOptionsFlow()


class InternetSpeedRuOptionsFlow(_ManualServerCascade, config_entries.OptionsFlow):
    """Change the manually selected catalog server."""

    _entry_title = ""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Start the same city/provider/server cascade used at setup."""
        return await self.async_step_city(user_input)
