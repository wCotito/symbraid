# VS Code extension `ada-b.code-index`

Extension управляет Code Index через JSON CLI. Он не содержит vector store и не
обращается к Qdrant/LanceDB напрямую.

Основные возможности:

- `Code Index: Manage` для profiles, backends, sources и migration;
- status bar с `Off`, `Indexing`, `On · LanceDB/Qdrant`;
- watcher save/create/delete с debounce и full reconcile после смены Git HEAD;
- watcher существует только в lifecycle открытого окна VS Code;
- Kilo sources отображаются как `Kilo · Ready/Stale/Error` и не изменяются.

Разработка:

```powershell
npm.cmd ci
npm.cmd test
node --check extension.js
npx.cmd vsce package --no-dependencies --allow-missing-repository
```

Для полной установки используйте `../../scripts/install-windows.ps1`. Подробное
поведение описано в `../../docs/ru/vscode-extension.md`.
