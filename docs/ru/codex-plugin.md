# Codex plugin и MCP

## Назначение

`hybrid-code-search` добавляет Codex semantic discovery, но не превращает индекс в
источник истины. Официальная документация OpenAI описывает plugins как способ
расширять Codex skills и MCP servers; в этом проекте эти части намеренно отделены
от приложения индексирования.

## Установка

Локальный clone:

```powershell
codex plugin marketplace add D:\work\semantic-code-index-kit
codex plugin add hybrid-code-search@semantic-code-index-kit
```

GitHub repository:

```powershell
codex plugin marketplace add OWNER/semantic-code-index-kit --ref main
codex plugin add hybrid-code-search@semantic-code-index-kit
```

Перед этим установите Code Index. Плагин запускает portable launcher через:

```text
cmd.exe /d /s /c "%LOCALAPPDATA%\CodeIndex\bin\code-index-mcp.cmd"
```

В plugin bundle нет Python runtime, Qdrant/LanceDB drivers, embedding settings или
watcher. После установки откройте новую сессию Codex.

## MCP tools

### semantic_search

Параметры:

- `query` — вопрос по поведению/архитектуре;
- `project_path` — абсолютный путь зарегистрированного проекта;
- `top_k` — 10 по умолчанию, максимум 20;
- `path_filter` — необязательное ограничение подсистемы.

Возвращает только active source проекта и включает `source_id`, `owner`, `backend`,
score, path, symbol/kind, строки, preview и hashes.

### index_status

Возвращает backend, ownership, completeness и metadata активного source.

### list_index_sources

Возвращает configured sources и текущий `active_source_id` без изменений.

## Алгоритм работы агента

Если известен точный идентификатор:

```text
rg → AST/symbol search → чтение файла
```

Если запрос описывает поведение:

```text
semantic_search → rg по кандидатам → AST → чтение → callers/tests
```

Если нужны все использования:

```text
AST/symbol search → rg → чтение
```

Запрещено изменять файл только по preview или score. Hash/строки могут устареть,
поэтому всегда читается текущий файл с диска.

## Отказоустойчивость

Если runtime, active source, backend или embedding profile недоступен, агент
сообщает конкретную причину и продолжает ограниченным `rg`/AST поиском. Плагин не
пытается исправлять или переиндексировать проект.

## Обновление plugin во время разработки

После изменения manifest/skill:

```powershell
python $env:USERPROFILE\.codex\skills\.system\plugin-creator\scripts\update_plugin_cachebuster.py `
  .\plugins\hybrid-code-search
python $env:USERPROFILE\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py `
  .\plugins\hybrid-code-search
codex plugin add hybrid-code-search@semantic-code-index-kit
```

Затем использовать новую сессию Codex.

Официальная отправная точка по расширениям: [OpenAI Developers](https://developers.openai.com/).
