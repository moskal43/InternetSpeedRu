"""User-facing translation tests."""

from homeassistant.helpers import translation

DOMAIN = "internet_speed_ru"

EN_WARNING = (
    "InternetSpeedRu runs active tests through a public Iperf3 server. "
    "Each measurement can saturate download and upload for about 10 seconds "
    "per direction. Automatic measurements default to once every 24 hours "
    "and can be changed or disabled later."
)
RU_WARNING = (
    "InternetSpeedRu выполняет активные тесты через публичный Iperf3-сервер. "
    "Каждый замер может полностью загрузить download и upload примерно на 10 "
    "секунд в каждом направлении. Автоматические замеры по умолчанию выполняются "
    "раз в 24 часа; позже расписание можно изменить или отключить."
)


async def test_config_flow_warning_is_available_in_english_and_russian(hass) -> None:
    """The setup warning is complete in both supported languages."""
    english = await translation.async_get_translations(
        hass,
        "en",
        "config",
        integrations={DOMAIN},
    )
    russian = await translation.async_get_translations(
        hass,
        "ru",
        "config",
        integrations={DOMAIN},
    )

    description_key = f"component.{DOMAIN}.config.step.user.description"
    title_key = f"component.{DOMAIN}.config.step.user.title"

    assert english[title_key] == "Set up InternetSpeedRu"
    assert english[description_key] == EN_WARNING
    assert russian[title_key] == "Настройка InternetSpeedRu"
    assert russian[description_key] == RU_WARNING

    error_key = f"component.{DOMAIN}.config.error.catalog_unavailable"
    assert english[error_key] == (
        "No valid server catalog is available. Check the connection and try again."
    )
    assert russian[error_key] == (
        "Нет доступного валидного каталога серверов. "
        "Проверьте подключение и повторите попытку."
    )
