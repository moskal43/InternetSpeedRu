# InternetSpeedRu

InternetSpeedRu — пользовательская интеграция Home Assistant для измерения
качества интернет-соединения через публичные Iperf3-серверы в России.

> [!WARNING]
> Iperf3 выполняет активные сетевые тесты. Каждый замер может полностью загрузить
> download и upload примерно на 10 секунд в каждом направлении.

## Требования

- Home Assistant OS;
- Home Assistant Core 2026.8 или новее;
- HACS.

Другие типы установки Home Assistant пока поддерживаются в режиме best effort.

## Установка через HACS

1. Откройте HACS и добавьте
   `https://github.com/moskal43/InternetSpeedRu` как пользовательский репозиторий
   категории **Integration**.
2. Установите InternetSpeedRu.
3. Перезапустите Home Assistant.
4. Откройте **Настройки → Устройства и службы → Добавить интеграцию** и выберите
   InternetSpeedRu.

Интеграция допускает только один config entry. На первом шаге Config Flow
показывает предупреждение о сетевой нагрузке до создания записи.

## English

InternetSpeedRu is a custom Home Assistant integration for measuring an internet
connection through public Iperf3 servers in Russia. It requires Home Assistant
Core 2026.8+ and is installed as a HACS custom integration. Iperf3 tests can
saturate both download and upload for about 10 seconds per direction.

## Разработка

```console
UV_CACHE_DIR=/private/tmp/internetspeedru-uv-cache uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Лицензия

[MIT](LICENSE)
