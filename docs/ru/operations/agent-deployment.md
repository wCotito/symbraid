# Развёртывание агентом

Чек-лист для агента или maintainer, который меняет Symbraid в checkout. Он
разделяет исходники, установку runtime и проверки.

## Безопасная последовательность

1. Прочитайте [архитектуру](../architecture.md) и guide изменяемого компонента.
2. Проверьте `git status --short` и сохраните чужие изменения.
3. Меняйте canonical source только в этом repository. Не правьте установленный
   runtime, plugin cache, model cache, database или credential store напрямую.
4. Сначала обновите `docs/en`, а в том же изменении — идентичный путь `docs/ru`.
5. Запустите проверку parity документации и релевантные tests. Dry plan
   benchmark не является измерением.
6. Соберите core, extension и plugin поддерживаемыми scripts и проверьте diff.
7. Устанавливайте только после review; затем проверьте MCP handshake, active
   source и список клиентов в новой сессии.
8. Сохраняйте исходный managed source для rollback до подтверждения миграции.

Индексацией и foreground watcher владеет core; VS Code и Codex — тонкие
клиенты. Секреты поступают через защищённый ввод или разрешённую env-ссылку,
но не через аргументы CLI и не в логи.

