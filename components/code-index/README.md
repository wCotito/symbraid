# Code Index: приложение и MCP gateway

Самостоятельный Python‑компонент. Он индексирует рабочие каталоги, хранит registry
и secrets, управляет LanceDB/Qdrant и предоставляет read-only MCP для клиентов.

Запускать рекомендуется через установленный launcher:

```powershell
$codeIndex = "$env:LOCALAPPDATA\CodeIndex\bin\code-index.cmd"
& $codeIndex --help
& $codeIndex mcp
```

Исходные точки входа:

- `scripts/code_index_cli.py` — JSON CLI;
- `mcp_gateway.py` — MCP stdio server;
- `code_index/indexer.py` — chunking и incremental refresh;
- `code_index/service.py` — orchestration и active source;
- `code_index/lancedb_store.py`, `qdrant.py` — managed stores.

Не запускайте этот каталог как отдельную установку. Используйте корневой
`scripts/install-windows.ps1`, чтобы runtime и остальные компоненты оставались
согласованными. Настройки описаны в `../../docs/ru/configuration.md`, embeddings —
в `../../docs/ru/embeddings.md`, CLI — в `../../docs/ru/cli.md`.
