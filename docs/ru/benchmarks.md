# Бенчмарки

Закоммиченный harness — воспроизводимый каркас, а не заявление о результатах.
Он использует MIT-лицензированный polyglot fixture в
[`../../benchmarks/fixture`](../../benchmarks/fixture), manifest версий и
лицензий и adapters с явными командами подготовки.

На текущем состоянии репозитория benchmark ещё не запускался. Нет заявленных
latency, recall, throughput или сравнений с конкурентами. Первый запуск должен
сохранить версии инструментов, model/provider, hardware, OS, хэши fixture и
query set и режим до записи результата.

## Два режима

1. **Out-of-box:** документированные defaults каждого инструмента.
2. **Controlled:** одинаковые provider/model, chunking и query set там, где это
   поддерживается. Несовместимые настройки получают `not_comparable`, а не
   молча нормализуются.

Dry plan без внешних инструментов:

~~~text
python benchmarks/run.py --dry-run
~~~

Реальный запуск требует явного флага и пишет raw output только в игнорируемый
каталог `benchmarks/results/`:

~~~text
python benchmarks/run.py --execute --mode out-of-box --output benchmarks/results/run.json
~~~

## Метрики

Harness поддерживает nDCG@10, MRR@10, Recall@1/5/10, Precision@5/10, file
recall и context efficiency. Performance schema включает минимум пять warm
repeats, p50/p95/p99, cold-index wall/CPU, files/LOC per second, peak RSS, disk
bytes per chunk, startup, incremental convergence, idle memory и response size.
Неполученные значения помечаются `not_collected`, а неподдерживаемый controlled
track — `not_comparable`; нули и выдуманные результаты не используются.

Опциональный CodeSearchNet subset закреплён в
`benchmarks/external/codesearchnet-manifest.json`; download выполняется только
явной командой `python benchmarks/download_codesearchnet.py --download`.
Human judgments и license provenance сохраняются.

Правила adapters и provenance описаны в
[`../../benchmarks/README.md`](../../benchmarks/README.md).
