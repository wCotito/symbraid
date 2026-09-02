# Symbraid benchmark harness

This directory contains a committed, MIT-licensed polyglot fixture and a
stdlib-only harness for code-search comparisons. It is intentionally an
execution scaffold: the repository currently has no benchmark results.

## Status

`python benchmarks/run.py --dry-run` reports `not_executed` and prints the
planned commands. No competitor is downloaded, contacted, or configured by the
dry run. Actual execution requires the explicit `--execute` flag and local
installations of the selected adapters.

Raw command output belongs below `benchmarks/results/`, which is ignored by Git.
Never commit result files containing private source, credentials, model caches,
or machine-specific paths.

## Fixture and query set

The fixture contains small, deterministic examples in Python, JavaScript,
TypeScript, Rust, Go, Java, PHP, C#, C++, Ruby, Markdown, YAML, JSON, and SQL. It
also includes explicit decoys and ignored dependency/cache paths. It is distributed
under the root MIT license; see `fixture/LICENSE`. Queries and relevance judgments
are in `config/queries.jsonl`. The harness records SHA-256 digests of both before
an execution.

## Comparison tracks

- **out-of-box** uses each adapter's documented default model/configuration;
- **controlled** uses the common provider/model and chunking settings only when
  an adapter explicitly supports them; otherwise the result is
  `not_comparable`.

The competitor/version/license inventory is `competitors.json`. The optional
CodeSearchNet subset manifest and human-judgment provenance are in
`external/codesearchnet-manifest.json`; run `python benchmarks/download_codesearchnet.py
--download` only after an explicit review. It records
provenance and observation dates; it is not a ranking or a claim about
performance.

## Adapters

Each JSON adapter in `adapters/` contains an executable name, argument template,
result format, setup notes, and controlled-track support. Commands use
placeholders `{fixture}`, `{query}`, and `{k}` and are executed without a shell.
The adapter must return either a JSON list of hits or an object with a
`results`/`hits` list whose items include `path`.

The included adapter descriptions are:

- Symbraid working tree;
- Codanna 0.12.0 (Apache-2.0);
- open-codebase-index 0.23.0 (MIT); and
- ripgrep lexical control 14.1.0 (MIT OR Unlicense); and
- Claude Context 0.1.11 (MIT, pinned commit; execution remains blocked until a
  read-only adapter is reviewed).

These versions and licenses are recorded for reproducibility, not inferred
from an unrecorded local installation. Verify them again before publishing any
benchmark report.

## Metrics

For each query the runner calculates nDCG@10, MRR@10, Recall@1/5/10,
Precision@5/10, file recall, and context efficiency when the adapter output
contains enough evidence. The performance schema supports at least five warm
repeats with p50/p95/p99 latency and response-size percentiles, cold-index wall
and CPU time, files/LOC per second, peak RSS, disk bytes per chunk, startup,
incremental convergence, and idle memory. Unsupported or unmeasured values are
explicit `not_collected` (or `not_comparable` for an unsupported controlled
track), never zero or an invented result.

Example commands:

~~~text
python benchmarks/run.py --dry-run
python benchmarks/run.py --execute --adapter symbraid --mode controlled \
  --output benchmarks/results/symbraid-controlled.json
~~~

An executed report must include tool versions, provider/model, hardware, OS,
fixture/query hashes, mode, and the exact adapter command. Do not describe a
dry plan as a benchmark result.
