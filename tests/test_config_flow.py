"""User-facing configuration flow tests."""

import asyncio

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.internet_speed_ru.const import (
    CONF_CITY,
    CONF_PROVIDER,
    CONF_SERVER,
)

DOMAIN = "internet_speed_ru"


async def test_user_can_configure_integration_once(hass) -> None:
    """A user selects a catalog server through the manual cascade once."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "city"
    assert "Киров" in result["data_schema"]({CONF_CITY: "Киров"}).values()

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CITY: "Киров"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "provider"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVIDER: "ЭР-Телеком"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "server"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: "st.kirov.ertelecom.ru"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "InternetSpeedRu"
    assert result["data"] == {CONF_SERVER: "st.kirov.ertelecom.ru"}

    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert duplicate["type"] is FlowResultType.ABORT
    assert duplicate["reason"] == "single_instance_allowed"


async def test_options_flow_changes_manual_server_through_same_cascade(hass) -> None:
    """Options expose city, provider, and server without free-form endpoints."""
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CITY: "Киров"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVIDER: "ЭР-Телеком"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: "st.kirov.ertelecom.ru"}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    options = await hass.config_entries.options.async_init(entry.entry_id)
    assert options["step_id"] == "city"

    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_CITY: "Москва"}
    )
    assert options["step_id"] == "provider"

    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_PROVIDER: "HOSTKEY"}
    )
    assert options["step_id"] == "server"

    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_SERVER: "spd-rudp.hostkey.ru"}
    )

    assert options["type"] is FlowResultType.CREATE_ENTRY
    assert options["data"] == {CONF_SERVER: "spd-rudp.hostkey.ru"}


async def test_server_change_starts_measurement_when_idle(hass) -> None:
    """A new selected server immediately starts one fresh measurement."""
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CITY: "Киров"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVIDER: "ЭР-Телеком"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: "st.kirov.ertelecom.ru"}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    started = asyncio.Event()
    release = asyncio.Event()
    attempted_servers: list[str] = []

    async def probe(server: str, port: int) -> float:
        attempted_servers.append(server)
        started.set()
        await release.wait()
        return 10.0

    entry.runtime_data.probe = probe
    entry.runtime_data.runner = lambda server, port, reverse: 50.0

    options = await hass.config_entries.options.async_init(entry.entry_id)
    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_CITY: "Москва"}
    )
    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_PROVIDER: "HOSTKEY"}
    )
    await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_SERVER: "spd-rudp.hostkey.ru"}
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    assert attempted_servers == ["spd-rudp.hostkey.ru"]
    release.set()


async def test_server_change_during_measurement_does_not_queue_another(hass) -> None:
    """A server change updates future work but never queues behind active work."""
    flow = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CITY: "Киров"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVIDER: "ЭР-Телеком"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: "st.kirov.ertelecom.ru"}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    started = asyncio.Event()
    release = asyncio.Event()
    attempted_servers: list[str] = []

    async def probe(server: str, port: int) -> float:
        attempted_servers.append(server)
        started.set()
        await release.wait()
        return 10.0

    entry.runtime_data.probe = probe
    entry.runtime_data.runner = lambda server, port, reverse: 50.0
    active = asyncio.create_task(entry.runtime_data.async_measure())
    await started.wait()

    options = await hass.config_entries.options.async_init(entry.entry_id)
    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_CITY: "Москва"}
    )
    options = await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_PROVIDER: "HOSTKEY"}
    )
    await hass.config_entries.options.async_configure(
        options["flow_id"], {CONF_SERVER: "spd-rudp.hostkey.ru"}
    )

    release.set()
    await active
    await asyncio.sleep(0)
    assert attempted_servers == ["st.kirov.ertelecom.ru"] * 3
    assert entry.runtime_data.server == "spd-rudp.hostkey.ru"
