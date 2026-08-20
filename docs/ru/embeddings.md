# Embeddings и подключение своей модели

Во всех примерах используется launcher из установленного runtime:

```powershell
$codeIndex = "$env:LOCALAPPDATA\CodeIndex\bin\code-index.cmd"
```

## Что такое embedding profile

Профиль описывает способ преобразования текста и поискового запроса в vector:

- `provider`: `fastembed` или `openai-compatible`;
- `model`: ID модели;
- `dimension`: точная размерность vector;
- `base_url`: endpoint для OpenAI-compatible provider;
- `secret_ref`: ссылка на ключ в Windows Credential Manager.

Model, provider и dimension являются частью схемы индекса. Их нельзя менять для
готового индекса без полной переиндексации или создания нового source.

## Локальная модель FastEmbed

Профиль по умолчанию:

```text
provider: fastembed
model: jinaai/jina-embeddings-v2-base-code
dimension: 768
```

Создать/заменить профиль:

```powershell
& $codeIndex profile set local-code `
  --provider fastembed `
  --model jinaai/jina-embeddings-v2-base-code `
  --dimension 768

& $codeIndex profile test local-code
& $codeIndex project override C:\repo --embedding-profile local-code
```

При первом тесте/индексации модель загружается в
`%LOCALAPPDATA%\CodeIndex\models`. Убедитесь, что имя поддерживается установленной
версией FastEmbed и реальная размерность совпадает с `--dimension`.

## Свой OpenAI-compatible endpoint

Endpoint должен принимать POST на `/embeddings` в формате:

```json
{
  "model": "your-model-id",
  "input": ["first text", "second text"]
}
```

Ответ должен содержать `data[].embedding` и `data[].index`.

Пример настройки:

```powershell
$apiKey = Read-Host 'Embedding API key' -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
  [Runtime.InteropServices.Marshal]::SecureStringToBSTR($apiKey)
)
$plain | & $codeIndex profile set company-code `
  --provider openai-compatible `
  --model company/code-embedding-v2 `
  --dimension 1024 `
  --base-url https://embeddings.example.com/v1 `
  --api-key-stdin
$plain = $null

& $codeIndex profile test company-code
```

Если `base_url` не заканчивается на `/embeddings`, Code Index добавляет этот
суффикс. Ключ передаётся как `Authorization: Bearer ...`. Пустой ключ разрешён для
локальных endpoints без authentication.

Для локального OpenAI-compatible сервера:

```powershell
& $codeIndex profile set local-api `
  --provider openai-compatible `
  --model my-embedding-model `
  --dimension 768 `
  --base-url http://127.0.0.1:8080/v1
& $codeIndex profile test local-api
```

## Выбор размерности

Не угадывайте dimension. Возьмите её из документации модели или выполните один
тестовый запрос. `profile test` проверяет длину возвращённого vector и выдаёт
ошибку при несовпадении.

## Переход на новую модель

Безопасная последовательность:

1. создать новый профиль;
2. выполнить `profile test`;
3. выбрать профиль для проекта;
4. создать/очистить совместимый managed source и выполнить полный `index --force`;
5. проверить `status` и несколько запросов;
6. только затем удалять старый индекс отдельным подтверждённым действием.

`migrate-backend` переносит существующие vectors без пересчёта и поэтому не
предназначен для смены embedding model или dimension.

## Типовые ошибки

- `Embedding dimension mismatch` — неверный `--dimension` или endpoint вернул
  другую модель;
- `Embedding endpoint failed` — URL, TLS, proxy, authentication или сервер;
- модель FastEmbed не найдена — неверный model ID либо модель не поддерживается.
