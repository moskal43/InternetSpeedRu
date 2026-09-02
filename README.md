# InternetSpeedRu

InternetSpeedRu — пользовательская интеграция Home Assistant для атомарных
замеров download, upload и latency через публичные Iperf3-серверы в России.
Она настраивается из интерфейса, сама выбирает доступный сервер или закрепляет
выбранный пользователем и не запускает несколько тяжёлых замеров одновременно.

## Гарантированная платформа

Гарантированный baseline версии `v0.1.0`:

- Home Assistant OS;
- Home Assistant Core 2026.8+;
- HACS.

Home Assistant Container, Supervised и Core Python installation допускаются
только в режиме **best effort**: они не входят в гарантированный support scope
`v0.1.0`. Home Assistant Core старше 2026.8 не поддерживается.

## Установка через HACS custom repository

1. Откройте HACS.
2. Откройте меню в правом верхнем углу и выберите **Custom repositories**.
3. Вставьте `https://github.com/moskal43/InternetSpeedRu`, выберите категорию
   **Integration** и нажмите **Add**.
4. Найдите InternetSpeedRu в HACS и нажмите **Download**.
5. Перезапустите Home Assistant.
6. Откройте **Настройки → Устройства и службы → Добавить интеграцию**, найдите
   InternetSpeedRu и пройдите Config Flow.

Публикация в стандартном каталоге HACS для установки не требуется.

## Настройка через Config Flow

При добавлении интеграции Config Flow предупреждает, что публичный Iperf3-сервер
и интернет-канал будут активно нагружены. Продолжение настройки означает
согласие на немедленный первый замер.

Далее можно оставить включённый по умолчанию Auto или выбрать manual. В manual
режиме город, провайдер и сервер выбираются последовательно из каталога; адрес
и порт вручную не вводятся. InternetSpeedRu допускает ровно один config entry.

Если удалённый каталог временно недоступен, настройка продолжится с последней
валидной cache-копией или встроенным fallback. Источник каталога показывается в
Config Flow. Если нет ни одного валидного источника, запись не создаётся.

## Настройки через Options Flow

Откройте **Настройки → Устройства и службы → InternetSpeedRu → Настроить**.
Options Flow позволяет:

- переключить Auto/manual и выбрать другой manual-сервер;
- установить интервал автоматических замеров или отключить расписание.

Смена режима или сервера запускает новый замер. Изменение только интервала не
создаёт лишний тест: срок пересчитывается от текущей точки расписания, и замер
запускается сразу лишь тогда, когда новый срок уже наступил.

## Режимы Auto и manual

**Auto** ранжирует доступные серверы лёгкими TCP connection probes и выбирает по
latency, а не по географической близости или пропускной способности. Ranking
обновляется перед первым замером после истечения 24 часов. Работающий сервер
меняется только при существенном улучшении (не менее 5 мс и 20%), а при его
недоступности интеграция может перейти к следующему ranked server до начала
передачи данных.

**Manual** закрепляет выбранный сервер. InternetSpeedRu автоматически пробует
его заявленные порты, начиная с последнего успешного, но никогда не переключает
manual-замер на другой сервер без ведома пользователя.

## Интервалы запуска

Доступны `off`, 30 минут, 1 час, 3 часа, 6 часов, 12 часов и 24 часа. По
умолчанию выбран интервал 24 часа. `off` отключает только расписание — кнопка
ручного запуска остаётся доступной.

После перезапуска Home Assistant замер выполняется только при наступившем сроке.
Успешный ручной замер переносит следующую автоматическую попытку на выбранный
интервал; неудачный ручной замер расписание не сдвигает. Специальных retry после
ошибки нет.

## Сущности

Один config entry создаёт одно устройство и пять стабильных сущностей:

- **Download** — последняя успешная входящая скорость в Mbit/s;
- **Upload** — последняя успешная исходящая скорость в Mbit/s;
- **Latency** — медиана трёх TCP connection probes, в миллисекундах;
- **Статус последнего замера** — `running`, `success` или `error`, время
  последней попытки/успеха, нормализованная ошибка и публичные сведения о сервере;
- **Запустить замер** — кнопка ручного запуска.

Download, upload и latency публикуются вместе только после успеха обеих
Iperf3-фаз на одном server/port. При ошибке числовые сущности сохраняют последний
полный результат, а статус объясняет сбой. Идентичность сущностей не зависит от
режима или сервера, поэтому смена точки не разрывает историю Recorder.

## Диагностика

В карточке интеграции откройте меню и выберите **Скачать диагностику**. Отчёт
содержит версию, режим, интервал, публичные metadata сервера, источник и возраст
каталога, время последней попытки/успеха, статус и нормализованный код ошибки.

Диагностика намеренно не содержит local/public IP пользователя, имя сетевого
интерфейса, DNS-результаты, сырой Iperf3 JSON или Recorder history.

## Нагрузка Iperf3

> [!WARNING]
> Каждый замер выполняет две последовательные TCP-фазы: около 10 секунд download
> и около 10 секунд upload, по 4 parallel streams. В это время тест способен
> полностью занять интернет-канал и повлиять на звонки, видео, игры и другие
> сетевые задачи.

Выбирайте редкий интервал или `off`, если канал ограничен. Не запускайте ручной
замер во время важного сетевого трафика. Повторное нажатие во время активного
замера возвращает ошибку busy и не ставится в очередь. При выгрузке интеграции
поздний результат отбрасывается, хотя уже начатая Iperf3-фаза может физически
завершиться.

## Каталог серверов

Upstream runtime source —
[`itdoginfo/russian-iperf3-servers/list.yml`](https://github.com/itdoginfo/russian-iperf3-servers/blob/main/list.yml).
InternetSpeedRu загружает его только во время работы, не чаще раза в 24 часа, и
использует лишь после полной валидации. Порядок источников: новый валидный remote
catalog → последняя валидная локальная cache-копия → компактный встроенный
fallback.

Полный upstream `list.yml` не commit'ится, не входит в source tree, HACS package
или GitHub release artifacts InternetSpeedRu. Runtime cache хранится только в
локальном storage конкретной установки Home Assistant.

## Миграция с официальной Iperf3-интеграции

Автоматической миграции нет. Безопасный порядок — установить InternetSpeedRu
параллельно, сравнить несколько замеров, вручную перевести dashboard и automation
на новые entity IDs и только затем удалить legacy YAML. Recorder history старых
сущностей не переносится. Полная пошаговая инструкция: [docs/migration.md](docs/migration.md).

## English summary

InternetSpeedRu is a HACS custom integration for atomic download, upload, and
TCP-latency measurements through public Iperf3 servers in Russia. The guaranteed
`v0.1.0` baseline is Home Assistant OS with Home Assistant Core 2026.8+; Container,
Supervised, and Core Python installations are best effort.

Add `https://github.com/moskal43/InternetSpeedRu` to HACS as a custom
**Integration**, download it, restart Home Assistant, and add InternetSpeedRu
under **Settings → Devices & services**. Config Flow offers automatic or manual
server selection and performs the first measurement after the load warning is
accepted. Options Flow changes the mode, manual server, or schedule (`off`, 30m,
1h, 3h, 6h, 12h, 24h). The integration exposes download, upload, latency, status,
and a manual-run button. Diagnostics use a privacy-safe whitelist.

Each measurement may saturate download and upload for about 10 seconds per
direction with 4 parallel streams. The full upstream catalog is fetched and
validated at runtime and is not shipped. Existing official Iperf3 users should
run both integrations temporarily, switch dashboards and automations manually,
then remove legacy YAML; Recorder history is not transferred.

## Разработка и release gates

```console
UV_CACHE_DIR=/private/tmp/internetspeedru-uv-cache uv sync --locked --dev
UV_CACHE_DIR=/private/tmp/internetspeedru-uv-cache uv run pytest
UV_CACHE_DIR=/private/tmp/internetspeedru-uv-cache uv run ruff check .
UV_CACHE_DIR=/private/tmp/internetspeedru-uv-cache uv run ruff format --check .
```

Каждый release проходит HACS Action, Hassfest (manifest и translations), pytest
и ruff. `mypy` не является release gate `v0.1.0`.

## Лицензия

[MIT](LICENSE)
