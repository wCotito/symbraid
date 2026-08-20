# Semantic Code Index Kit

Локальный набор инструментов для семантического поиска по исходному коду:
самостоятельный индексатор, MCP gateway, VS Code extension и тонкий Codex‑плагин.

Проект рассчитан на Windows и хранит индексы локально. По умолчанию используется
встраиваемая LanceDB, поэтому Docker не нужен. При желании можно переключиться на
Qdrant или подключить существующий индекс Kilo Code в режиме только для чтения.

## Что входит в проект

```text
semantic-code-index-kit/
├─ components/code-index/          Python-приложение, CLI и MCP gateway
├─ extensions/vscode-code-index/   VS Code extension ada-b.code-index
├─ plugins/hybrid-code-search/     Codex plugin и skill проверки результатов
├─ docs/ru/                        подробная документация на русском
├─ scripts/                        установка, удаление и проверка
└─ .agents/plugins/                marketplace для установки Codex plugin
```

Приложение Code Index владеет индексированием и настройками. Codex‑плагин не
работает с базами напрямую и получает результаты только через три read-only MCP
инструмента: `semantic_search`, `index_status`, `list_index_sources`.

## Быстрый старт

Требования:

- Windows 10/11;
- Python 3.10 или новее;
- `ripgrep`;
- Node.js и VS Code — если устанавливается extension;
- Codex CLI — если устанавливается Codex plugin;
- Docker нужен только для Qdrant, LanceDB работает без него.

В PowerShell из корня проекта:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

Установщик:

1. создаёт runtime в `%LOCALAPPDATA%\CodeIndex`;
2. устанавливает Python‑зависимости в отдельный `venv`;
3. создаёт `code-index.cmd` и `code-index-mcp.cmd`;
4. собирает и устанавливает `ada-b.code-index`;
5. подключает marketplace репозитория и устанавливает `hybrid-code-search`.

После установки перезапустите окно VS Code и откройте новую сессию Codex.

Зарегистрировать и проиндексировать проект вручную:

```powershell
$codeIndex = "$env:LOCALAPPDATA\CodeIndex\bin\code-index.cmd"
& $codeIndex project register C:\path\to\project
& $codeIndex index C:\path\to\project
& $codeIndex status C:\path\to\project
```

В VS Code откройте `Code Index: Manage`. Клик по `Code Index: Off` включает
watcher для текущего workspace; watcher существует только пока открыто это окно.

## Документация

- [Архитектура](docs/ru/architecture.md)
- [Установка и обновление](docs/ru/installation.md)
- [Конфигурация и хранение секретов](docs/ru/configuration.md)
- [Embedding‑провайдеры и свои модели](docs/ru/embeddings.md)
- [CLI: команды и примеры](docs/ru/cli.md)
- [VS Code extension и watcher](docs/ru/vscode-extension.md)
- [Codex plugin и MCP](docs/ru/codex-plugin.md)
- [Подключение индексов Kilo Code](docs/ru/kilo-code.md)
- [Диагностика проблем](docs/ru/troubleshooting.md)
- [Инструкция для агентов по развёртыванию](docs/ru/agent-deployment.md)

## Безопасность данных

- исходники и embeddings остаются на машине, кроме запросов к настроенному вами
  внешнему embedding endpoint;
- API keys хранятся в Windows Credential Manager через `keyring`;
- ключи не записываются в `config.json` и не передаются аргументами командной строки;
- Kilo‑источники всегда read-only;
- semantic result считается подсказкой, а не доказательством: skill требует
  `semantic → rg → AST → чтение актуального файла`.

## Проверка и разработка

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-windows.ps1
```

Проект не создаёт Windows service. Индексатор запускается явно через CLI или из
VS Code extension. Лицензия — MIT.
