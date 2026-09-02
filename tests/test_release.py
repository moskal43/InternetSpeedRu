"""Public release artifact contract tests."""

import json
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
RELEASE_VERSION = "0.1.1"


def test_release_metadata_and_license_are_consistent() -> None:
    """The public package advertises one MIT-licensed release version."""
    manifest = json.loads(
        (PROJECT_ROOT / "custom_components/internet_speed_ru/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")

    assert manifest["version"] == RELEASE_VERSION
    assert project["version"] == RELEASE_VERSION
    assert project["license"] == "MIT"
    assert license_text.startswith("MIT License\n")


def test_primary_readme_documents_the_supported_user_path() -> None:
    """The release README covers every supported setup and operating choice."""
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    required_sections = (
        "## Гарантированная платформа",
        "## Установка через HACS custom repository",
        "## Настройка через Config Flow",
        "## Настройки через Options Flow",
        "## Режимы Auto и manual",
        "## Интервалы запуска",
        "## Сущности",
        "## Диагностика",
        "## Нагрузка Iperf3",
        "## Каталог серверов",
        "## Миграция с официальной Iperf3-интеграции",  # noqa: RUF001
        "## English summary",
    )
    for section in required_sections:
        assert section in readme

    assert "Home Assistant OS" in readme
    assert "Home Assistant Core 2026.8+" in readme
    assert "best effort" in readme
    assert "docs/migration.md" in readme


def test_migration_guide_requires_an_explicit_manual_cutover() -> None:
    """Migration remains reversible and makes no history-transfer promise."""
    guide = (PROJECT_ROOT / "docs/migration.md").read_text(encoding="utf-8")

    required_steps = (
        "параллельно",
        "dashboard",
        "automation",
        "configuration.yaml",
        "Recorder history",
        "не переносится",
    )
    for step in required_steps:
        assert step in guide
