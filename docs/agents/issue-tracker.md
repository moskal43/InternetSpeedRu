# Трекер задач: GitHub

Задачи и PRD этого репозитория ведутся в GitHub Issues. Для всех операций используется CLI `gh`.

GitHub remote настроен на `moskal43/InternetSpeedRu`; при запуске внутри репозитория `gh` определяет его автоматически через `git remote -v`.

## Соглашения

- **Создать задачу**: `gh issue create --title "..." --body "..."`. Для многострочного описания использовать heredoc.
- **Прочитать задачу**: `gh issue view <number> --comments`, отфильтровав комментарии через `jq` и также получив метки.
- **Получить список задач**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` с подходящими фильтрами `--label` и `--state`.
- **Добавить комментарий**: `gh issue comment <number> --body "..."`.
- **Добавить или удалить метки**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`.
- **Закрыть задачу**: `gh issue close <number> --comment "..."`.

Репозиторий определяется по `git remote -v` — при запуске внутри клона `gh` делает это автоматически.

## Pull request как источник запросов для triage

**PRs as a request surface: no.**

Если значение изменено на `yes`, pull request проходят через те же метки и состояния, что и задачи, с использованием эквивалентных команд `gh pr`:

- **Прочитать PR**: `gh pr view <number> --comments` и `gh pr diff <number>` для просмотра diff.
- **Получить внешние PR для triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`, затем оставить только `authorAssociation` со значениями `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR` или `NONE`, исключив `OWNER`, `MEMBER` и `COLLABORATOR`.
- **Комментировать, назначать метки или закрывать**: `gh pr comment`, `gh pr edit --add-label` / `--remove-label`, `gh pr close`.

GitHub использует общее пространство номеров для issues и pull request, поэтому ссылка вида `#42` может указывать на любой из этих объектов. Сначала выполнить `gh pr view 42`, а при отсутствии PR — `gh issue view 42`.

## Когда skill просит опубликовать задачу в трекере

Создать GitHub issue.

## Когда skill просит получить соответствующий ticket

Выполнить `gh issue view <number> --comments`.

## Операции wayfinding

Используются skill `/wayfinder`. **Map** — это одна issue, а связанные с ней задачи оформляются как дочерние issues.

- **Map**: одна issue с меткой `wayfinder:map`, содержащая разделы Notes, Decisions-so-far и Fog. Создаётся командой `gh issue create --label wayfinder:map`.
- **Child ticket**: issue, связанная с map как GitHub sub-issue через endpoint sub-issues в `gh api`. Если sub-issues недоступны, добавить child в task list тела map и поместить `Part of #<map>` в начало тела child. Метки: `wayfinder:<type>`, где type — `research`, `prototype`, `grilling` или `task`. После назначения ticket закрепляется за исполнителем.
- **Blocking**: использовать нативные зависимости GitHub Issues. Связь добавляется командой `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, где `<blocker-db-id>` — числовой database ID блокирующей issue из `gh api repos/<owner>/<repo>/issues/<n> --jq .id`, а не номер `#<n>` и не `node_id`. GitHub возвращает открытые блокеры в `issue_dependencies_summary.blocked_by`. Если dependencies недоступны, добавить строку `Blocked by: #<n>, #<n>` в начало тела child. Ticket становится разблокированным после закрытия всех блокеров.
- **Frontier query**: получить открытые дочерние задачи map, исключить задачи с открытыми блокерами или назначенным исполнителем и выбрать первую по порядку в map.
- **Claim**: `gh issue edit <n> --add-assignee @me` — первая операция записи сессии.
- **Resolve**: добавить комментарий с ответом, закрыть ticket и добавить ссылку на контекст в раздел Decisions-so-far у map.
