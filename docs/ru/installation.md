# Установка, обновление и удаление

## Требования

- Windows 10/11 x64;
- Python 3.10+ в `PATH`;
- `ripgrep` (`rg.exe`);
- Node.js/npm и VS Code CLI (`code.cmd`) для extension;
- Codex CLI для Codex plugin;
- Qdrant опционален; LanceDB не требует Docker.

Проверьте инструменты:

```powershell
python --version
rg --version
node --version
npm.cmd --version
code.cmd --version
codex --version
```

## Полная установка

```powershell
git clone <URL-вашего-репозитория> semantic-code-index-kit
cd semantic-code-index-kit
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

Флаги установщика:

- `-SkipExtension` — не собирать/устанавливать VS Code extension;
- `-SkipCodexPlugin` — не подключать marketplace и Codex plugin;
- `-SkipDependencies` — не запускать pip, если venv уже подготовлен.

Установленные данные:

```text
%LOCALAPPDATA%\CodeIndex\
├─ app\                 копия Python-компонента
├─ runtime\.venv\      изолированный Python runtime
├─ bin\                 code-index.cmd и code-index-mcp.cmd
├─ config.json          registry без секретов
├─ data\lancedb\       managed LanceDB indexes
├─ models\              model cache FastEmbed
└─ locks\               project locks
```

VSIX собирается как `%LOCALAPPDATA%\CodeIndex\ada-b.code-index-0.1.0.vsix`.
Codex marketplace регистрируется из корня клона, затем устанавливается
`hybrid-code-search@semantic-code-index-kit`.

После установки:

1. перезапустите окно VS Code;
2. откройте новую сессию Codex;
3. зарегистрируйте проект CLI или просто откройте его в VS Code;
4. включите watcher кликом по `Code Index: Off`, если он нужен.

## Только приложение

```powershell
.\scripts\install-windows.ps1 -SkipExtension -SkipCodexPlugin
```

## Обновление

```powershell
git pull
.\scripts\verify-windows.ps1
.\scripts\install-windows.ps1
```

Установщик сохраняет предыдущую копию runtime app как `app.previous`. Registry,
models и indexes не перезаписываются. Если изменилась embedding model/dimension,
выполните новую индексацию; несовместимый существующий store не будет принят.

## Удаление

По умолчанию удаляются integrations, но пользовательские индексы сохраняются:

```powershell
.\scripts\uninstall-windows.ps1
```

Удалить также marketplace:

```powershell
.\scripts\uninstall-windows.ps1 -RemoveMarketplace
```

Полностью удалить runtime, registry, models и indexes:

```powershell
.\scripts\uninstall-windows.ps1 -RemoveMarketplace -RemoveData
```

`-RemoveData` — необратимая операция и требует PowerShell confirmation.

## Установка из GitHub marketplace

После публикации репозитория marketplace можно добавить напрямую:

```powershell
codex plugin marketplace add OWNER/semantic-code-index-kit --ref main
codex plugin add hybrid-code-search@semantic-code-index-kit
```

Само приложение Code Index всё равно необходимо установить корневым PowerShell
скриптом: Codex plugin не содержит Python runtime и backend drivers.
