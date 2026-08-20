# Инструкция для агентов

Этот репозиторий — единый источник истины для Code Index, VS Code extension и
Codex plugin. Не вносить изменения в установленный runtime
`%LOCALAPPDATA%\CodeIndex` или plugin cache напрямую: сначала изменить исходники
здесь, затем запустить установку и проверки.

## Карта компонентов

- `components/code-index` — Python 3.10+, индексатор, stores, CLI, read-only MCP.
- `extensions/vscode-code-index` — Node/VS Code extension без собственной логики БД.
- `plugins/hybrid-code-search` — thin Codex plugin; не добавлять сюда индексатор.
- `docs/ru` — пользовательская и эксплуатационная документация.
- `scripts` — единственная поддерживаемая точка установки/проверки на Windows.

## Обязательные архитектурные границы

1. Codex plugin не должен напрямую импортировать Qdrant/LanceDB, считать embedding
   или изменять индекс.
2. MCP plugin предоставляет только `semantic_search`, `index_status` и
   `list_index_sources`.
3. Kilo Code adapters строго read-only.
4. Один проект имеет один активный source; смешивание результатов запрещено.
5. Перед переключением backend проверяются schema, provider, model, dimension и
   count; исходный индекс сохраняется для rollback.
6. Секреты принимаются только через stdin и сохраняются в Windows Credential
   Manager. Не логировать ключи и не добавлять их в CLI arguments/config/tests.
7. Watcher живёт только в extension host открытого VS Code workspace.
8. Никогда не изменять и не удалять старые/внешние коллекции без отдельного
   явного разрешения пользователя.

## Порядок изменения и развёртывания

1. Прочитать `docs/ru/architecture.md` и документ затрагиваемого компонента.
2. Изменить canonical source в этом репозитории.
3. Запустить `scripts\verify-windows.ps1`.
4. Запустить `scripts\install-windows.ps1` для синхронизации runtime/VSIX/plugin.
5. Проверить `code-index status`, MCP handshake и список установленных extensions.
6. Для изменённого Codex skill/plugin выполнить validation, cachebuster и
   переустановку; затем тестировать в новой сессии Codex.
7. Инкрементально обновить индекс этого репозитория.
8. Обновить соответствующую документацию в том же изменении.

Полная пошаговая процедура и команды: [docs/ru/agent-deployment.md](docs/ru/agent-deployment.md).

## Проверки перед завершением

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-windows.ps1
$codeIndex = "$env:LOCALAPPDATA\CodeIndex\bin\code-index.cmd"
& $codeIndex status $PWD
code.cmd --list-extensions --show-versions
codex plugin list
```

Не коммитить `node_modules`, `.venv`, VSIX, model cache, LanceDB data, credentials,
логи и файлы пользовательского registry.
