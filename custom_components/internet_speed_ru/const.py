"""Constants for InternetSpeedRu."""

from homeassistant.const import Platform

DOMAIN = "internet_speed_ru"
NAME = "InternetSpeedRu"

CONF_CITY = "city"
CONF_PROVIDER = "provider"
CONF_SERVER = "server"

PLATFORMS = (Platform.SENSOR, Platform.BUTTON)

IPERF3_SERVER = "st.kirov.ertelecom.ru"
IPERF3_PORT = 5201
IPERF3_DURATION = 10
IPERF3_STREAMS = 4
TCP_PROBE_COUNT = 3
TCP_PROBE_TIMEOUT = 5.0
