"""User-visible scheduling behavior through a loaded config entry."""

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from custom_components.internet_speed_ru.const import (
    CONF_INTERVAL,
    DATA_RUNNER,
    DATA_SCHEDULER_FACTORY,
    DATA_STATE_STORE_FACTORY,
    DOMAIN,
    SCHEDULE_INTERVALS,
)
from tests.helpers import async_configure_kirov_entry

type TimerCallback = Callable[[], Awaitable[None] | None]


class FakeClock:
    """Deterministic clock/timer boundary driven by behavior tests."""

    def __init__(self) -> None:
        self.current = datetime(2026, 9, 2, tzinfo=UTC)
        self._timers: list[tuple[datetime, TimerCallback, list[bool]]] = []

    def now(self) -> datetime:
        return self.current

    def async_call_at(
        self, callback: TimerCallback, when: datetime
    ) -> Callable[[], None]:
        active = [True]
        self._timers.append((when, callback, active))
        return lambda: active.__setitem__(0, False)

    async def async_advance(self, delta: timedelta) -> None:
        target = self.current + delta
        while due := sorted(
            (timer for timer in self._timers if timer[2][0] and timer[0] <= target),
            key=lambda timer: timer[0],
        ):
            when, callback, active = due[0]
            active[0] = False
            self.current = when
            result = callback()
            if inspect.isawaitable(result):
                await result
        self.current = target


@pytest.fixture
def fake_clock(hass) -> FakeClock:
    clock = FakeClock()
    hass.data.setdefault(DOMAIN, {})[DATA_SCHEDULER_FACTORY] = lambda hass: clock
    hass.data[DOMAIN]["now"] = clock.now
    return clock


async def _set_interval(hass, entry, interval: str) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "schedule"}
    )
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_INTERVAL: interval}
    )
    await hass.async_block_till_done()


async def test_new_entry_uses_24h_default_and_measures_immediately(hass) -> None:
    """Finishing setup starts one measurement and stores the default preset."""
    entry = await async_configure_kirov_entry(hass)

    assert entry.data[CONF_INTERVAL] == "24h"
    assert entry.runtime_data.measurement is not None
    assert entry.runtime_data.schedule_baseline == entry.runtime_data.last_success


async def test_options_flow_offers_only_supported_schedule_presets(hass) -> None:
    """Schedule options expose the seven product presets with 24h selected."""
    entry = await async_configure_kirov_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {"schedule", "city"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "schedule"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "schedule"
    field, validator = next(iter(result["data_schema"].schema.items()))
    assert field.default() == "24h"
    assert tuple(validator.config["options"]) == SCHEDULE_INTERVALS


@pytest.mark.parametrize(
    ("preset", "duration"),
    [
        ("30m", timedelta(minutes=30)),
        ("1h", timedelta(hours=1)),
        ("3h", timedelta(hours=3)),
        ("6h", timedelta(hours=6)),
        ("12h", timedelta(hours=12)),
        ("24h", timedelta(hours=24)),
    ],
)
async def test_each_enabled_interval_runs_only_when_due(
    hass, fake_clock: FakeClock, preset: str, duration: timedelta
) -> None:
    """Every enabled preset waits its full duration after first success."""
    phases = 0

    def runner(server: str, port: int, reverse: bool) -> float:
        nonlocal phases
        phases += 1
        return 50.0

    hass.data[DOMAIN][DATA_RUNNER] = runner
    entry = await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))
    assert phases == 2

    await _set_interval(hass, entry, preset)
    await fake_clock.async_advance(duration - timedelta(seconds=1))
    assert phases == 2
    await fake_clock.async_advance(timedelta(seconds=1))
    assert phases == 4


async def test_off_disables_automatic_runs_but_keeps_button(
    hass, fake_clock: FakeClock
) -> None:
    """The off preset cancels timers without removing manual measurement."""
    entry = await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))

    await _set_interval(hass, entry, "off")
    previous_success = entry.runtime_data.last_success
    await fake_clock.async_advance(timedelta(days=30))

    assert entry.runtime_data.last_success == previous_success
    assert hass.states.get("button.internetspeedru_run_measurement") is not None


async def test_restart_before_due_keeps_the_remaining_delay(
    hass, fake_clock: FakeClock
) -> None:
    """Reloading an entry does not restart the interval from zero."""
    phases = 0

    def runner(server: str, port: int, reverse: bool) -> float:
        nonlocal phases
        phases += 1
        return 50.0

    hass.data[DOMAIN][DATA_RUNNER] = runner
    entry = await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))
    await fake_clock.async_advance(timedelta(hours=10))

    assert await hass.config_entries.async_reload(entry.entry_id)
    await fake_clock.async_advance(timedelta(hours=13, minutes=59))
    assert phases == 2
    await fake_clock.async_advance(timedelta(minutes=1))
    assert phases == 4


async def test_restart_after_due_runs_once_immediately(
    hass, fake_clock: FakeClock
) -> None:
    """An entry restored after downtime catches up with one due attempt."""
    phases = 0

    def runner(server: str, port: int, reverse: bool) -> float:
        nonlocal phases
        phases += 1
        return 50.0

    hass.data[DOMAIN][DATA_RUNNER] = runner
    entry = await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))
    assert await hass.config_entries.async_unload(entry.entry_id)
    await fake_clock.async_advance(timedelta(hours=25))

    assert await hass.config_entries.async_setup(entry.entry_id)
    await fake_clock.async_advance(timedelta(0))
    assert phases == 4


async def test_successful_manual_run_resets_the_next_automatic_due_time(
    hass, fake_clock: FakeClock
) -> None:
    """A successful button run starts a fresh full interval."""
    phases = 0

    def runner(server: str, port: int, reverse: bool) -> float:
        nonlocal phases
        phases += 1
        return 50.0

    hass.data[DOMAIN][DATA_RUNNER] = runner
    await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))
    await fake_clock.async_advance(timedelta(hours=10))
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.internetspeedru_run_measurement"},
        blocking=True,
    )
    assert phases == 4

    await fake_clock.async_advance(timedelta(hours=23, minutes=59))
    assert phases == 4
    await fake_clock.async_advance(timedelta(minutes=1))
    assert phases == 6


async def test_failed_manual_run_does_not_move_the_automatic_due_time(
    hass, fake_clock: FakeClock
) -> None:
    """A failed button run leaves the prior schedule baseline intact."""
    entry = await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))
    original_baseline = entry.runtime_data.schedule_baseline
    await fake_clock.async_advance(timedelta(hours=10))

    async def unavailable(server: str, port: int) -> float:
        raise OSError

    entry.runtime_data.probe = unavailable
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.internetspeedru_run_measurement"},
            blocking=True,
        )
    assert entry.runtime_data.schedule_baseline == original_baseline

    async def available(server: str, port: int) -> float:
        return 12.0

    entry.runtime_data.probe = available
    await fake_clock.async_advance(timedelta(hours=14))
    assert entry.runtime_data.status.value == "success"
    assert entry.runtime_data.last_success == fake_clock.now()


async def test_shorter_overdue_interval_runs_now_and_longer_waits_remainder(
    hass, fake_clock: FakeClock
) -> None:
    """Interval changes recalculate due time from the existing baseline."""
    phases = 0

    def runner(server: str, port: int, reverse: bool) -> float:
        nonlocal phases
        phases += 1
        return 50.0

    hass.data[DOMAIN][DATA_RUNNER] = runner
    entry = await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))
    await fake_clock.async_advance(timedelta(hours=2))

    await _set_interval(hass, entry, "3h")
    await fake_clock.async_advance(timedelta(minutes=59))
    assert phases == 2
    await fake_clock.async_advance(timedelta(minutes=1))
    assert phases == 4

    await fake_clock.async_advance(timedelta(hours=2))
    await _set_interval(hass, entry, "1h")
    await fake_clock.async_advance(timedelta(0))
    assert phases == 6


async def test_failed_scheduled_run_has_no_early_retry(
    hass, fake_clock: FakeClock
) -> None:
    """A scheduled failure waits the same ordinary interval before retrying."""
    entry = await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))
    await _set_interval(hass, entry, "30m")

    async def unavailable(server: str, port: int) -> float:
        raise OSError

    entry.runtime_data.probe = unavailable
    await fake_clock.async_advance(timedelta(minutes=30))
    failed_at = entry.runtime_data.last_attempt
    assert entry.runtime_data.status.value == "error"

    await fake_clock.async_advance(timedelta(minutes=29, seconds=59))
    assert entry.runtime_data.last_attempt == failed_at
    await fake_clock.async_advance(timedelta(seconds=1))
    assert entry.runtime_data.last_attempt == fake_clock.now()


async def test_scheduled_overlap_is_skipped_without_queueing(
    hass, fake_clock: FakeClock
) -> None:
    """A due timer advances normally when a manual measurement owns the slot."""
    entry = await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))
    await _set_interval(hass, entry, "30m")
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_probe(server: str, port: int) -> float:
        started.set()
        await release.wait()
        return 12.0

    entry.runtime_data.probe = blocked_probe
    manual = asyncio.create_task(entry.runtime_data.async_measure())
    await started.wait()
    await fake_clock.async_advance(timedelta(minutes=30))
    assert not manual.done()

    release.set()
    await manual
    completed_at = entry.runtime_data.last_success
    await fake_clock.async_advance(timedelta(minutes=29, seconds=59))
    assert entry.runtime_data.last_success == completed_at
    await fake_clock.async_advance(timedelta(seconds=1))
    assert entry.runtime_data.last_success == fake_clock.now()


async def test_scheduled_run_claims_the_slot_before_persistence(
    hass, fake_clock: FakeClock
) -> None:
    """A manual request cannot slip in while a due attempt is being persisted."""

    class GateStore:
        def __init__(self) -> None:
            self.state = None
            self.block_next = False
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def async_load(self):
            return self.state

        async def async_save(self, state) -> None:
            if self.block_next:
                self.block_next = False
                self.entered.set()
                await self.release.wait()
            self.state = state

    store = GateStore()
    hass.data[DOMAIN][DATA_STATE_STORE_FACTORY] = lambda hass, entry_id: store
    entry = await async_configure_kirov_entry(hass)
    await fake_clock.async_advance(timedelta(0))
    await _set_interval(hass, entry, "30m")

    store.block_next = True
    scheduled = asyncio.create_task(fake_clock.async_advance(timedelta(minutes=30)))
    await store.entered.wait()
    assert entry.runtime_data.running

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.internetspeedru_run_measurement"},
            blocking=True,
        )

    store.release.set()
    await scheduled
    assert entry.runtime_data.status.value == "success"
