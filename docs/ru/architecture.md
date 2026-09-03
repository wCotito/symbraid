# Архитектура

Symbraid — локальный индекс исходного кода. Портируемое Python-ядро владеет
конфигурацией, индексацией, managed-хранилищами и foreground watcher. Клиенты
используют read-only контракт MCP и не открывают vector store напрямую.

~~~text
проект на диске
      │
      ▼
Symbraid core (CLI / foreground watcher)
  ├─ rg + ignore rules
  ├─ Tree-sitter chunking
  ├─ file/content hashes
  └─ embedding profile
      │
      ▼
один активный managed source проекта
  ├─ LanceDB (локально)
  └─ Qdrant (managed/remote)
      │
      ▼
read-only MCP gateway
  ├─ stdio (по умолчанию)
  └─ loopback-only Streamable HTTP (opt-in)
      │
      ▼
VS Code, Codex и другие клиенты
~~~

## Границы

Ядро — единственный владелец registry, индексации, миграций и жизненного цикла
watcher. Нормализованный абсолютный путь даёт стабильный project_id: первые 16
символов SHA-256. У проекта ровно один активный managed source, результаты
разных sources не смешиваются.

Watcher — видимый foreground-процесс ядра. Для операторов могут существовать
service recipes, но installer не должен молча создавать привилегированный или
всегда запущенный daemon.

## Хранилища и миграция

Одна строка индекса соответствует функции, методу, классу или небольшому
текстовому фрагменту. Payload включает repo_id, path, language, symbol, kind,
диапазон строк и file/content hashes.

Incremental indexing сначала помечает metadata как incomplete, пересчитывает
только изменённые chunks, удаляет удалённые пути и ставит complete только после
успеха. Backend migration копирует vectors и payload партиями, проверяет
schema/provider/model/dimension/count и атомарно меняет active source. Старый
source остаётся вариантом rollback.

## MCP и клиенты

Gateway предоставляет ровно три read-only tools:

- semantic_search;
- index_status;
- list_index_sources.

Stdio используется по умолчанию. Streamable HTTP отключён без явного opt-in и
может слушать только loopback. Codex plugin и VS Code — тонкие клиенты: они не
импортируют LanceDB/Qdrant, не считают embeddings и не меняют индекс.

Semantic result — кандидат, а не доказательство. Перед изменением подтверждайте
его точным поиском, AST/symbol search и чтением текущего файла с диска.

## Границы доверия

- managed sources записывает только core;
- MCP доступен только для чтения;
- credentials принимаются через stdin или явно разрешённую env-ссылку и
  хранятся в OS keyring;
- пути, ключи, model cache и private source остаются локальными, кроме запросов
  к настроенному embedding endpoint.
