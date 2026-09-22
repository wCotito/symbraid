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

## Внешний HTTP MCP для sandbox-клиента

Если embedding profile использует удалённый OpenAI-compatible endpoint, stdio-
сервер sandbox-клиента может унаследовать запрет исходящей сети. На Windows
настройте один внешний loopback-сервер для всех проектов, зарегистрированных в
реестре Symbraid. Запускайте скрипт из обычного внешнего PowerShell, а не из
sandboxed Codex shell:

```powershell
.\scripts\configure-codex-http-mcp.ps1
```

Helper использует `-CodexHome`, затем `CODEX_HOME`, затем обычный профиль
пользователя. Профиль с сегментом `CodexSandbox*` отклоняется, чтобы случайно
не изменить shadow-директорию sandbox. До любых изменений проверяется, что
установленный `symbraid` поддерживает `--allow-all-projects` и
`--auth-token-env`.

Скрипт создаёт или переиспользует bearer token в пользовательской переменной
окружения, отключает только stdio MCP установленных Symbraid plugins и добавляет
одну глобальную Streamable HTTP запись в `<CodexHome>\config.toml`. Токен не
записывается в Codex config, state JSON, аргументы task или логи. Listener всегда
привязан к `127.0.0.1` и требует токен.

Для явного запуска при входе пользователя:

```powershell
.\scripts\configure-codex-http-mcp.ps1 -InstallStartupTask
```

Проверить или удалить только интеграцию, принадлежащую helper:

```powershell
.\scripts\configure-codex-http-mcp.ps1 -Action Status
.\scripts\configure-codex-http-mcp.ps1 -Action Remove
```

`-Action Remove` сохраняет token environment variable, если явно не передан
`-RemoveManagedToken`. `-NoStart` настраивает Codex, но не утверждает, что
endpoint запущен. После настройки перезапустите Codex, чтобы он перечитал
`config.toml` и пользовательское окружение.

Сервер запускается без `--project`; каждый tool request должен передавать
зарегистрированный `project_path`. Поэтому один процесс может обращаться к
любому проекту из общего registry и сохраняет те же три read-only tools.

## Необязательный HTTP-транспорт

Для ручной локальной интеграции передавайте bearer token через окружение. По
умолчанию привяжите сервер к одному проекту и никогда не коммитьте значение
токена:

```text
symbraid mcp --transport streamable-http --project /absolute/project --host 127.0.0.1 --port 8765 --auth-token-env SYMBRAID_MCP_TOKEN
```

Чтобы один процесс обслуживал все зарегистрированные проекты, замените
`--project ...` на `--allow-all-projects`. Расширенная область всегда включается
явно; запросы по-прежнему должны передавать `project_path`. `--token-env`
остаётся совместимым alias для `--auth-token-env`.

Обычно endpoint имеет вид `http://127.0.0.1:8765/mcp`. Клиент должен передавать
Bearer Authorization и подходящий Accept-заголовок Streamable HTTP.

## Безопасность транспорта

Для локальных клиентов рекомендуется stdio. HTTP включайте только для явной
локальной интеграции, привязывайте к `127.0.0.1` или `::1`, требуйте token и
ограничивайте допустимый `Origin`. Нельзя использовать `0.0.0.0`, LAN-адрес или
публичный интерфейс. Материал токена хранится в окружении ОС и не сериализуется
и не записывается в логи.

См. [конфигурацию](../configuration.md) и [правила безопасности](../project/security.md).
