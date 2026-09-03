# Benchmarks

Symbraid includes a reproducible benchmark harness and an MIT-licensed polyglot
fixture under [`../../benchmarks/fixture`](../../benchmarks/fixture). The first
measured snapshot below is deliberately partial: it compares Symbraid with
ripgrep as a lexical control. It is not yet a complete competitor ranking.

## Local snapshot — 2026-09-03

The controlled track used the committed fixture, six human-judged queries, `top_k=10`, one excluded warm-up per query,
and five measured CLI invocations per query. Symbraid 0.3.0 used LanceDB and
FastEmbed with `jinaai/jina-embeddings-v2-base-code` (768 dimensions). The
lexical control used ripgrep 15.2.0. The run was made from the reviewed working
tree on Windows 11 x64, Python 3.10.5, an AMD Ryzen 7 3700X, and 64 GiB RAM.

| Metric | Symbraid | ripgrep control |
| --- | ---: | ---: |
| nDCG@10 | 0.830 | 0.634 |
| MRR@10 | 0.867 | 0.722 |
| Recall@1 | 0.087 | 0.069 |
| Recall@5 | 0.604 | 0.294 |
| Recall@10 | 0.886 | 0.622 |
| Precision@5 | 0.867 | 0.567 |
| Precision@10 | 0.700 | 0.600 |
| Warmed CLI invocation p50 | 5,435 ms | 52 ms |
| Warmed CLI invocation p95 | 5,930 ms | 70 ms |
| Warmed CLI invocation p99 | 7,082 ms | 189 ms |
| Median response size | 6,859 bytes | 819 bytes |

On this small fixture, Symbraid produced the stronger semantic ranking while
ripgrep was dramatically faster and returned less context. These numbers are
useful as a regression baseline, not as a universal performance claim: the two
systems perform different retrieval work, the corpus is small, and one machine
was measured.

Cold indexing, CPU time, throughput, peak RSS, disk bytes per chunk, startup,
incremental convergence, idle memory, and context efficiency were not collected
in this snapshot. The Symbraid index was prepared outside the timed harness, so
no index-time estimate is inferred from setup logs. Codanna,
open-codebase-index, and Zilliz Claude Context remain pending isolated,
version-pinned runs.

Provenance hashes recorded by the harness:

- fixture: `417d14d41e45cc581f5081c40c692d99dc28b1e1e20458cb4501e3cd4c83e261`;
- query set: `a4a6bf8605d5152ad7d5feb0ab839d334fb5862a8a59aa3914782f70cd6343e5`;
- competitor manifest: `c0271a4fb85f9ed9e8c26f639b70021a0e511bfeb31fd74332e0c2304ac0f185`;
- harness: `4449ae0ddc314f2fa3bc6726eb9c90de27972e55d9bbdcf9651af95652c5e3a7`.

Raw results stay in the ignored `benchmarks/results/` directory because they
may contain machine-local paths. Reproduce the measured pair with:

```text
python benchmarks/run.py --execute --adapter symbraid --adapter ripgrep-lexical-control --mode controlled --output benchmarks/results/controlled-snapshot.json
```

## Methodology

The two supported tracks are:

1. **Out-of-box:** each tool uses its documented default configuration.
2. **Controlled:** tools use the same corpus, judgments, query set, result
   limit, provider/model, and chunking where those controls exist. Unsupported
   controls are reported as `not_comparable`.

The quality schema covers nDCG@10, MRR@10, Recall@1/5/10, Precision@5/10, file
recall, and context efficiency. The performance schema covers one excluded warm-up followed by at least five measured
CLI invocations. Its p50/p95/p99 values include process and model startup; they
are not in-process query latency. The schema also records response size, cold indexing,
throughput, peak RSS, storage per chunk, startup, incremental convergence, and
idle memory. Missing observations are `not_collected`, never zero or fabricated.

The optional CodeSearchNet subset is separately pinned in
[`benchmarks/external/codesearchnet-manifest.json`](../../benchmarks/external/codesearchnet-manifest.json)
and downloaded only through the explicit opt-in helper. See
[`benchmarks/README.md`](../../benchmarks/README.md) for adapter, isolation, and
provenance rules.