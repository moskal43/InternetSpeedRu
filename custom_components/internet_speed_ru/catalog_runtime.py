"""Runtime catalog loading with validated cache and fallback precedence."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from logging import getLogger
from typing import Protocol, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .catalog import (
    FALLBACK_CATALOG,
    InvalidCatalogError,
    ServerCatalog,
    parse_upstream_catalog,
)
from .const import (
    CATALOG_REFRESH_INTERVAL,
    CATALOG_URL,
    DATA_CATALOG_PROVIDER,
    DOMAIN,
)

_LOGGER = getLogger(__name__)
_CATALOG_STORAGE_KEY = f"{DOMAIN}.catalog"
_CATALOG_STORAGE_VERSION = 1

type CatalogFetcher = Callable[[], Awaitable[str]]
type Clock = Callable[[], datetime]


class CatalogSource(StrEnum):
    """Observable origin of the active validated catalog."""

    REMOTE = "remote"
    CACHE = "cache"
    FALLBACK = "fallback"


class CatalogUnavailableError(Exception):
    """Raised when no validated catalog source is available."""


@dataclass(frozen=True, slots=True)
class CatalogSelection:
    """One validated catalog and its origin."""

    catalog: ServerCatalog
    source: CatalogSource
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CatalogCache:
    """Last refresh attempt and optional last-known-good catalog."""

    catalog: ServerCatalog | None
    fetched_at: datetime | None
    last_attempt: datetime | None


class CatalogStore(Protocol):
    """Persistent boundary for the last-known-good catalog."""

    async def async_load(self) -> CatalogCache | None:
        """Load cached catalog state."""

    async def async_save(self, value: CatalogCache) -> None:
        """Replace cached catalog state."""


class CatalogProviderProtocol(Protocol):
    """Validated catalog boundary consumed by config-entry orchestration."""

    async def async_catalog(self) -> CatalogSelection:
        """Return the best currently available catalog."""


class CatalogProvider:
    """Choose remote, cache, or fallback without exposing source mechanics."""

    def __init__(
        self,
        fetch: CatalogFetcher,
        store: CatalogStore,
        *,
        fallback: ServerCatalog | None = FALLBACK_CATALOG,
        now: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self._fetch = fetch
        self._store = store
        self._fallback = fallback
        self._now = now
        self._state: CatalogCache | None = None
        self._selection: CatalogSelection | None = None
        self._loaded = False
        self._lock = asyncio.Lock()

    async def async_catalog(self) -> CatalogSelection:
        """Return the best catalog, attempting remote no more than daily."""
        async with self._lock:
            if not self._loaded:
                try:
                    self._state = await self._store.async_load()
                except Exception as err:  # storage must not defeat the fallback
                    _LOGGER.warning("Unable to load catalog cache: %s", err)
                self._loaded = True

            now = self._now()
            if (
                self._state is not None
                and self._state.last_attempt is not None
                and now - self._state.last_attempt < CATALOG_REFRESH_INTERVAL
            ):
                return self._local_selection()

            previous = self._state or CatalogCache(None, None, None)
            attempted = CatalogCache(
                previous.catalog,
                previous.fetched_at,
                now,
            )
            try:
                catalog = parse_upstream_catalog(await self._fetch())
            except Exception as err:
                _LOGGER.warning("Unable to refresh server catalog: %s", err)
                self._state = attempted
                self._selection = None
                await self._safe_save(attempted)
                return self._local_selection()

            self._state = CatalogCache(catalog, now, now)
            await self._safe_save(self._state)
            self._selection = CatalogSelection(catalog, CatalogSource.REMOTE, now)
            return self._selection

    def _local_selection(self) -> CatalogSelection:
        if self._selection is not None:
            return self._selection
        if self._state is not None and self._state.catalog is not None:
            self._selection = CatalogSelection(
                self._state.catalog,
                CatalogSource.CACHE,
                self._state.fetched_at,
            )
            return self._selection
        if self._fallback is not None:
            self._selection = CatalogSelection(
                self._fallback,
                CatalogSource.FALLBACK,
                None,
            )
            return self._selection
        raise CatalogUnavailableError

    async def _safe_save(self, value: CatalogCache) -> None:
        try:
            await self._store.async_save(value)
        except Exception as err:
            _LOGGER.warning("Unable to save catalog cache: %s", err)


class HomeAssistantCatalogStore:
    """Store only a normalized validated catalog in Home Assistant storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, object]] = Store(
            hass,
            _CATALOG_STORAGE_VERSION,
            _CATALOG_STORAGE_KEY,
        )

    async def async_load(self) -> CatalogCache | None:
        """Load the cache, discarding malformed content as a whole."""
        raw = await self._store.async_load()
        if raw is None:
            return None
        try:
            entries = raw.get("catalog")
            catalog = ServerCatalog(entries) if isinstance(entries, list) else None
            return CatalogCache(
                catalog,
                _stored_datetime(raw.get("fetched_at")),
                _stored_datetime(raw.get("last_attempt")),
            )
        except (InvalidCatalogError, TypeError, ValueError) as err:
            _LOGGER.warning("Ignoring invalid catalog cache: %s", err)
            return None

    async def async_save(self, value: CatalogCache) -> None:
        """Persist normalized servers and refresh timestamps."""
        catalog = None
        if value.catalog is not None:
            catalog = [
                {
                    "city": server.city,
                    "provider": server.provider,
                    "hostname": server.hostname,
                    "ports": list(server.ports),
                }
                for server in value.catalog.servers
            ]
        await self._store.async_save(
            {
                "catalog": catalog,
                "fetched_at": _dump_datetime(value.fetched_at),
                "last_attempt": _dump_datetime(value.last_attempt),
            }
        )


def _stored_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("catalog timestamp must be a string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("catalog timestamp must include a timezone")
    return parsed


def _dump_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def create_catalog_provider(hass: HomeAssistant) -> CatalogProvider:
    """Create the production provider around Home Assistant HTTP and storage."""
    session = async_get_clientsession(hass)

    async def fetch() -> str:
        async with session.get(CATALOG_URL) as response:
            response.raise_for_status()
            return await response.text()

    return CatalogProvider(fetch, HomeAssistantCatalogStore(hass))


def catalog_provider(hass: HomeAssistant) -> CatalogProvider:
    """Return the one catalog provider shared by every integration flow."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    provider = domain_data.get(DATA_CATALOG_PROVIDER)
    if provider is None:
        provider = create_catalog_provider(hass)
        domain_data[DATA_CATALOG_PROVIDER] = provider
    return cast(CatalogProvider, provider)
