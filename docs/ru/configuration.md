# Конфигурация и секреты

## Расположение

Конфигурация хранится вне индексируемых репозиториев. Если не задана
SYMBRAID_CONFIG, используются:

- Windows: %LOCALAPPDATA%\Symbraid\config.json;
- Linux: $XDG_CONFIG_HOME или $HOME/.config/symbraid/config.json.

Indexes, locks и model cache используют platform data directories. Точные пути
выводит команда symbraid paths и они не коммитятся.

Registry хранит только secret_ref. В интерактивной установке используется OS
keyring. Для headless Linux можно явно включить ссылку env://SYMBRAID_EMBEDDING_KEY;
значение читается во время запуска и не попадает в JSON или logs.

## Defaults и project overrides

~~~text
symbraid defaults show
symbraid defaults set --backend lancedb
symbraid project override /absolute/project --debounce-ms 2000
symbraid project override /absolute/project --embedding-profile local-code
~~~

Основные настройки: backend (lancedb или qdrant), embedding_profile, URL и
secret_ref Qdrant, local store root, debounce/bulk thresholds, max file size,
chunk size/overlap/batch size и путь к rg.

Project config хранит normalized path, project_id, состояние watcher, managed
sources и один active_source_id, а также только отличия от defaults.

## Безопасный ввод ключа

Передавайте ключ через stdin, чтобы core сохранил его в OS keyring:

~~~powershell
Read-Host 'Embedding API key' -AsSecureString |
  symbraid profile set remote-code --api-key-stdin
~~~

Не помещайте secrets в shell history, process arguments, tests, reports или
config.json. Перед сменой provider запустите profile test и проверьте dimension.
Новый provider/model/dimension создаёт новый managed source.

## Locks и безопасность

Watcher, index, refresh и migration используют lock проекта и не меняют его
параллельно. status и search read-only. Symbraid изменяет только созданные им
managed sources и не трогает неизвестные Qdrant collections или внешние LanceDB
directories без отдельного подтверждения.

## Имена коллекций

Managed Qdrant sources используют префикс коллекции `symbraid-<project-id>`.
Структурное изменение настроек создаёт новый source `symbraid-*` и сохраняет
предыдущий source для отката. Сгенерированный source никогда не использует
коллекцию, принадлежащую другому проекту.
