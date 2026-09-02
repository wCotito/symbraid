# Документация Symbraid

[English](../en/README.md) | [Русский](README.md)


Symbraid — локальный набор инструментов для индексации исходного кода и
семантического поиска. Каноническая документация находится в `docs/en`, а этот
русский каталог сохраняет те же относительные пути.

## Руководства

- [Архитектура](architecture.md)
- [Установка и обновление](installation.md)
- [Конфигурация и секреты](configuration.md)
- [Профили embeddings](embeddings.md)
- [CLI](cli.md)
- [Интеграция MCP](integrations/mcp.md)
- [Интеграция с VS Code и watcher](integrations/vscode.md)
- [Codex plugin и MCP](integrations/codex.md)
- [Диагностика](operations/troubleshooting.md)
- [Развёртывание агентом](operations/agent-deployment.md)
- [Бенчмарки](benchmarks.md)
- [Инструкции для агентов](project/agents.md)
- [Участие в проекте](project/contributing.md)
- [Правила безопасности](project/security.md)
- [Лицензия](project/license.md)
- [Готовность релиза](reviews/release-readiness.md)

После изменения английского файла переведите соответствующий файл здесь и
запустите:

```powershell
python scripts/sync_docs.py --check
```

