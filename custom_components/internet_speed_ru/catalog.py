"""Validated server catalog for InternetSpeedRu."""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import yaml

_HOSTNAME_PATTERN = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?",
    re.IGNORECASE,
)


class InvalidCatalogError(ValueError):
    """Raised when a catalog is empty or contains invalid entries."""


@dataclass(frozen=True, slots=True)
class CatalogServer:
    """One selectable public Iperf3 server."""

    city: str
    provider: str
    hostname: str
    ports: tuple[int, ...]


def _upstream_ports(value: object) -> tuple[int, ...]:
    """Parse the upstream single-port or inclusive range representation."""
    if isinstance(value, bool):
        raise InvalidCatalogError("upstream port is invalid")
    if isinstance(value, int):
        return (value,)
    if not isinstance(value, str):
        raise InvalidCatalogError("upstream port is invalid")
    parts = value.split("-")
    try:
        if len(parts) == 1:
            return (int(parts[0]),)
        if len(parts) == 2:
            start, end = (int(part) for part in parts)
            if start > end:
                raise InvalidCatalogError("upstream port range is invalid")
            return tuple(range(start, end + 1))
    except ValueError as err:
        raise InvalidCatalogError("upstream port is invalid") from err
    raise InvalidCatalogError("upstream port is invalid")


def parse_upstream_catalog(payload: str) -> ServerCatalog:
    """Fully validate the upstream list.yml payload as one catalog."""
    try:
        raw_entries = yaml.safe_load(payload)
    except yaml.YAMLError as err:
        raise InvalidCatalogError("upstream YAML is invalid") from err
    if not isinstance(raw_entries, list):
        raise InvalidCatalogError("upstream catalog must be a list")

    entries: list[CatalogServer] = []
    for raw in raw_entries:
        if not isinstance(raw, Mapping):
            raise InvalidCatalogError("upstream entry has an invalid shape")
        try:
            name = raw["Name"]
            city = raw["City"]
            hostname = raw["address"]
            port = raw["port"]
        except KeyError as err:
            raise InvalidCatalogError("upstream entry is missing a field") from err
        if not isinstance(name, str) or not isinstance(city, str):
            raise InvalidCatalogError("upstream name and city must be strings")
        suffix = f" {city}"
        provider = name[: -len(suffix)] if name.endswith(suffix) else name
        entries.append(
            CatalogServer(
                city=city,
                provider=provider,
                hostname=hostname,
                ports=_upstream_ports(port),
            )
        )
    return ServerCatalog(entries)


def _validated_server(raw: Mapping[str, Any] | CatalogServer) -> CatalogServer:
    if isinstance(raw, CatalogServer):
        server = raw
    else:
        try:
            ports = tuple(raw["ports"])
            server = CatalogServer(
                city=raw["city"],
                provider=raw["provider"],
                hostname=raw["hostname"],
                ports=ports,
            )
        except (KeyError, TypeError) as err:
            raise InvalidCatalogError("catalog entry has an invalid shape") from err

    if not all(
        isinstance(value, str) and value.strip() == value and value
        for value in (server.city, server.provider, server.hostname)
    ):
        raise InvalidCatalogError("catalog text fields must be non-empty strings")
    if _HOSTNAME_PATTERN.fullmatch(server.hostname) is None:
        raise InvalidCatalogError("catalog hostname is invalid")
    if not server.ports or any(
        not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535
        for port in server.ports
    ):
        raise InvalidCatalogError("catalog ports are invalid")
    if len(server.ports) != len(set(server.ports)):
        raise InvalidCatalogError("catalog entry contains duplicate ports")

    return CatalogServer(
        city=server.city,
        provider=server.provider,
        hostname=server.hostname.lower(),
        ports=tuple(sorted(server.ports)),
    )


class ServerCatalog:
    """A fully validated catalog with cascade lookups."""

    def __init__(
        self,
        entries: Iterable[Mapping[str, Any] | CatalogServer],
    ) -> None:
        servers = tuple(_validated_server(entry) for entry in entries)
        if not servers:
            raise InvalidCatalogError("catalog must contain at least one server")

        hostnames = [server.hostname for server in servers]
        if len(hostnames) != len(set(hostnames)):
            raise InvalidCatalogError("catalog contains duplicate servers")

        self._servers = tuple(
            sorted(
                servers,
                key=lambda server: (
                    server.city.casefold(),
                    server.provider.casefold(),
                    server.hostname,
                ),
            )
        )

    @property
    def servers(self) -> tuple[CatalogServer, ...]:
        """Return every server in deterministic cascade order."""
        return self._servers

    @property
    def cities(self) -> tuple[str, ...]:
        """Return the available cities."""
        return tuple(dict.fromkeys(server.city for server in self._servers))

    def providers(self, city: str) -> tuple[str, ...]:
        """Return providers available in one city."""
        return tuple(
            dict.fromkeys(
                server.provider for server in self._servers if server.city == city
            )
        )

    def servers_for(self, city: str, provider: str) -> tuple[CatalogServer, ...]:
        """Return servers available for one city and provider."""
        return tuple(
            server
            for server in self._servers
            if server.city == city and server.provider == provider
        )

    def get(self, hostname: str) -> CatalogServer:
        """Resolve one server by its catalog hostname."""
        normalized = hostname.lower()
        for server in self._servers:
            if server.hostname == normalized:
                return server
        raise KeyError(hostname)


# These endpoints were independently TCP-checked from the project workspace on
# 2026-09-02. The compact fallback intentionally spans European Russia, Siberia,
# and the Far East and is maintained separately from the upstream runtime catalog.
FALLBACK_VERIFIED_ON = date(2026, 9, 2)
FALLBACK_CATALOG = ServerCatalog(
    (
        CatalogServer(
            city="Киров",
            provider="ЭР-Телеком",
            hostname="st.kirov.ertelecom.ru",
            ports=tuple(range(5201, 5210)),
        ),
        CatalogServer(
            city="Москва",
            provider="HOSTKEY",
            hostname="spd-rudp.hostkey.ru",
            ports=tuple(range(5201, 5210)),
        ),
        CatalogServer(
            city="Санкт-Петербург",
            provider="ЭР-Телеком",
            hostname="st.spb.ertelecom.ru",
            ports=tuple(range(5201, 5210)),
        ),
        CatalogServer(
            city="Волгоград",
            provider="TTK",
            hostname="speed-vgd.vtt.net",
            ports=(5201,),
        ),
        CatalogServer(
            city="Краснодар",
            provider="MTS",
            hostname="kndst.st.mtsws.net",
            ports=(3333,),
        ),
        CatalogServer(
            city="Новосибирск",
            provider="ЭР-Телеком",
            hostname="st.nsk.ertelecom.ru",
            ports=tuple(range(5201, 5210)),
        ),
        CatalogServer(
            city="Иркутск",
            provider="ЭР-Телеком",
            hostname="st.irkutsk.ertelecom.ru",
            ports=tuple(range(5201, 5210)),
        ),
        CatalogServer(
            city="Якутск",
            provider="MTS",
            hostname="yktst.st.mtsws.net",
            ports=(3333,),
        ),
    )
)


def ordered_ports(server: CatalogServer, last_good_port: int | None) -> Sequence[int]:
    """Put the last working port first, then try the rest in ascending order."""
    if last_good_port not in server.ports:
        return server.ports
    return (last_good_port, *(port for port in server.ports if port != last_good_port))
