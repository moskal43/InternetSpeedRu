"""Iperf3 system-boundary adapter tests."""

from types import SimpleNamespace

from custom_components.internet_speed_ru.const import (
    IPERF3_DURATION,
    IPERF3_STREAMS,
)
from custom_components.internet_speed_ru.iperf import run_iperf_phase


def test_iperf_adapter_uses_the_fixed_tcp_profile(monkeypatch) -> None:
    """The external client always receives the v0.1 throughput profile."""
    clients = []

    class FakeClient:
        def __init__(self) -> None:
            clients.append(self)

        def run(self):
            return SimpleNamespace(
                error=None,
                received_Mbps=123.5,
                sent_Mbps=45.0,
            )

    monkeypatch.setattr(
        "custom_components.internet_speed_ru.iperf.iperf3.Client",
        FakeClient,
    )

    assert run_iperf_phase("server.example", 5201, True) == 123.5
    assert vars(clients[0]) == {
        "server_hostname": "server.example",
        "port": 5201,
        "protocol": "tcp",
        "duration": IPERF3_DURATION,
        "num_streams": IPERF3_STREAMS,
        "reverse": True,
    }
