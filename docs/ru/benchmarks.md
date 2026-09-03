# Бенчмарки

Symbraid включает воспроизводимый benchmark harness и MIT-лицензированный
polyglot fixture в [`../../benchmarks/fixture`](../../benchmarks/fixture).
Первый измеренный срез ниже намеренно неполный: он сравнивает Symbraid с
ripgrep как лексическим контролем. Это ещё не полный рейтинг конкурентов.

## Локальный срез — 2026-09-03

В controlled-режиме использовались закоммиченный fixture, шесть запросов с
ручной оценкой релевантности, `top_k=10`, один исключённый warm-up и пять
измеряемых CLI invocation на каждый запрос. Symbraid 0.3.0 работал с LanceDB и FastEmbed, модель
`jinaai/jina-embeddings-v2-base-code` (768 измерений). Лексический контроль —
ripgrep 15.2.0. Прогон выполнен из проверяемого рабочего дерева на Windows 11
x64, Python 3.10.5, AMD Ryzen 7 3700X и 64 ГиБ RAM.

| Метрика | Symbraid | ripgrep control |
| --- | ---: | ---: |
| nDCG@10 | 0.830 | 0.634 |
| MRR@10 | 0.867 | 0.722 |
| Recall@1 | 0.087 | 0.069 |
| Recall@5 | 0.604 | 0.294 |
| Recall@10 | 0.886 | 0.622 |
| Precision@5 | 0.867 | 0.567 |
| Precision@10 | 0.700 | 0.600 |
| Warmed CLI invocation p50 | 5 435 мс | 52 мс |
| Warmed CLI invocation p95 | 5 930 мс | 70 мс |
| Warmed CLI invocation p99 | 7 082 мс | 189 мс |
| Медианный размер ответа | 6 859 байт | 819 байт |

На этом небольшом fixture Symbraid дал более качественное семантическое
ранжирование, а ripgrep оказался значительно быстрее и вернул меньше контекста.
Эти числа полезны как regression baseline, но не как универсальное заявление о
производительности: системы выполняют разную поисковую работу, корпус мал, а
измерения сделаны на одной машине.

В этом срезе не измерялись cold indexing, CPU time, throughput, peak RSS, disk
bytes per chunk, startup, incremental convergence, idle memory и context
efficiency. Индекс Symbraid был подготовлен вне измеряемого harness, поэтому
время индексации не выводится из setup-логов. Изолированные прогоны Codanna,
open-codebase-index и Zilliz Claude Context с зафиксированными версиями ещё
предстоит выполнить.

Хэши provenance, записанные harness:

- fixture: `417d14d41e45cc581f5081c40c692d99dc28b1e1e20458cb4501e3cd4c83e261`;
- набор запросов: `a4a6bf8605d5152ad7d5feb0ab839d334fb5862a8a59aa3914782f70cd6343e5`;
- manifest конкурентов: `c0271a4fb85f9ed9e8c26f639b70021a0e511bfeb31fd74332e0c2304ac0f185`;
- harness: `4449ae0ddc314f2fa3bc6726eb9c90de27972e55d9bbdcf9651af95652c5e3a7`.

Raw results остаются в игнорируемом каталоге `benchmarks/results/`, потому что
могут содержать локальные пути машины. Команды воспроизведения измеренной пары:

```text
python benchmarks/run.py --execute --adapter symbraid --adapter ripgrep-lexical-control --mode controlled --output benchmarks/results/controlled-snapshot.json
```

## Методика

Поддерживаются два режима:

1. **Out-of-box:** каждый инструмент использует документированную конфигурацию
   по умолчанию.
2. **Controlled:** инструменты используют одинаковые корпус, relevance
   judgments, запросы, лимит результатов, provider/model и chunking там, где
   такие настройки доступны. Неподдерживаемые ограничения получают
   `not_comparable`.

Схема качества включает nDCG@10, MRR@10, Recall@1/5/10, Precision@5/10, file
recall и context efficiency. Перед минимум пятью измеряемыми CLI invocation выполняется один исключённый
warm-up. Значения p50/p95/p99 включают запуск процесса и модели: это не
in-process query latency. Схема также хранит размер ответа, cold indexing,
throughput, peak RSS, storage per chunk, startup, incremental convergence и
idle memory. Отсутствующие наблюдения помечаются `not_collected`, а не нулём и
не выдуманным значением.

Опциональный subset CodeSearchNet отдельно зафиксирован в
[`benchmarks/external/codesearchnet-manifest.json`](../../benchmarks/external/codesearchnet-manifest.json)
и скачивается только явным opt-in helper. Правила adapters, изоляции и
provenance описаны в [`benchmarks/README.md`](../../benchmarks/README.md).