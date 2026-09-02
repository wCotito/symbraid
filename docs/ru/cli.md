# CLI

CLI core — граница автоматизации. Команды печатают structured JSON в stdout, а
ошибки — в stderr с ненулевым exit code.

~~~text
symbraid --help
symbraid paths
~~~

## Проекты и sources

~~~text
symbraid project register /absolute/project
symbraid project list
symbraid project watch /absolute/project on
symbraid source list /absolute/project
symbraid source use /absolute/project managed-lancedb
~~~

project remove по умолчанию удаляет только registry metadata; physical managed
index сохраняется. У проекта ровно один active managed source.

## Settings и profiles

~~~text
symbraid settings show --project /absolute/project
printf '{"backend":"qdrant"}' | symbraid settings plan /absolute/project
symbraid defaults show
symbraid profile list
symbraid profile test local-code
~~~

Payload settings и secret values принимаются через stdin. settings plan возвращает
configuration-only, transfer или reindex; старый plan hash отклоняется.

## Indexing и search

~~~text
symbraid index /absolute/project
symbraid index /absolute/project --force
symbraid refresh /absolute/project src/auth/session.py
symbraid status /absolute/project
symbraid search /absolute/project "where are access tokens renewed" --top-k 10
~~~

index пересчитывает изменённые files, --force — все chunks. После branch switch
или изменения ignore rules используйте full reconcile. Search result проверяйте
по текущему файлу до edits.

## Backend migration

~~~text
symbraid migrate-backend /absolute/project qdrant
symbraid migrate-backend /absolute/project lancedb
~~~

Vectors копируются без пересчёта. Core проверяет schema/provider/model/dimension/
count, затем переключает active source; прежний source сохраняется для rollback.

## MCP

~~~text
symbraid mcp
symbraid mcp --http 127.0.0.1:8765
~~~

Stdio — default, HTTP — explicit loopback opt-in. Gateway предоставляет только
semantic_search, index_status и list_index_sources.
