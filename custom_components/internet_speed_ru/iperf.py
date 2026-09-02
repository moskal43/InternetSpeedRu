"""Blocking Iperf3 adapter for InternetSpeedRu."""

import math

import iperf3

from .const import IPERF3_DURATION, IPERF3_STREAMS


class InvalidIperfResultError(Exception):
    """Raised when Iperf3 did not return a usable throughput value."""


class IperfExecutionError(Exception):
    """Raised when Iperf3 reports that a phase failed."""


class IperfPreTransferError(IperfExecutionError):
    """Raised when Iperf3 fails before it starts transferring test data."""


_PRE_TRANSFER_ERRORS = (
    "unable to connect to server",
    "server is busy",
    "control connection",
    "control socket",
)


def run_iperf_phase(server: str, port: int, reverse: bool) -> float:
    """Run one fixed-profile TCP Iperf3 phase and return Mbit/s."""
    client = iperf3.Client()
    client.server_hostname = server
    client.port = port
    client.protocol = "tcp"
    client.duration = IPERF3_DURATION
    client.num_streams = IPERF3_STREAMS
    client.reverse = reverse

    result = client.run()
    if result is None:
        raise IperfExecutionError
    if result.error:
        if any(marker in result.error.lower() for marker in _PRE_TRANSFER_ERRORS):
            raise IperfPreTransferError
        raise IperfExecutionError

    value = result.received_Mbps if reverse else result.sent_Mbps
    if not isinstance(value, int | float) or not math.isfinite(value) or value < 0:
        raise InvalidIperfResultError

    return float(value)
