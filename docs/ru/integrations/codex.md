# Интеграция Codex

Codex plugin — тонкий адаптер MCP-сервера Symbraid. По умолчанию он подключает
stdio и передаёт read-only запросы поиска и статуса. В plugin нет indexer,
vector store, embedding provider или database dependency.

## Границы

Разрешены только `semantic_search`, `index_status` и `list_index_sources`.
Нельзя добавлять команды индексации, refresh, delete, transfer или переключения
source. Ядро владеет project identity, выбором source, совместимостью embeddings
и всеми операциями записи.

## Настройка

Установите `symbraid-search` из checkout или проверенного artifact и начните
новую сессию Codex. Перед поиском проверьте MCP handshake и active source. При
ошибке используйте [диагностику](../operations/troubleshooting.md); не
сбрасывайте индекс и не добавляйте второй source для обхода ошибки клиента.

MCP server id: `io.github.wcotito/symbraid`.
