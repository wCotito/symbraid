# Symbraid

[English](https://github.com/wCotito/symbraid/blob/main/docs/en/README.md) | [Русский](https://github.com/wCotito/symbraid/blob/main/docs/ru/README.md)

Symbraid — локальный семантический индекс для программных репозиториев. Он
превращает проект в поисковый источник знаний для разработчиков, IDE и любых
MCP-совместимых AI-клиентов. За индексацию не отвечает ни VS Code, ни конкретный
агент.

Python-ядро владеет конфигурацией, индексацией, инкрементальными обновлениями,
хранилищем и read-only MCP-сервером. Интеграции VS Code и Codex — необязательные
тонкие клиенты над единым CLI.

## Зачем нужен Symbraid

- Искать код по смыслу, когда неизвестны имя файла или символа.
- Использовать один индекс одновременно из разных редакторов и AI-клиентов.
- Работать на Windows 10/11 x64 и Linux glibc x86_64.
- Хранить векторы локально в LanceDB или в настроенном Qdrant.
- Отслеживать создание, изменение и удаление файлов, правила ignore и
  переключения Git-веток.
- Предоставлять только три read-only MCP-инструмента: `semantic_search`,
  `index_status` и `list_index_sources`.
- Менять backend или модель embeddings через проверяемый план с сохранением
  предыдущего source для отката.

## Как это работает

1. CLI регистрирует канонический путь проекта и создаёт один активный managed
   source.
2. Индексатор обнаруживает файлы через `ripgrep`, делит поддерживаемый код и
   текстовые форматы на chunks, строит embeddings и сохраняет метаданные вместе
   с векторами.
3. `symbraid watch` инкрементально согласует изменения файловой системы и Git.
4. Поиск через CLI или MCP возвращает ограниченный набор подходящих chunks с
   метаданными проекта и source.
5. Редактор или агент проверяет найденные кандидаты по текущим файлам перед
   использованием.

Конфигурация и secrets хранятся вне репозитория. API-ключи доступны через
системный keyring или переменные окружения и не возвращаются через CLI, MCP,
HTTP или представление Manage.

## Быстрый старт

Требуются Python 3.10 или новее и `rg` в `PATH`.

~~~text
git clone <repository-url> symbraid
cd symbraid
python -m pip install -e ./components/symbraid

symbraid project register /absolute/path/to/project
symbraid index /absolute/path/to/project
symbraid status /absolute/path/to/project
symbraid search /absolute/path/to/project "где обновляются access tokens"
~~~

Поддерживайте индекс актуальным в foreground-процессе:

~~~text
symbraid watch /absolute/path/to/project
~~~

Запустите стандартный stdio MCP-сервер для клиента:

~~~text
symbraid mcp --project /absolute/path/to/project
~~~

Установка для Windows и Linux, настройка Qdrant, embedding-профилей и обновлений
описаны в руководствах по [установке](installation.md) и
[конфигурации](configuration.md).

## Интеграции

Symbraid не привязан к одному хосту. Стандартные MCP-транспорты и примеры
конфигурации подготовлены для Codex, Claude Code/Desktop, VS Code, Cursor,
Windsurf и OpenCode. Stdio используется по умолчанию. Опциональный Streamable
HTTP разрешён только на loopback и проверяет bearer token, Origin и Host.

- [MCP-клиенты и транспорты](integrations/mcp.md)
- [Расширение VS Code](integrations/vscode.md)
- [Плагин Codex](integrations/codex.md)
- [Справочник CLI](cli.md)

## Сильные стороны и ограничения

Сильные стороны:

- независимое от хоста ядро и единый индекс для всех интеграций;
- local-first режим с выбором встроенного или сервисного хранилища;
- инкрементальный watcher, блокировка проекта, восстановление после прерывания
  и проверка source;
- явное исключение secrets и намеренно read-only поверхность MCP;
- безопасная смена backend/модели с сохранением предыдущего source;
- симметричная английская и русская документация и кросс-платформенные тесты.

Ограничения:

- первая полная индексация может требовать заметных CPU, сетевого трафика и
  расходов embedding-провайдера;
- качество и задержка зависят от модели, chunking, оборудования и backend;
- для Qdrant нужен отдельно запущенный сервис;
- macOS, Linux ARM64, внешний HTTP bind, TLS termination и multi-user remote
  deployment пока не входят в заявленные цели релиза;
- результаты поиска являются кандидатами и должны проверяться по актуальным
  файлам перед автоматическим редактированием.

## Документация

- [Архитектура](architecture.md)
- [Установка](installation.md)
- [Конфигурация и secrets](configuration.md)
- [Embedding-профили](embeddings.md)
- [Эксплуатация и диагностика](operations/troubleshooting.md)
- [Безопасность](project/security.md)
- [Проверка доступности названия](project/naming.md)
- [Участие в проекте](project/contributing.md)
- [Независимое ревью готовности](reviews/release-readiness.md)

Symbraid распространяется по [лицензии MIT](project/license.md).
