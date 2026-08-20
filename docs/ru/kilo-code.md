# Kilo Code: подключение существующих индексов

Code Index может читать индекс Kilo Code 7.4.22, но не владеет его lifecycle.

## Поддерживаемая схема

- Qdrant collection: `ws-<sha256(workspacePath)[0:16]>`;
- LanceDB directory: `<basename>-<sha256(workspacePath)[0:16]>`;
- таблицы `vector` и `metadata`;
- schema `2`;
- chunk fields: `filePath`, `fileHash`, `codeChunk`, `startLine`, `endLine`,
  `segmentHash`;
- metadata: `indexing_complete`, provider, model ID, dimension.

## Автоматическое обнаружение

В `Code Index: Manage` нажмите `Detect Kilo`. Extension покажет candidates и
запросит подтверждение `Attach` или `Attach and activate`. Автоматическая
активация без подтверждения запрещена.

Если candidates несколько, сравните backend, location и metadata. Если нужный
source не обнаружен, добавьте его CLI вручную — примеры в [cli.md](cli.md).

## Embedding profile

Для search Code Index должен самостоятельно вычислить query vector. Создайте
профиль, у которого provider/model/dimension точно совпадают с metadata Kilo.
Credentials Kilo не копируются: ключ embedding endpoint задаётся отдельно в
Windows Credential Manager.

## Ready, Stale и Error

- `Ready` — schema/profile совместимы и `indexing_complete=true`;
- `Stale` — metadata сообщает incomplete;
- `Error` — backend недоступен, metadata отсутствует или profile несовместим.

Kilo source нельзя мигрировать, индексировать, удалять или optimize через Code
Index. Чтобы обновить его, используйте Kilo Code; Code Index увидит обновлённое
состояние при следующем status/search.
