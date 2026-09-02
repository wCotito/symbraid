# Benchmarks

The committed benchmark harness is a reproducible scaffold, not a result
claim. It uses the MIT-licensed polyglot fixture under
[`../../benchmarks/fixture`](../../benchmarks/fixture), a version/license
manifest, and adapters with explicit setup commands.

As of this repository state, no benchmark run has been executed. There are no
published latency, recall, throughput, or competitor claims. The first run
must record tool versions, model/provider, hardware, operating system, fixture
hash, query-set hash, and mode before producing results.

## Two tracks

1. **Out-of-box:** each tool uses its documented default model and configuration.
2. **Controlled:** tools that support it use the same provider/model, chunking
   and query set. Unsupported controls are reported as `not_comparable`, never
   silently normalized.

Run a dry plan without external tools:

```text
python benchmarks/run.py --dry-run
```

An actual run is explicit and writes raw outputs only below the ignored
`benchmarks/results/` directory:

```text
python benchmarks/run.py --execute --mode out-of-box --output benchmarks/results/run.json
```

The harness records nDCG@10, MRR@10, Recall@1/5/10, Precision@5/10, file recall,
and context efficiency when the adapter output supports them. Its performance
schema supports at least five warm repeats with p50/p95/p99 latency and response
size, cold-index wall and CPU time, files/LOC per second, peak RSS, disk bytes per
chunk, startup, incremental convergence, and idle memory. Unsupported values are
explicit `not_collected` or `not_comparable`, never zero or fabricated. It does
not download competitors or publish results.
The optional CodeSearchNet subset is separately pinned in
[`benchmarks/external/codesearchnet-manifest.json`](../../benchmarks/external/codesearchnet-manifest.json)
and downloaded only by the explicit opt-in helper. Human judgments remain
provenance-bearing evaluation data. See [`benchmarks/README.md`](../../benchmarks/README.md)
for adapter and provenance rules.
