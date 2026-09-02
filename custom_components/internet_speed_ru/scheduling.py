"""Clock-driven automatic measurement scheduling."""

import asyncio
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from homeassistant.core import HassJob, HomeAssistant
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import SCHEDULE_DURATIONS, ScheduleInterval
from .runtime import MeasurementError

if TYPE_CHECKING:
    from .runtime import InternetSpeedRuRuntime

type TimerCallback = Callable[[], Coroutine[Any, Any, None]]


class ClockScheduler(Protocol):
    """Time and one-shot timer boundary used by scheduling orchestration."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC time."""

    def async_call_at(
        self, callback: TimerCallback, when: datetime
    ) -> Callable[[], None]:
        """Call an async callback once at the requested time."""


class HomeAssistantClockScheduler:
    """Production clock/timer adapter backed by Home Assistant helpers."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def now(self) -> datetime:
        """Return Home Assistant's current UTC time."""
        return dt_util.utcnow()

    def async_call_at(
        self, callback: TimerCallback, when: datetime
    ) -> Callable[[], None]:
        """Register a one-shot Home Assistant timer."""
        if when <= self.now():
            task: asyncio.Task[Any] = self._hass.async_create_task(
                callback(),
                "InternetSpeedRu scheduled measurement",
            )

            def cancel() -> None:
                task.cancel()

            return cancel

        async def async_run(_now: datetime) -> None:
            await callback()

        return async_track_point_in_utc_time(
            self._hass,
            HassJob(
                async_run,
                "InternetSpeedRu scheduled measurement",
                cancel_on_shutdown=True,
            ),
            when,
        )


class MeasurementSchedule:
    """Own one predictable automatic schedule for a config entry."""

    def __init__(
        self,
        runtime: InternetSpeedRuRuntime,
        clock: ClockScheduler,
        interval: str,
    ) -> None:
        self._runtime = runtime
        self._clock = clock
        self._interval = ScheduleInterval(interval)
        self._cancel_timer: Callable[[], None] | None = None
        self._cancelled = False

    @property
    def interval(self) -> str:
        """Return the configured schedule preset."""
        return self._interval.value

    def start(self) -> None:
        """Arm the initial or restored schedule."""
        self.recalculate()

    def update_interval(self, interval: str) -> None:
        """Apply a preset immediately against the persisted baseline."""
        self._interval = ScheduleInterval(interval)
        self.recalculate()

    def recalculate(self) -> None:
        """Replace the active timer with the one implied by current state."""
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None
        if self._cancelled:
            return
        duration = SCHEDULE_DURATIONS[self._interval]
        if duration is None:
            return
        baseline = self._runtime.schedule_baseline
        due = self._clock.now() if baseline is None else baseline + duration
        if due < self._clock.now():
            due = self._clock.now()
        self._cancel_timer = self._clock.async_call_at(self._async_due, due)

    async def _async_due(self) -> None:
        self._cancel_timer = None
        attempt_time = self._clock.now()
        if self._runtime.running:
            await self._runtime.async_set_schedule_baseline(attempt_time)
            self.recalculate()
            return
        try:
            await self._runtime.async_measure(schedule_baseline=attempt_time)
        except MeasurementError:
            pass
        finally:
            self.recalculate()

    def cancel(self) -> None:
        """Prevent all future scheduled work."""
        self._cancelled = True
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None
