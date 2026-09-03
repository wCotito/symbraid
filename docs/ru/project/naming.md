# Проверка названия продукта

Последняя проверка: 2026-09-03

Название release candidate — **Symbraid**. Точное имя проверено через публичные
read-only API реестров непосредственно перед review готовности к релизу:

| Реестр | Точный запрос | Результат |
| --- | --- | --- |
| GitHub repositories | `wCotito/symbraid` | Создан для этого проекта |
| PyPI | distribution `symbraid` | HTTP 404 (не зарегистрирован) |
| npm | unscoped package `symbraid` | HTTP 404 (не зарегистрирован) |
| VS Code Marketplace | extension ID `symbraid.symbraid` | 0 результатов |
| Official MCP Registry | поиск `symbraid` | 0 servers |

Публичные идентификаторы используют имя проекта и подтверждённого GitHub owner:
repository `wCotito/symbraid`, Python package/CLI `symbraid`, VS Code extension
`symbraid.symbraid`, Codex plugin `symbraid-search` и MCP server
`io.github.wcotito/symbraid`.

Доступность меняется со временем и не резервирует имя. Все проверки нужно
повторить непосредственно перед публикацией или созданием publisher/package
accounts. Чистый поиск по реестрам не является проверкой товарного знака,
юридическим заключением или гарантией безопасности имени во всех юрисдикциях и
классах продуктов; перед публичным коммерческим запуском нужна подходящая
юридическая проверка.