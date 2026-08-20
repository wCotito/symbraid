# Архитектура

## Общая схема

```text
проект на диске
      │
      ▼
Code Index CLI / VS Code watcher
  ├─ rg + .gitignore
  ├─ Tree-sitter chunking
  ├─ file/content hashes
  └─ embedding profile
      │
      ▼
один активный source проекта
  ├─ managed LanceDB
  └─ managed Qdrant
      │
      ▼
read-only MCP gateway
      │
      ▼
Codex plugin: semantic → rg → AST → чтение
```

## Компоненты

### Code Index

Единственный владелец индексации. Registry связывает абсолютный путь проекта с
`project_id`, набором managed sources и одним `active_source_id`. Code Index
создаёт, обновляет и безопасно переключает эти sources.

`project_id` — первые 16 символов SHA‑256 нормализованного абсолютного пути.
Поэтому одинаковое имя папки в разных местах получает разные индексы.

### VS Code extension

Транспорт и lifecycle‑контроллер. Все настройки и операции выполняются командами
CLI, чтобы extension не дублировал Python‑логику. Watcher запускается только для
managed source с включённым `watch_enabled` и останавливается вместе с extension
host.

### MCP gateway

Стабильная read-only граница между хранилищем и агентом. Клиент не должен знать,
какой backend активен. Контракт одинаков для LanceDB и Qdrant.

### Codex plugin

Содержит launcher и skill, но не индексатор. Semantic hit рассматривается только
как кандидат. Перед изменением агент обязан подтвердить идентификаторы точным
поиском, структуру AST/symbol search и прочитать актуальный файл с диска.

## Chunk и payload

Одна vector row соответствует функции, методу, классу или небольшому текстовому
фрагменту. Основные поля:

```json
{
  "repo_id": "0123456789abcdef",
  "path": "src/auth/session.ts",
  "language": "typescript",
  "symbol": "renewSessionCredentials",
  "kind": "function",
  "start_line": 84,
  "end_line": 126,
  "file_hash": "...",
  "content_hash": "...",
  "text": "..."
}
```

Metadata row хранит branch/commit, completeness, число файлов/chunks, schema,
embedding provider/model/dimension. `indexing_complete=false` означает, что индекс
нельзя считать полным.

## Инкрементальная индексация

1. `rg --files` формирует список с учётом `.gitignore` и исключений.
2. File hash сравнивается с сохранёнными значениями.
3. Embedding вычисляется только для новых/изменённых chunks.
4. Точки удалённых файлов удаляются.
5. Metadata сначала помечается incomplete и только после успеха — complete.

## Миграция backend

При `migrate-backend` vectors не вычисляются повторно. Приложение копирует vectors
и payload партиями, проверяет schema/provider/model/dimension/count и лишь затем
атомарно меняет `active_source_id`. Исходный индекс остаётся rollback‑вариантом.
При ошибке активный source не переключается, а состояние target восстанавливается.

## Границы доверия

- managed source: чтение и запись принадлежат Code Index;
- MCP: только чтение;
- Codex skill: не запускает индексацию;
- secrets: Windows Credential Manager, в JSON только ссылки.
