# Embedding profiles

An embedding profile maps code and a search query to vectors. It is part of an
index schema and contains:

- `provider`: `fastembed` or `openai-compatible`;
- `model`: the model identifier;
- `dimension`: the exact vector length;
- `base_url`: the endpoint for an OpenAI-compatible provider; and
- `secret_ref`: a reference managed by the OS keyring or an opted-in environment
  source.

## Local FastEmbed

The default profile is local and does not need an API key:

```text
provider: fastembed
model: jinaai/jina-embeddings-v2-base-code
dimension: 768
```

Configure and test it:

```text
symbraid profile set local-code \
  --provider fastembed \
  --model jinaai/jina-embeddings-v2-base-code \
  --dimension 768
symbraid profile test local-code
```

The first run may download a model into the platform model cache. Confirm that
the installed FastEmbed version supports the model and that its actual vector
length equals `dimension`.

## OpenAI-compatible endpoint

The endpoint accepts `POST /embeddings` with a payload like:

```json
{"model":"your-model-id","input":["first text","second text"]}
```

The response must include `data[].embedding` and `data[].index`.

```text
symbraid profile set remote-code \
  --provider openai-compatible \
  --model company/code-embedding-v2 \
  --dimension 1024 \
  --base-url https://embeddings.example.com/v1 \
  --api-key-stdin
symbraid profile test remote-code
```

The key is sent as `Authorization: Bearer ...`. A local endpoint may use an
empty key. Never guess a dimension: read the model documentation or use
`profile test`.

## Changing a model

Create and test a new profile, assign it to the project, build a new managed
source with a full index, and compare status/search results before removing the
old source in a separately confirmed operation. `migrate-backend` copies
existing vectors and is not a model migration.

Common failures are a dimension mismatch, an unavailable endpoint, or an
unsupported model identifier. Keep the old compatible source for rollback.
