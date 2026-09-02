# Polyglot benchmark fixture

This fixture is a deliberately small, deterministic codebase for semantic and
symbol search experiments. It contains equivalent authentication, billing, and
configuration concepts in several languages plus one SQL migration. The fixture
is distributed under the repository's MIT license; it contains no credentials,
network calls, or generated data.

The relevance judgments in `../config/queries.jsonl` identify the files and
symbols expected for each query. Do not treat those judgments as a claim that
one implementation is better than another.
