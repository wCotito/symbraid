# Участие в проекте

Изменения должны сохранять индексацию и владение данными в Symbraid core.
Интеграции остаются тонкими клиентами и используют только документированный
read-only MCP surface.

Для документации сначала редактируйте файл в `docs/en`, затем идентичный
относительный путь в `docs/ru` и запускайте `python scripts/sync_docs.py
--check`. Не оставляйте flat legacy filename, если страница относится к
integration, operations, project или review.

Для браузерного регрессионного теста Manage нужен Python 3.10+ в `PATH`:

```sh
cd extensions/vscode-symbraid
npm ci
npx playwright install chromium
npm run test:browser
```

Другой Python можно выбрать через `SYMBRAID_TEST_PYTHON`. Тест вызывает настоящие
preview/plan/apply core в изолированном временном каталоге без зависимостей БД
и моделей и проверяет настоящую форму Manage на EN/RU. CI запускает эту проверку
вместе с тестами расширения.

См. [корневой CONTRIBUTING](../../../CONTRIBUTING.md) и [готовность релиза](../reviews/release-readiness.md).

