"""Constants for InternetSpeedRu."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "internet_speed_ru"
NAME = "InternetSpeedRu"
DATA_CATALOG_PROVIDER = "catalog_provider"

CATALOG_URL = (
    "https://raw.githubusercontent.com/itdoginfo/russian-iperf3-servers/main/list.yml"
)
CATALOG_REFRESH_INTERVAL = timedelta(hours=24)

CONF_CITY = "city"
CONF_PROVIDER = "provider"
CONF_SERVER = "server"

PLATFORMS = (Platform.SENSOR, Platform.BUTTON)

IPERF3_DURATION = 10
IPERF3_STREAMS = 4
TCP_PROBE_COUNT = 3
TCP_PROBE_TIMEOUT = 5.0
