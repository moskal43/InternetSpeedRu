"""Public server catalog behavior tests."""

from datetime import date
from pathlib import Path

import pytest

from custom_components.internet_speed_ru.catalog import (
    FALLBACK_CATALOG,
    FALLBACK_VERIFIED_ON,
    InvalidCatalogError,
    ServerCatalog,
)


def test_fallback_is_small_distributed_and_dated() -> None:
    """The release fallback is independently maintained and includes Kirov."""
    assert 6 <= len(FALLBACK_CATALOG.servers) <= 10
    assert "Киров" in FALLBACK_CATALOG.cities
    assert len(FALLBACK_CATALOG.cities) == len(FALLBACK_CATALOG.servers)
    assert FALLBACK_VERIFIED_ON == date(2026, 9, 2)


@pytest.mark.parametrize(
    "entries",
    [
        [],
        [
            {
                "city": "Киров",
                "provider": "ЭР-Телеком",
                "hostname": "not a hostname",
                "ports": [5201],
            }
        ],
        [
            {
                "city": "Киров",
                "provider": "ЭР-Телеком",
                "hostname": "st.kirov.ertelecom.ru",
                "ports": [5201],
            },
            {
                "city": "Киров",
                "provider": "Другой",
                "hostname": "st.kirov.ertelecom.ru",
                "ports": [5202],
            },
        ],
    ],
)
def test_catalog_rejects_invalid_or_duplicate_entries(entries) -> None:
    """An invalid catalog can never become a source of selectable servers."""
    with pytest.raises(InvalidCatalogError):
        ServerCatalog(entries)


def test_full_upstream_catalog_is_not_vendored() -> None:
    """The upstream runtime dataset is absent from source and test fixtures."""
    project_root = Path(__file__).parent.parent
    assert not list(project_root.glob("**/list.yml"))
