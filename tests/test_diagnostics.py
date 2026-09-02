"""Privacy-safe support diagnostics behavior tests."""

import asyncio
import json
import socket
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.internet_speed_ru.catalog import (
    FALLBACK_CATALOG,
    CatalogServer,
    ServerCatalog,
)
from custom_components.internet_speed_ru.catalog_runtime import (
    CatalogSelection,
    CatalogSource,
    CatalogUnavailableError,
)
from custom_components.internet_speed_ru.const import (
    DATA_CATALOG_PROVIDER,
    DATA_NOW,
    DOMAIN,
)
from custom_components.internet_speed_ru.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.internet_speed_ru.iperf import (
    InvalidIperfResultError,
    IperfExecutionError,
)
from tests.helpers import async_configure_auto_entry, async_configure_kirov_entry


async def test_diagnostics_are_an_explicit_support_whitelist(hass) -> None:
    """Diagnostics expose useful public context and no implicit entry data."""
    now = datetime(2026, 9, 2, 12, tzinfo=UTC)
    updated_at = now - timedelta(hours=3)

    class RemoteProvider:
        async def async_catalog(self) -> CatalogSelection:
            return CatalogSelection(
                FALLBACK_CATALOG,
                CatalogSource.REMOTE,
                updated_at,
            )

    hass.data[DOMAIN][DATA_CATALOG_PROVIDER] = RemoteProvider()
    hass.data[DOMAIN][DATA_NOW] = lambda: now
    entry = await async_configure_kirov_entry(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    status = hass.states.get("sensor.internetspeedru_last_measurement_status")

    assert status is not None
    assert status.attributes["mode"] == "manual"
    assert diagnostics == {
        "version": "0.1.3",
        "mode": "manual",
        "interval": "24h",
        "server": {
            "hostname": "st.kirov.ertelecom.ru",
            "city": "Киров",
            "provider": "ЭР-Телеком",
            "port": 5201,
        },
        "catalog": {
            "source": "remote",
            "age_seconds": 10800.0,
        },
        "last_attempt": now.isoformat(),
        "last_success": now.isoformat(),
        "status": "success",
        "error": None,
    }


async def test_status_exposes_attempt_and_success_timing_while_running(hass) -> None:
    """The running state keeps the last success and dates the new attempt."""
    now = [datetime(2026, 9, 2, tzinfo=UTC)]
    hass.data[DOMAIN][DATA_NOW] = lambda: now[0]
    entry = await async_configure_kirov_entry(hass)
    previous_success = now[0].isoformat()
    now[0] += timedelta(hours=1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_probe(server: str, port: int) -> float:
        started.set()
        await release.wait()
        return 12.0

    entry.runtime_data.probe = blocked_probe
    run = asyncio.create_task(
        hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.internetspeedru_run_measurement"},
            blocking=True,
        )
    )
    await started.wait()

    status = hass.states.get("sensor.internetspeedru_last_measurement_status")
    assert status is not None
    assert status.state == "running"
    assert status.attributes["last_attempt"] == now[0].isoformat()
    assert status.attributes["last_success"] == previous_success
    assert status.attributes["error"] is None

    release.set()
    await run


async def test_raw_network_failure_data_never_enters_support_surfaces(hass) -> None:
    """A normalized DNS failure cannot leak its adapter details."""
    entry = await async_configure_kirov_entry(hass)
    secret = "local_ip=192.168.77.4 interface=en0 dns_result=203.0.113.8"

    async def dns_failure(server: str, port: int) -> float:
        raise socket.gaierror(secret)

    entry.runtime_data.probe = dns_failure
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.internetspeedru_run_measurement"},
            blocking=True,
        )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    status = hass.states.get("sensor.internetspeedru_last_measurement_status")
    assert status is not None
    assert diagnostics["error"] == "dns"
    assert diagnostics["catalog"] == {
        "source": "fallback",
        "age_seconds": None,
    }
    assert status.attributes["error"] == "dns"
    serialized = json.dumps(
        {"diagnostics": diagnostics, "attributes": dict(status.attributes)}
    )
    assert secret not in serialized
    assert all(
        forbidden not in serialized
        for forbidden in (
            "local_ip",
            "public_ip",
            "interface",
            "dns_result",
            "iperf_json",
            "history",
        )
    )


async def test_fallback_replaces_stale_remote_catalog_age(hass) -> None:
    """Diagnostics keep catalog source and age from the same selection."""
    now = datetime(2026, 9, 2, 12, tzinfo=UTC)
    entry = await async_configure_kirov_entry(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)

    class RemoteWithoutConfiguredServer:
        async def async_catalog(self) -> CatalogSelection:
            return CatalogSelection(
                ServerCatalog(
                    (
                        CatalogServer(
                            "Москва",
                            "ExampleNet",
                            "speed.example.net",
                            (5201,),
                        ),
                    )
                ),
                CatalogSource.REMOTE,
                now - timedelta(hours=3),
            )

    hass.data[DOMAIN][DATA_CATALOG_PROVIDER] = RemoteWithoutConfiguredServer()
    hass.data[DOMAIN][DATA_NOW] = lambda: now
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["catalog"] == {
        "source": "fallback",
        "age_seconds": None,
    }


async def test_catalog_failure_has_a_stable_diagnostic_code(hass) -> None:
    """A catalog loss during an Auto rerank is distinct from reachability."""
    now = [datetime(2026, 9, 2, tzinfo=UTC)]

    class ToggleProvider:
        unavailable = False

        async def async_catalog(self) -> CatalogSelection:
            if self.unavailable:
                raise CatalogUnavailableError
            return CatalogSelection(
                FALLBACK_CATALOG,
                CatalogSource.CACHE,
                now[0] - timedelta(hours=2),
            )

    provider = ToggleProvider()
    hass.data[DOMAIN][DATA_CATALOG_PROVIDER] = provider
    hass.data[DOMAIN][DATA_NOW] = lambda: now[0]
    entry = await async_configure_auto_entry(hass)
    provider.unavailable = True
    now[0] += timedelta(days=1)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.internetspeedru_run_measurement"},
            blocking=True,
        )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    status = hass.states.get("sensor.internetspeedru_last_measurement_status")
    assert diagnostics["mode"] == "auto"
    assert status is not None
    assert status.attributes["mode"] == "auto"
    assert diagnostics["catalog"] == {
        "source": "cache",
        "age_seconds": 93600.0,
    }
    assert diagnostics["error"] == "catalog"


async def test_unexpected_adapter_text_is_replaced_by_a_machine_code(hass) -> None:
    """Arbitrary adapter exceptions cannot become attributes or diagnostics."""
    entry = await async_configure_kirov_entry(hass)
    secret = '{"raw_iperf_json":{"public_ip":"203.0.113.9"}}'

    def broken_runner(server: str, port: int, reverse: bool) -> float:
        raise ValueError(secret)

    entry.runtime_data.runner = broken_runner
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.internetspeedru_run_measurement"},
            blocking=True,
        )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    status = hass.states.get("sensor.internetspeedru_last_measurement_status")
    assert status is not None
    assert diagnostics["error"] == "unexpected"
    assert status.attributes["error"] == "unexpected"
    assert secret not in json.dumps(
        {"diagnostics": diagnostics, "attributes": dict(status.attributes)}
    )


@pytest.mark.parametrize(
    ("stage", "failure", "expected"),
    [
        ("probe", TimeoutError("adapter timeout"), "timeout"),
        ("probe", OSError("all ports refused"), "unreachable"),
        ("runner", InvalidIperfResultError("raw invalid result"), "invalid_result"),
        ("runner", IperfExecutionError("raw library error"), "iperf"),
    ],
)
async def test_main_failure_paths_publish_only_normalized_codes(
    hass,
    stage: str,
    failure: Exception,
    expected: str,
) -> None:
    """Support diagnostics distinguish failures without adapter messages."""
    entry = await async_configure_kirov_entry(hass)

    async def failed_probe(server: str, port: int) -> float:
        raise failure

    def failed_runner(server: str, port: int, reverse: bool) -> float:
        raise failure

    if stage == "probe":
        entry.runtime_data.probe = failed_probe
    else:
        entry.runtime_data.runner = failed_runner

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.internetspeedru_run_measurement"},
            blocking=True,
        )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["error"] == expected
    assert str(failure) not in json.dumps(diagnostics)
