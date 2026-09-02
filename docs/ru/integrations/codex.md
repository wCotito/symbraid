# Интеграция Codex

Codex plugin — тонкий адаптер MCP-сервера Symbraid. По умолчанию он подключает
stdio и передаёт read-only запросы поиска и статуса. В plugin нет indexer,
vector store, embedding provider или database dependency.

## Граница

Разрешены только `semantic_search`, `index_status` и `list_index_sources`.
Нельзя добавлять команды индексирования, refresh, delete, transfer или
переключения source. Ядро владеет project identity, выбором source,
совместимостью embeddings и всеми записями.

Историческое имя `hybrid-code-search` остаётся compatibility alias одной
major-версии. В новой документации используется `symbraid-search`.

## Настройка

Установите plugin из checkout или проверенного artifact и начните новую сессию
Codex. Проверьте MCP handshake и active source до поиска. При ошибке используйте
[диагностику](../operations/troubleshooting.md); не сбрасывайте индекс и не
добавляйте второй source в обход ошибки клиента.

MCP server id: `io.github.symbraid-project/symbraid`.
