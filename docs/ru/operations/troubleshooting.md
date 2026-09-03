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

