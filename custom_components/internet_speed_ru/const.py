"""Constants for InternetSpeedRu."""

from datetime import timedelta
from enum import StrEnum
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

DOMAIN = "internet_speed_ru"
NAME = "InternetSpeedRu"
DATA_CATALOG_PROVIDER = "catalog_provider"
DATA_NOW = "now"
DATA_PROBE = "probe"
DATA_RUNNER = "runner"
DATA_SCHEDULER_FACTORY = "scheduler_factory"
DATA_STATE_STORE_FACTORY = "state_store_factory"

CATALOG_URL = (
    "https://raw.githubusercontent.com/itdoginfo/russian-iperf3-servers/main/list.yml"
)
CATALOG_REFRESH_INTERVAL = timedelta(hours=24)

CONF_CITY = "city"
CONF_AUTO = "auto"
CONF_PROVIDER = "provider"
CONF_SERVER = "server"
CONF_INTERVAL = "interval"


class ScheduleInterval(StrEnum):
    """Supported automatic measurement presets."""

    OFF = "off"
    MINUTES_30 = "30m"
    HOUR_1 = "1h"
    HOURS_3 = "3h"
    HOURS_6 = "6h"
    HOURS_12 = "12h"
    HOURS_24 = "24h"


DEFAULT_INTERVAL = ScheduleInterval.HOURS_24.value
SCHEDULE_INTERVALS = tuple(interval.value for interval in ScheduleInterval)
SCHEDULE_DURATIONS = {
    ScheduleInterval.OFF: None,
    ScheduleInterval.MINUTES_30: timedelta(minutes=30),
    ScheduleInterval.HOUR_1: timedelta(hours=1),
    ScheduleInterval.HOURS_3: timedelta(hours=3),
    ScheduleInterval.HOURS_6: timedelta(hours=6),
    ScheduleInterval.HOURS_12: timedelta(hours=12),
    ScheduleInterval.HOURS_24: timedelta(hours=24),
}


def effective_interval(entry: ConfigEntry[Any]) -> str:
    """Resolve an entry's configured preset with migration-safe precedence."""
    value: object = entry.options.get(
        CONF_INTERVAL,
        entry.data.get(CONF_INTERVAL, DEFAULT_INTERVAL),
    )
    if not isinstance(value, str):
        return DEFAULT_INTERVAL
    try:
        return ScheduleInterval(value).value
    except ValueError:
        return DEFAULT_INTERVAL


def effective_auto(entry: ConfigEntry[Any]) -> bool:
    """Resolve Auto while preserving manual behavior for older entries."""
    value = entry.options.get(CONF_AUTO, entry.data.get(CONF_AUTO, False))
    return value if isinstance(value, bool) else False


PLATFORMS = (Platform.SENSOR, Platform.BUTTON)

IPERF3_DURATION = 10
IPERF3_STREAMS = 4
TCP_PROBE_COUNT = 3
TCP_PROBE_TIMEOUT = 5.0
AUTO_PROBE_CONCURRENCY = 5
AUTO_CANDIDATE_COUNT = 3
