# Конфигурация

## Где хранится

Registry находится в `%LOCALAPPDATA%\CodeIndex\config.json`. Конфигурация не
записывается в индексируемые репозитории. API keys находятся в Windows Credential
Manager; JSON содержит только `secret_ref`.

Основные разделы:

```json
{
  "schema_version": 1,
  "defaults": {},
  "profiles": {},
  "projects": {}
}
```

Не рекомендуется редактировать файл вручную: используйте CLI или `Code Index:
Manage`. Запись выполняется атомарно через временный файл.

## Defaults

Во всех примерах ниже используется установленный launcher:

```powershell
$codeIndex = "$env:LOCALAPPDATA\CodeIndex\bin\code-index.cmd"
```

- `backend`: `lancedb` или `qdrant`;
- `embedding_profile`: профиль для новых managed sources;
- `qdrant_url`, `qdrant_secret_ref`;
- `lancedb_root`;
- `debounce_ms`, `bulk_change_threshold`;
- `max_file_bytes`;
- `chunk_chars`, `chunk_overlap_chars`, `batch_size`;
- `rg_path`;
- `kilo_lancedb_roots`.

Показать defaults:

```powershell
& $codeIndex defaults show
```

Изменить backend для новых проектов:

```powershell
& $codeIndex defaults set --backend lancedb
```

Настроить Qdrant:

```powershell
& $codeIndex defaults set --qdrant-url http://127.0.0.1:18133
Get-Content .\qdrant-key.txt -Raw |
  & $codeIndex defaults set --qdrant-api-key-stdin
```

После команды безопасно удалите временный файл с ключом. Предпочтительнее передать
секрет из password manager непосредственно в stdin.

## Project overrides

Проект хранит только отличия от defaults:

```powershell
& $codeIndex project override C:\repo --debounce-ms 2500 --bulk-change-threshold 200
& $codeIndex project override C:\repo --embedding-profile company-code
& $codeIndex project override C:\repo --clear-embedding-profile
```

Каждый проект имеет:

- нормализованный path и `project_id`;
- `watch_enabled`;
- `overrides`;
- словарь `sources`;
- один `active_source_id`.

## Managed source

Code Index может записывать managed source. Для Qdrant создаётся collection
`code-index-<project_id>`. Для LanceDB создаётся directory
`<project-name>-<project_id>` с таблицами `vector` и `metadata`.

## External source

External Kilo source всегда имеет `mode: read-only`. Его provider/model/dimension
должны совпасть с выбранным embedding profile, иначе активация отклоняется.

## Locks

Операции записи используют lock в `%LOCALAPPDATA%\CodeIndex\locks`. Одновременные
watcher, CLI index и migration не могут изменять один project index параллельно.
`status` и `search` остаются read-only.
