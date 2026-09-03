# Инструкции для агентов

Symbraid имеет единый источник истины для core, VS Code integration, Codex
plugin и документации. Агент может менять исходники в
repository, но не установленный runtime и не plugin cache.

Архитектурные границы:

- `components/symbraid` владеет индексацией, stores, конфигурацией, миграциями
  и read-only MCP server;
- `extensions/vscode-symbraid` — тонкий клиент текущего workspace;
- `plugins/symbraid-search` — тонкий Codex adapter;
- у project только один active managed source;
- перед backend change проверяются source, provider, model, dimension и count.

Не сериализуйте secrets, не смешивайте projects и не удаляйте старую или
внешнюю collection без явного разрешения. При изменении поведения обновляйте
canonical English docs и соответствующий русский путь.

