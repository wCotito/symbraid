# Embedding profiles

Embedding profile преобразует код и поисковый запрос в vectors. В профиль входят
provider (fastembed или openai-compatible), model, точная dimension, base_url и
secret_ref из OS keyring либо явно разрешённой env-ссылки.

## Локальный FastEmbed

Профиль по умолчанию:

~~~text
provider: fastembed
model: jinaai/jina-embeddings-v2-base-code
dimension: 768
~~~

~~~text
symbraid profile set local-code \
  --provider fastembed \
  --model jinaai/jina-embeddings-v2-base-code \
  --dimension 768
symbraid profile test local-code
~~~

При первом запуске модель может загрузиться в platform model cache. Проверьте,
что установленная версия поддерживает model ID и реальная длина vector совпадает
с dimension.

## OpenAI-compatible endpoint

Endpoint принимает POST /embeddings:

~~~json
{"model":"your-model-id","input":["first text","second text"]}
~~~

Ответ должен содержать data[].embedding и data[].index.

~~~text
symbraid profile set remote-code \
  --provider openai-compatible \
  --model company/code-embedding-v2 \
  --dimension 1024 \
  --base-url https://embeddings.example.com/v1 \
  --api-key-stdin
symbraid profile test remote-code
~~~

Ключ отправляется как Authorization: Bearer. Не угадывайте dimension: возьмите
её из документации model или используйте profile test.

## Смена model

Создайте и проверьте новый profile, назначьте его проекту, постройте новый source
через полный index и сравните status/search. Старый source удаляйте только
отдельно подтверждённой операцией. migrate-backend переносит vectors, но не
меняет model.

Типовые ошибки: dimension mismatch, недоступный endpoint или неизвестный model
ID. Совместимый старый source оставляйте для rollback.
