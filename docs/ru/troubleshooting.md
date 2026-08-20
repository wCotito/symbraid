# Диагностика

## Базовая проверка

```powershell
$ci = "$env:LOCALAPPDATA\CodeIndex\bin\code-index.cmd"
Test-Path $ci
& $ci defaults show
& $ci project list
& $ci status C:\path\to\project
code.cmd --list-extensions --show-versions | Select-String 'ada-b.code-index'
codex plugin list | Select-String 'hybrid-code-search'
```

Полный suite:

```powershell
.\scripts\verify-windows.ps1
```

## Project is not registered

```powershell
& $ci project register C:\path\to\project
& $ci index C:\path\to\project
```

Проверьте, что используете тот же нормализованный абсолютный путь, а не symlink или
другую букву диска.

## rg не найден

Установите ripgrep и задайте полный путь в defaults/registry. На машине со Scoop
обычно это `%USERPROFILE%\scoop\shims\rg.exe`.

## Индекс incomplete

Предыдущая индексация была остановлена или завершилась ошибкой. Устраните исходную
ошибку и выполните `index` повторно. Не считайте результаты repository-wide до
`indexing_complete=true`.

## Another indexing operation is already running

Дождитесь текущего watcher/index/migration. Если процесс аварийно завершился,
сначала убедитесь, что процессов Code Index действительно нет. Lock ОС снимается
после завершения процесса; удаление lock-файла обычно не требуется.

## Qdrant unavailable

```powershell
Invoke-RestMethod http://127.0.0.1:18133/collections
```

Проверьте Docker container, port mapping, URL и API key. Для работы без Qdrant
переключитесь на LanceDB.

## Dimension/model mismatch

Выполните `profile test`. Нельзя подключать index, построенный другой моделью или
dimension. Создайте правильный profile или перестройте managed index.

## VS Code status Unavailable/Error

Проверьте наличие runtime launcher и вызовите CLI вручную. После установки
перезапустите `Developer: Reload Window`. Для Kilo Error откройте Manage и сравните
metadata с profile.

## Codex не видит MCP tools

1. проверьте `%LOCALAPPDATA%\CodeIndex\bin\code-index-mcp.cmd`;
2. проверьте `codex plugin list`;
3. переустановите plugin из правильного marketplace;
4. откройте новую сессию Codex.

Codex plugin не должен запускаться до установки приложения.

## Секрет отсутствует

Повторно сохраните ключ через stdin в `profile set` или `defaults set`. Не помещайте
ключ в JSON вручную: registry ожидает `secret_ref`, а secret — запись Windows
Credential Manager.

## В индекс попал node_modules/build

Убедитесь, что используется актуальная версия с рекурсивными ignore patterns,
проверьте `.gitignore`, затем выполните full `index`. Лишние пути будут удалены
reconcile‑операцией.
