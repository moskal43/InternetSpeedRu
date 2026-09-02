"""Constants for InternetSpeedRu."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "internet_speed_ru"
NAME = "InternetSpeedRu"
DATA_CATALOG_PROVIDER = "catalog_provider"
DATA_NOW = "now"
DATA_PROBE = "probe"
DATA_RUNNER = "runner"
DATA_SCHEDULER_FACTORY = "scheduler_factory"

CATALOG_URL = (
    "https://raw.githubusercontent.com/itdoginfo/russian-iperf3-servers/main/list.yml"
)
CATALOG_REFRESH_INTERVAL = timedelta(hours=24)

CONF_CITY = "city"
CONF_PROVIDER = "provider"
CONF_SERVER = "server"
CONF_INTERVAL = "interval"

DEFAULT_INTERVAL = "24h"
SCHEDULE_INTERVALS = ("off", "30m", "1h", "3h", "6h", "12h", "24h")
SCHEDULE_DURATIONS = {
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "3h": timedelta(hours=3),
    "6h": timedelta(hours=6),
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
}

PLATFORMS = (Platform.SENSOR, Platform.BUTTON)

IPERF3_DURATION = 10
IPERF3_STREAMS = 4
TCP_PROBE_COUNT = 3
TCP_PROBE_TIMEOUT = 5.0
