# Развёртывание агентом

Этот документ предназначен для Codex и других coding agents, которым поручено
установить, обновить или диагностировать Semantic Code Index Kit на Windows.

## Целевой результат

- canonical source остаётся в clone этого репозитория;
- runtime установлен в `%LOCALAPPDATA%\CodeIndex`;
- `ada-b.code-index` установлен в VS Code;
- marketplace `semantic-code-index-kit` подключён;
- `hybrid-code-search` установлен из этого marketplace;
- registry и существующие indexes сохранены;
- секреты отсутствуют в логах, JSON и process arguments;
- MCP expose-ит ровно три read-only tools.

## 1. Предварительный аудит

Не изменяя систему, проверить:

```powershell
python --version
Get-Command rg,node,npm.cmd,code.cmd,codex -ErrorAction SilentlyContinue
Test-Path "$env:LOCALAPPDATA\CodeIndex\config.json"
code.cmd --list-extensions --show-versions
codex plugin marketplace list
codex plugin list
```

Если Python ниже 3.10, Node/VS Code/Codex отсутствуют, сообщить пользователю,
какой необязательный компонент нельзя установить. Для установки только приложения
использовать skip flags, а не загружать случайный runtime скрытно.

Перед destructive действиями разрешить точные absolute paths. Не удалять Qdrant
collections, LanceDB directories, registry, model cache или Credential Manager
entries без отдельного явного разрешения.

## 2. Проверка исходников

```powershell
git status --short
powershell -ExecutionPolicy Bypass -File .\scripts\verify-windows.ps1
```

Если runtime ещё не установлен, сначала выполнить installer с нужными skip flags,
затем verification. Не запускать тесты из global Python, если зависимости проекта
находятся в `%LOCALAPPDATA%\CodeIndex\runtime\.venv`.

## 3. Установка

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

Installer разрешено запускать повторно: source app обновляется, но `config.json`,
models и data indexes сохраняются. Проверить exit code каждого внешнего процесса.
Не считать предупреждение npm/vsce успешной установкой без строки об установленном
extension.

## 4. Проверка runtime и CLI

```powershell
$ci = "$env:LOCALAPPDATA\CodeIndex\bin\code-index.cmd"
& $ci defaults show
& $ci project list
& "$env:LOCALAPPDATA\CodeIndex\runtime\.venv\Scripts\python.exe" -c `
  "import lancedb, mcp, keyring; print(lancedb.__version__)"
```

Если тестируется новый проект:

```powershell
& $ci project register $PWD
& $ci index $PWD
& $ci status $PWD
& $ci search $PWD 'где настраивается embedding provider' --top-k 5
```

Первая индексация может загружать модель. Не оставлять оборванный процесс. Если
оболочка завершилась по timeout, проверить command line процессов перед точечной
остановкой; не завершать все процессы Python на машине.

## 5. Проверка VS Code extension

```powershell
code.cmd --list-extensions --show-versions |
  Select-String '^ada-b\.code-index@'
```

Проверить Node tests и syntax через `verify-windows.ps1`. Интерактивная приёмка:

1. открыть тестовый workspace;
2. открыть `Code Index: Manage`;
3. проверить active source/backend;
4. нажать status `Off` и убедиться в `Indexing`, затем `On · ...`;
5. изменить/создать/удалить небольшой файл и проверить incremental refresh;
6. закрыть окно и убедиться, что watcher process не остаётся глобально.

Не включать watcher автоматически для всех ранее известных проектов.

## 6. Проверка Codex plugin

```powershell
codex plugin marketplace list
codex plugin list
```

Проверить manifest и skill официальными локальными validators:

```powershell
$py = "$env:LOCALAPPDATA\CodeIndex\runtime\.venv\Scripts\python.exe"
& $py "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" `
  .\plugins\hybrid-code-search\skills\hybrid-code-search
& $py "$env:USERPROFILE\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py" `
  .\plugins\hybrid-code-search
```

При изменении plugin source обновить cachebuster штатным helper, повторно
валидировать и выполнить:

```powershell
codex plugin add hybrid-code-search@semantic-code-index-kit
```

Тестировать только в новой сессии Codex.

## 7. MCP handshake

Проверить initialize и `tools/list` MCP SDK‑клиентом. Ожидаемый набор:

```text
semantic_search
index_status
list_index_sources
```

Наличие `index`, `refresh`, `remove`, `migrate` или другого mutating MCP tool —
ошибка архитектуры и блокирует релиз.

После установки этот handshake выполняется готовым скриптом:

```powershell
$py = "$env:LOCALAPPDATA\CodeIndex\runtime\.venv\Scripts\python.exe"
& $py .\scripts\verify_mcp.py
```

На Windows venv launcher может создавать дочерний base‑Python process. Тестовый
клиент должен закрывать stdin/transport и иметь timeout; после сбоя проверять и
останавливать только процессы с command line `mcp_gateway.py` этого runtime.

## 8. Backend и migration acceptance

Для Qdrant использовать только новую temporary/test collection или managed
`code-index-<project_id>`. Не трогать `ws-*`, `codex-code-v1` и неизвестные
collections.

Проверить:

1. LanceDB index/search;
2. migration LanceDB → Qdrant;
3. count/schema/model/dimension;
4. search на Qdrant;
5. migration обратно;
6. исходный index сохранён.

При mismatch active source не должен переключаться.

## 9. Документация и завершение

Если изменились CLI flags, schema, paths, install flow, extension UI или skill,
обновить соответствующие файлы `docs/ru` и README компонента.

Перед завершением:

```powershell
git status --short
git diff --check
.\scripts\verify-windows.ps1
& $ci status $PWD
```

Не коммитить generated/runtime data. Сообщить пользователю установленную версию,
active source, completeness, результаты тестов и необходимость новой Codex session
или VS Code reload.
