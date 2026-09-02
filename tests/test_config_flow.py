"""User-facing configuration flow tests."""

import asyncio
from datetime import UTC, datetime

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.internet_speed_ru.catalog import ServerCatalog
from custom_components.internet_speed_ru.catalog_runtime import (
    CatalogCache,
    CatalogProvider,
    CatalogSource,
)
from custom_components.internet_speed_ru.const import (
    CONF_CITY,
    CONF_PROVIDER,
    CONF_SERVER,
    DATA_CATALOG_PROVIDER,
    DOMAIN,
)
from custom_components.internet_speed_ru.runtime import (
    MeasurementError,
    MeasurementErrorCode,
)
from tests.helpers import async_configure_kirov_entry


class FakeCatalogStore:
    """In-memory boundary for catalog cache behavior."""

    def __init__(self, value=None) -> None:
        self.value = value

    async def async_load(self):
        return self.value

    async def async_save(self, value) -> None:
        self.value = value


def _install_catalog_provider(
    hass,
    fetch,
    store=None,
    fallback=None,
    now=lambda: datetime(2026, 9, 2, 9, tzinfo=UTC),
) -> CatalogProvider:
    provider = CatalogProvider(
        fetch,
        store or FakeCatalogStore(),
        fallback=fallback,
        now=now,
    )
    hass.data.setdefault(DOMAIN, {})[DATA_CATALOG_PROVIDER] = provider
    return provider


REMOTE_CATALOG = """\
- Name: ExampleNet Kazan
  City: Kazan
  address: speed.example.net
  port: 5201-5202
"""


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


async def test_runtime_remote_catalog_is_used_and_not_fetched_twice_in_24h(
    hass,
) -> None:
    """Config and options flows share one fresh runtime catalog."""
    requests = 0
    current_time = datetime(2026, 9, 2, 9, tzinfo=UTC)

    async def fetch() -> str:
        nonlocal requests
        requests += 1
        if requests == 2:
            raise OSError("offline")
        return REMOTE_CATALOG

    stale_cache = ServerCatalog(
        [
            {
                "city": "Тула",
                "provider": "CachedNet",
                "hostname": "cached.example.net",
                "ports": [5201],
            }
        ]
    )
    store = FakeCatalogStore(
        CatalogCache(
            stale_cache,
            datetime(2026, 8, 31, tzinfo=UTC),
            datetime(2026, 8, 31, tzinfo=UTC),
        )
    )
    _install_catalog_provider(hass, fetch, store=store, now=lambda: current_time)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["step_id"] == "city"
    assert "Kazan" in result["data_schema"]({CONF_CITY: "Kazan"}).values()
    assert result["description_placeholders"] == {
        "catalog_source": CatalogSource.REMOTE.value
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CITY: "Kazan"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PROVIDER: "ExampleNet"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SERVER: "speed.example.net"}
    )
    entry = result["result"]
    await hass.async_block_till_done()

    options = await hass.config_entries.options.async_init(entry.entry_id)
    assert options["step_id"] == "city"
    assert requests == 1

    current_time = datetime(2026, 9, 3, 8, 59, tzinfo=UTC)
    await entry.runtime_data.async_refresh_catalog()
    assert requests == 1

    current_time = datetime(2026, 9, 3, 9, tzinfo=UTC)
    await entry.runtime_data.async_refresh_catalog()
    assert requests == 2

    refreshed_options = await hass.config_entries.options.async_init(entry.entry_id)
    assert refreshed_options["description_placeholders"] == {
        "catalog_source": CatalogSource.CACHE.value
    }


@pytest.mark.parametrize("payload", ["", REMOTE_CATALOG + "- Name: Broken\n"])
async def test_invalid_remote_keeps_and_uses_last_known_good_cache(
    hass, payload: str
) -> None:
    """A wholly invalid response cannot replace the user's working cache."""
    cached = ServerCatalog(
        [
            {
                "city": "Тула",
                "provider": "CachedNet",
                "hostname": "cached.example.net",
                "ports": [5201],
            }
        ]
    )
    store = FakeCatalogStore(
        CatalogCache(
            cached,
            datetime(2026, 8, 31, tzinfo=UTC),
            datetime(2026, 8, 31, tzinfo=UTC),
        )
    )

    async def invalid() -> str:
        return payload

    _install_catalog_provider(hass, invalid, store=store)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["step_id"] == "city"
    assert result["description_placeholders"] == {
        "catalog_source": CatalogSource.CACHE.value
    }
    assert "Тула" in result["data_schema"]({CONF_CITY: "Тула"}).values()
    assert store.value.catalog.servers == cached.servers


async def test_offline_setup_warns_when_using_bundled_fallback(hass) -> None:
    """GitHub downtime leaves setup usable and makes its source visible."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["step_id"] == "city"
    assert result["description_placeholders"] == {
        "catalog_source": CatalogSource.FALLBACK.value
    }
    assert "Киров" in result["data_schema"]({CONF_CITY: "Киров"}).values()


async def test_setup_stays_open_with_localized_error_when_all_catalogs_fail(
    hass,
) -> None:
    """No config entry is created without any validated catalog source."""

    async def unavailable() -> str:
        raise OSError("offline")

    _install_catalog_provider(hass, unavailable, fallback=None)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "catalog_unavailable"}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_existing_remote_selection_restores_when_catalog_drops_server(
    hass,
) -> None:
    """A catalog refresh cannot discard an existing entry's entities or status."""

    async def original_remote() -> str:
        return REMOTE_CATALOG

    _install_catalog_provider(hass, original_remote)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    for user_input in (
        {},
        {CONF_CITY: "Kazan"},
        {CONF_PROVIDER: "ExampleNet"},
        {CONF_SERVER: "speed.example.net"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input
        )
    entry = result["result"]
    await hass.async_block_till_done()

    entry.runtime_data.probe = lambda server, port: asyncio.sleep(0, result=10.0)
    entry.runtime_data.runner = lambda server, port, reverse: 50.0
    await entry.runtime_data.async_measure()
    assert await hass.config_entries.async_unload(entry.entry_id)

    async def replacement_remote() -> str:
        return """\
- Name: OtherNet Omsk
  City: Omsk
  address: other.example.net
  port: 5201
"""

    _install_catalog_provider(hass, replacement_remote)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.server == "speed.example.net"
    assert entry.runtime_data.measurement is not None
    assert entry.runtime_data.measurement.server == "speed.example.net"
    assert entry.runtime_data.status.value == "success"

    previous_attempt = entry.runtime_data.last_attempt
    with pytest.raises(MeasurementError) as error:
        await entry.runtime_data.async_measure()

    assert error.value.code is MeasurementErrorCode.UNREACHABLE
    assert entry.runtime_data.measurement.server == "speed.example.net"
    assert entry.runtime_data.status.value == "error"
    assert entry.runtime_data.error is MeasurementErrorCode.UNREACHABLE
    assert entry.runtime_data.last_attempt != previous_attempt

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.measurement.server == "speed.example.net"
    assert entry.runtime_data.status.value == "error"
    assert entry.runtime_data.error is MeasurementErrorCode.UNREACHABLE


async def test_options_flow_changes_manual_server_through_same_cascade(hass) -> None:
    """Options expose city, provider, and server without free-form endpoints."""
    entry = await async_configure_kirov_entry(hass)

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
    entry = await async_configure_kirov_entry(hass)

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
    entry = await async_configure_kirov_entry(hass)

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
