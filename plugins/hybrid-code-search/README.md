# Codex plugin `hybrid-code-search`

Тонкий read-only плагин для Codex. Он запускает установленный
`%LOCALAPPDATA%\CodeIndex\bin\code-index-mcp.cmd` и добавляет skill, который
задаёт безопасный порядок поиска:

```text
semantic search → rg → AST/symbol search → чтение текущего файла
```

В плагине намеренно отсутствуют индексатор, embedding provider, watcher и
драйверы баз. Если Code Index или активный source недоступен, агент сообщает
причину и продолжает ограниченным `rg`/AST поиском.

Установка из корня монорепозитория:

```powershell
codex plugin marketplace add .
codex plugin add hybrid-code-search@semantic-code-index-kit
```

После установки откройте новую сессию Codex: MCP и skills загружаются при старте
сессии. Сначала должно быть установлено приложение Code Index корневым
`scripts/install-windows.ps1`.

Подробнее: `../../docs/ru/codex-plugin.md`.
