# CLI

После установки launcher находится здесь:

```powershell
$codeIndex = "$env:LOCALAPPDATA\CodeIndex\bin\code-index.cmd"
& $codeIndex --help
```

Все команды возвращают JSON в stdout. Ошибки возвращают JSON в stderr и ненулевой
exit code. Это позволяет безопасно вызывать CLI из VS Code и автоматизации.

## Settings API

```powershell
& $codeIndex settings show --project C:\repo
'{"backend":"qdrant"}' | & $codeIndex settings plan C:\repo
'{"backend":"qdrant","plan_hash":"..."}' | & $codeIndex settings apply-project C:\repo
'{"backend":"lancedb"}' | & $codeIndex settings apply-defaults
```

Payload передаётся только через stdin. `settings plan` возвращает impact
`configuration-only`, `transfer` или `reindex`; apply отклоняет устаревший
`plan_hash`. Для проверки доступны `settings test-backend` и
`profile test-config`, также принимающие JSON через stdin.

## Проекты

```powershell
& $codeIndex project register C:\repo
& $codeIndex project list
& $codeIndex project watch C:\repo on
& $codeIndex project watch C:\repo off
& $codeIndex project override C:\repo --debounce-ms 2000
& $codeIndex project remove C:\repo
```

`project remove` удаляет запись registry, но сохраняет физический индекс.

## Sources

```powershell
& $codeIndex source list C:\repo
& $codeIndex source use C:\repo managed-lancedb
```

Все sources являются managed. Переключение разрешено только после проверки
metadata/profile/count; предыдущий source сохраняется для rollback.

## Embedding profiles

```powershell
& $codeIndex profile list
& $codeIndex profile set local-code --provider fastembed --model MODEL --dimension 768
& $codeIndex profile set remote-code --provider openai-compatible `
  --model MODEL --dimension 1024 --base-url https://host/v1
$key | & $codeIndex profile set remote-code ... --api-key-stdin
& $codeIndex profile test remote-code
```

Подробности: [embeddings.md](embeddings.md).

## Индексация

```powershell
& $codeIndex index C:\repo
& $codeIndex index C:\repo --force
& $codeIndex refresh C:\repo src\a.py src\b.ts
& $codeIndex status C:\repo
```

- `index` делает reconcile всего проекта, но пересчитывает только изменённые файлы;
- `--force` пересчитывает все chunks;
- `refresh` предназначен для небольшого списка изменённых/удалённых файлов;
- после branch switch или изменения `.gitignore` используйте `index`.

## Поиск

```powershell
& $codeIndex search C:\repo "где обновляется access token" --top-k 10
& $codeIndex search C:\repo "валидация платежа" --path-filter "src/payments"
```

`top_k` ограничивается диапазоном 1–20. Результат содержит source/backend,
score, path, symbol/kind, строки, preview и hashes. Перед изменением файла результат
нужно проверить через `rg`, AST и чтение исходника.

## Миграция backend

```powershell
& $codeIndex migrate-backend C:\repo qdrant
& $codeIndex migrate-backend C:\repo lancedb
```

Миграция доступна только для managed source и не пересчитывает embedding. При
несовместимой metadata/count переключение не выполняется.

## MCP

```powershell
& $codeIndex mcp
# или
& "$env:LOCALAPPDATA\CodeIndex\bin\code-index-mcp.cmd"
```

MCP использует stdio; не запускайте его интерактивно и не печатайте посторонний
текст в stdout процесса.
