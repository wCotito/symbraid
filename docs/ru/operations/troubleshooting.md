# Диагностика

Начните с `symbraid status <project>` и проверьте active source, backend,
embedding profile, dimension и count chunks. Перед отправкой диагностики
удалите пути, токены и текст исходников.

## Частые случаи

- **Нет результатов:** убедитесь, что project зарегистрирован, индексация
  завершена, а запрос идёт в active managed source. Перед reindex проверьте
  provider, model и dimension.
- **Watcher не запущен:** проверьте workspace и watcher lease. Watcher —
  foreground-процесс ядра, extension только клиент. Запустите его через CLI
  ядра или используйте OS service recipe по явной необходимости.
- **MCP handshake не проходит:** сначала используйте stdio. Для HTTP проверьте
  loopback bind, token, host и origin; публичные и wildcard bind отклоняются.
- **Миграция небезопасна:** остановитесь и изучите impact plan. Старый source
  сохраняется до проверок schema, provider, model, dimension и count. Не
  удаляйте старую или внешнюю коллекцию без явного разрешения.
- **Секрет отсутствует:** восстановите keyring entry или разрешённую env-ссылку.
  Конфигурация хранит только ссылки, не значения.

См. [развёртывание агентом](agent-deployment.md), а также страницы [MCP](../integrations/mcp.md),
[VS Code](../integrations/vscode.md) и [Codex](../integrations/codex.md).
## Временные локальные сбои

Read-only запрос состояния не завершается ошибкой только из-за того, что Windows
временно запрещает проверку watcher-lock. Ответ сохраняет владельца watcher,
если его удалось прочитать, и помечает проверку как `unavailable`. Обзор VS Code
также запрашивает `symbraid status`, когда в настройках нет состояния индекса, и
показывает ошибку команды вместо пустого объекта.

Для OpenAI-compatible embedding повторяются временные сетевые ошибки, тайм-ауты,
временно некорректные ответы и HTTP 408, 429, а также ошибки шлюза или сервиса 5xx.
Всего выполняется до трёх попыток. Ошибки аутентификации и другие постоянные HTTP-
ошибки возвращаются сразу. Если не сработала ни одна попытка, проверьте доступность
endpoint, правила firewall и proxy, credentials и состояние provider.
