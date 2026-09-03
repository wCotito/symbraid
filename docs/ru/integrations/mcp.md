# Интеграция MCP

MCP-сервер Symbraid предоставляет только read-only поиск и диагностику. По
умолчанию используется локальный stdio. Streamable HTTP включается явно и
должен слушать только loopback-адрес с настроенным bearer-токеном и проверкой
origin.

## Инструменты

Сервер предоставляет ровно три инструмента:

- `semantic_search` ищет релевантные фрагменты активного managed source;
- `index_status` сообщает метаданные и готовность индекса;
- `list_index_sources` перечисляет идентификаторы источников без секретов.

MCP не индексирует, не обновляет, не удаляет, не переносит и не переключает
источники. Жизненным циклом управляет CLI ядра Symbraid. Клиент не должен
импортировать backend индекса, вычислять embeddings или записывать данные
индекса.

## Примеры конфигурации клиентов

Ниже используется стабильный id сервера и локальный stdio-процесс. Имена файлов
и полей конфигурации могут различаться в версиях клиентов; оставьте команду и
аргументы неизменными и перенесите эквивалентную запись в конфигурацию,
описанную для вашей версии клиента.

### Codex

В разделе MCP-конфигурации Codex (форма TOML):

```toml
[mcp_servers."io.github.wcotito/symbraid"]
command = "symbraid"
args = ["mcp", "--transport", "stdio"]
```

### Claude Code и Claude Desktop

Claude Desktop использует JSON-объект `mcpServers`. В Claude Code ту же команду
можно зарегистрировать через CLI:

```text
claude mcp add io.github.wcotito/symbraid -- symbraid mcp --transport stdio
```

Эквивалентная JSON-форма для Desktop:

```json
{
  "mcpServers": {
    "io.github.wcotito/symbraid": {
      "command": "symbraid",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}
```

### VS Code

Для workspace-файла `.vscode/mcp.json` используйте форму VS Code `servers`:

```json
{
  "servers": {
    "io.github.wcotito/symbraid": {
      "type": "stdio",
      "command": "symbraid",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}
```

### Cursor

В `.cursor/mcp.json` Cursor использует знакомую форму `mcpServers`:

```json
{
  "mcpServers": {
    "io.github.wcotito/symbraid": {
      "command": "symbraid",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}
```

### Windsurf

В конфигурации MCP Windsurf используйте ту же stdio-команду:

```json
{
  "mcpServers": {
    "io.github.wcotito/symbraid": {
      "command": "symbraid",
      "args": ["mcp", "--transport", "stdio"]
    }
  }
}
```

### OpenCode

В версиях OpenCode раздел может называться `mcp`, а локальная команда
представляться массивом аргументов. Ниже — общая форма; если имена полей вашей
версии отличаются, следуйте её схеме конфигурации:

```json
{
  "mcp": {
    "symbraid": {
      "type": "local",
      "command": ["symbraid", "mcp", "--transport", "stdio"],
      "enabled": true
    }
  }
}
```

## Необязательный HTTP-транспорт

Включайте HTTP только для явной локальной интеграции; токен передавайте через
переменную окружения. Никогда не коммитьте значение bearer-токена:

```text
symbraid mcp --transport streamable-http --host 127.0.0.1 --port 8765 --token-env SYMBRAID_MCP_TOKEN
```

Обычно endpoint имеет вид `http://127.0.0.1:8765/mcp`. Ниже приведена общая
запись HTTP-клиента; URL, transport и имена полей заголовков зависят от клиента
и его версии, поэтому проверьте их документацию. Обозначение
`${SYMBRAID_MCP_TOKEN}` означает чтение переменной окружения, а не значение,
которое нужно вставлять в коммит:

```json
{
  "type": "http",
  "url": "http://127.0.0.1:8765/mcp",
  "headers": {"Authorization": "Bearer ${SYMBRAID_MCP_TOKEN}"}
}
```

## Безопасность транспорта

Для локальных клиентов рекомендуется stdio. HTTP включайте только для явной
локальной интеграции, привязывайте к `127.0.0.1` или `::1`, требуйте созданный
токен и ограничивайте допустимый `Origin`. Нельзя использовать `0.0.0.0`, LAN-
адреса или публичный интерфейс. Материал токена храните в системном keyring;
для headless-развёртывания допустима ссылка на переменную окружения, но её
значение нельзя сериализовать или писать в лог.

См. [конфигурацию](../configuration.md) и [правила безопасности](../project/security.md).
