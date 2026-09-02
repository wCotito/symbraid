# Установка, обновление и удаление

## Поддерживаемая база

- Windows 10/11 x64;
- Linux glibc x86_64 (native release baseline);
- Python 3.10+;
- ripgrep (rg);
- Node.js/VS Code и Codex CLI только для нужных интеграций.

LanceDB работает локально. Qdrant опционален и включается только явно. Docker
для core не требуется.

## Установка из checkout

~~~powershell
git clone <repository-url> symbraid
cd symbraid
python -m pip install -e ./components/symbraid
python -m symbraid --help
~~~

В Windows остаётся удобный installer:

~~~powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
~~~

Runtime хранится вне checkout; пакеты не публикуются. Если интеграции не нужны,
используйте SkipExtension или SkipCodexPlugin. Credentials нельзя передавать в
аргументах или сохранять в config.

## Первый проект

Имена команд одинаковы на поддерживаемых платформах:

~~~text
symbraid project register /absolute/path/to/project
symbraid index /absolute/path/to/project
symbraid status /absolute/path/to/project
~~~

После установки интеграции откройте новое окно VS Code или новую Codex session.

## Обновление

1. Просмотрите CHANGELOG.
2. Запустите проверки своей платформы.
3. Установите core и нужные интеграции из checkout.
4. Проверьте status и metadata active source.

Registry, model cache и managed indexes сохраняются. Изменение model/dimension
требует нового source и полной переиндексации; backend migration embeddings не
пересчитывает.

## Удаление

Сначала удалите интеграции, а runtime data — только после проверки абсолютных
путей. Existing managed indexes и внешние collections автоматически не удаляются.
Разрушительную очистку выполняйте отдельным явным действием.

## Codex marketplace

~~~powershell
codex plugin marketplace add symbraid-project/symbraid --ref main
codex plugin add symbraid-search@symbraid
~~~

Plugin остаётся только тонким клиентом; core, зависимости и backend ставятся
отдельно.
