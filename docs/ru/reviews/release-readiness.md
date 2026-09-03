# Независимое ревью готовности к релизу

Дата ревью: 2026-09-03
Область: текущее рабочее дерево Symbraid
Reviewer: независимый агент, не участвовавший в написании проверяемых изменений
Вердикт: **ready**

## Контракт ревью

Замечания имеют severity P0 (критическая блокировка релиза), P1 (высокая
блокировка), P2 (исправить или обоснованно отклонить) и P3 (зарегистрированный
follow-up). Релиз нельзя принять при открытых P0/P1 или verdict `not ready`.

Проверялись Windows/Linux paths, независимость от хоста, watcher locking и
восстановление после прерывания, read-only контракт MCP, HTTP authentication и
изоляция проектов, сохранение sources, schema handling, redaction секретов,
паритет локалей и состав пакетов.

## Замечания и исправления

Замечаний P0 и P1 не обнаружено.

| ID | Severity | Замечание | Исправление | Проверка |
| --- | --- | --- | --- | --- |
| RR-01 | P2 | В подготовке project payload оставался неиспользуемый переходный параметр `store`. | Параметр и переходный комментарий удалены. | Статическая проверка call sites и Python suite. |
| RR-02 | P2 | Readiness-документ описывал устаревшую migration и старое число тестов. | Отчёт заменён этой актуальной записью. | Проверка локалей, hashes, links и повторное ревью. |

Отдельный аудит простых артефактов нашёл два compatibility shim, не связанных с
именем продукта: аргумент payload и константу release scanner. Оба удалены. Старое дерево плагина, старые console commands,
marketplace identity, executable fallback, schema migration и keyring fallback
также удалены, поскольку проект новый и ещё не опубликован.

## Доказательства

- Python: 31 тест прошёл; один Linux-only тест path casing ожидаемо пропущен на
  Windows-хосте ревью.
- VS Code: прошли тесты контракта extension и Manage webview. Панель состояния
  читает `project.index_status`, логики индексации в extension нет.
- MCP: ровно три read-only инструмента; тесты покрывают loopback-only HTTP,
  bearer token, проверки Origin/Host и изоляцию bound project.
- Watcher: тесты покрывают duplicate lease, clean pre-stop и metadata при
  прерванном refresh.
- Storage: тесты требуют префикс `symbraid-` для новых Qdrant collections и
  активацию source только после успешной индексации.
- Документация: 17 пар English/Russian прошли tree parity, translation hash,
  root projection и link checks.
- Packaging: прошли сборка wheel/sdist и archive-secret scans; в wheel есть
  только entry points `symbraid` и `symbraid-mcp`.
## Оставшиеся release gates

Тот же независимый reviewer повторно проверил RR-01 и RR-02 и не нашёл открытых
P0, P1 или P2. Hosted CI на Windows и Ubuntu, Linux-only тест и сборка артефактов из clean checkout
остаются зарегистрированными P3 gates release workflow; локальное Windows-ревью
не выдаёт их за выполненные.

## Финальный вердикт

**Ready.** Открытых P0, P1 и P2 нет. Публикация остаётся заблокированной до
прохождения зарегистрированных выше P3 checks release workflow.