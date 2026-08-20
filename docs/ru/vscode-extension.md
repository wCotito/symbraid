# VS Code extension и watcher

Extension ID: `ada-b.code-index`.

## Управление

Откройте Command Palette и выполните `Code Index: Manage`. Экран позволяет:

- выбрать default backend;
- задать Qdrant URL/API key и LanceDB root;
- настроить embedding provider/model/dimension/base URL/key;
- задать project overrides debounce/bulk/profile;
- посмотреть sources и выбрать active source;
- обнаружить Kilo indexes;
- запустить reconcile или migration.

Все изменения выполняются через JSON CLI. Extension не читает и не записывает
vector store напрямую.

## Status bar

Для managed source:

- `Code Index: Off` — watcher выключен;
- `Code Index: Indexing` — выполняется refresh/reconcile;
- `Code Index: On · LanceDB` или `On · Qdrant` — watcher включён;
- `Code Index: Error` — наведите курсор для текста ошибки.

Клик по managed status переключает watcher. Для external source показывается
`Kilo · Ready`, `Kilo · Stale` или `Kilo · Error`; клик открывает Manage и не
управляет watcher Kilo.

## Как работает watcher

1. Extension активируется в открытом окне VS Code.
2. Workspace регистрируется в Code Index.
3. Если `watch_enabled=true` и active source managed, создаётся VS Code filesystem
   watcher.
4. Save/create/delete накапливаются в очередь.
5. После `debounce_ms` вызывается `refresh` для небольшого списка файлов.
6. При большом числе событий, изменении `.gitignore` или Git HEAD вызывается full
   `index` reconcile.
7. При закрытии окна extension host уничтожает watcher и timers.

Фоновой Windows service нет. Если VS Code закрыт, изменения будут замечены при
следующем открытии workspace и reconcile.

## Multi-root workspace

Используется folder активного editor. Если активный editor не относится к folder и
открыто несколько roots, extension показывает выбор. Настройки и active source
хранятся отдельно для каждого абсолютного пути.

## После первой установки

Новый extension ID не наследует состояние старого watcher. Откройте каждый нужный
workspace и один раз нажмите `Code Index: Off`, чтобы включить наблюдение.

## Сборка вручную

```powershell
cd extensions\vscode-code-index
npm.cmd ci
npm.cmd test
npx.cmd vsce package --no-dependencies --allow-missing-repository
code.cmd --install-extension .\ada-b.code-index-0.1.0.vsix --force
```

Обычный пользователь должен использовать корневой installer: он помещает VSIX в
runtime, а не в Git working tree.
