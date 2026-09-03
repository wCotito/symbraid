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
паритет локалей, состав пакетов и воспроизводимость benchmark.

## Замечания и исправления

Замечаний P0 и P1 не обнаружено.

| ID | Severity | Замечание | Исправление | Проверка |
| --- | --- | --- | --- | --- |
| RR-01 | P2 | В подготовке project payload оставался неиспользуемый переходный параметр `store`. | Параметр и переходный комментарий удалены. | Статическая проверка call sites и Python suite. |
| RR-02 | P2 | Readiness-документ описывал устаревшую migration и старое число тестов. | Отчёт заменён этой актуальной записью. | Проверка локалей, hashes, links и повторное ревью. |
| RR-03 | P2 | Публичный README описывал метрики, но не содержал измеренного результата. | Выполнен и документирован controlled-срез Symbraid/ripgrep: шесть запросов, пять повторов, ограничения и provenance. | Игнорируемый raw JSON и зеркальные benchmark-отчёты. |
| RR-04 | P1 | Первый snapshot учитывал повторные chunks как отдельные file-level gains и неверно называл subprocess time warm query latency. | Hits дедуплицированы по файлу, добавлены bounds-тесты `[0, 1]`, исключён один warm-up, метрика названа warmed CLI invocation latency, оба adapter перезапущены вместе. | Один combined raw report, единый provenance, per-query bounds audit и benchmark tests. |

Отдельный аудит простых артефактов нашёл три compatibility shim, не связанные с
именем продукта: аргумент payload, константу release scanner и benchmark
wrapper. Все три удалены. Старое дерево плагина, старые console commands,
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
- Документация: 18 пар English/Russian прошли tree parity, translation hash,
  root projection и link checks.
- Packaging: прошли сборка wheel/sdist и archive-secret scans; в wheel есть
  только entry points `symbraid` и `symbraid-mcp`.
- Benchmark: прошли два regression tests метрик. Один combined report для
  Symbraid 0.3.0 и ripgrep 15.2.0 использует один harness hash; все
  нормализованные per-query метрики прошли bounds audit `[0, 1]`, отсутствующие
  значения остаются `not_collected`.

## Оставшиеся release gates

Тот же независимый reviewer повторно проверил RR-01—RR-04 и не нашёл открытых
P0, P1 или P2. Hosted CI на Windows и Ubuntu, Linux-only тест, полный
изолированный shortlist конкурентов и сборка артефактов из clean checkout
остаются зарегистрированными P3 gates release workflow; локальное Windows-ревью
не выдаёт их за выполненные.

## Финальный вердикт

**Ready.** Открытых P0, P1 и P2 нет. Публикация остаётся заблокированной до
прохождения зарегистрированных выше P3 checks release workflow.