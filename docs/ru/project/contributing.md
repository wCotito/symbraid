# Участие в проекте

Изменения должны сохранять индексацию и владение данными в Symbraid core.
Интеграции остаются тонкими клиентами и используют только документированный
read-only MCP surface.

Для документации сначала редактируйте файл в `docs/en`, затем идентичный
относительный путь в `docs/ru` и запускайте `python scripts/sync_docs.py
--check`. Не оставляйте flat legacy filename, если страница относится к
integration, operations, project или review.

Для сборки и тестов расширения нужны Node.js 22.12.0+ и Python 3.10+ в `PATH`.
Запуск браузерного регрессионного теста Manage:

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
Матрица CI расширения проверяет Node.js 22.12.0 и последнюю версию Node.js 22.

Security workflow проверяет полный Python lock-файл, включая все платформенные
варианты и extras, и все npm dev-зависимости. Он экспортирует `uv.lock` во
временный `pylock.toml` для `pip-audit` с OSV; экспорт не является вторым
поддерживаемым lock-файлом. Уязвимости и ошибки сервиса приводят к неуспеху
задания. Запускайте `npm audit --package-lock-only` из каталога расширения;
команды Python-аудита находятся в
[security workflow](/.github/workflows/security.yml).
Исходные номера алертов и требования совместимости приведены в
[обновлении безопасности зависимостей](/docs/ru/reviews/dependency-security.md).

См. [корневой CONTRIBUTING](../../../CONTRIBUTING.md) и [готовность релиза](../reviews/release-readiness.md).

