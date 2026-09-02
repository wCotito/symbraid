# Готовность релиза

Используйте чек-лист до запроса на публикацию релиза. Repository workflows
только собирают и загружают review artifacts; публикация в registry,
marketplace или release page является отдельным осознанным действием.

## Обязательные проверки

- [ ] `docs/en` и `docs/ru` имеют одинаковые Markdown paths, а translation
      manifest сообщает актуальные source hashes.
- [ ] Core tests проходят на поддерживаемых Windows и Linux runners.
- [ ] Extension и plugin artifacts собираются из переименованных Symbraid
      directories и не содержат credentials, generated indexes.
- [ ] MCP сохраняет ровно три read-only tools, HTTP остаётся opt-in loopback.
- [ ] Migration проверяет schema, provider, model, dimension и count; старый
      source остаётся доступен для rollback.
- [ ] `python benchmarks/run.py --dry-run` проходит, а каждый выполненный
      benchmark сохраняет versions, fixture/query hashes, config и raw artifacts.

## Честный отчёт

Не заявляйте результат competitor, если adapter не запускался или сравнение
некорректно. Начальный status repository — `not_executed`; меняйте его только
по воспроизводимому output harness.

## Запись независимой повторной проверки (2026-09-02)

`Verdict: ready`

Вердикт относится к текущему рабочему дереву кандидата в релиз после независимой проверки, исправлений и повторной проверки. Все первоначальные находки P0-P2 закрыты. Пункты P3 ниже являются действиями перед публикацией, а не открытыми блокерами реализации.

### Первоначальные находки и их статус

| Приоритет | Первоначальная находка | Итоговый статус и доказательства |
| --- | --- | --- |
| P0 | Находок P0 не было. | Отклонено: ни один кандидат не подтвердился; повторно проверены границы учётных данных, разрушающих операций, изоляции проектов, транспортов и артефактов. |
| P1 | Настраиваемый в workspace Windows-путь к `.cmd` позволял внедрить метасимволы shell. | Исправлено/закрыто: `spawnSymbraid` отклоняет метасимволы executable и аргументов до запуска через shell; нагрузка отклоняется, безопасный `npm.cmd --version` выполняется. |
| P1 | Английская корневая проекция документации устарела. | Исправлено/закрыто: Python 3.12 `scripts/sync_docs.py --check` сообщает о паритете 17 файлов и корректных ссылках и хешах. |
| P2 | Ошибки валидации, устаревшего plan hash, сохранения registry или reindex могли оставить заменённый credential в keyring. | Исправлено/закрыто: `SecretUpdate` восстанавливает прежний/пустой credential или удаляет новый; тесты покрывают неверные данные, устаревшие хеши, ошибки сохранения/reindex и сохранение прежнего source. |
| P2 | Остановка watcher VS Code могла гоняться с apply/restart. | Исправлено/закрыто: ожидается корректный выход с ограниченным fallback принудительного завершения; тесты отложенного и неуступчивого child process проходят. |
| P2 | Миграция schema v3 могла молча перезаписать записи с одинаковым ID, если пути нормализовались в один ключ. | Исправлено/закрыто: любая коллизия нормализованных путей отклоняется, исходные registry schema v2 и backup сохраняются. |
| P2 | Scanner архивов распознавал слишком мало форматов credentials. | Исправлено/закрыто: расширены шаблоны bearer, JWT, npm, GitLab, GitHub, AWS, присваиваний и private key; self-tests и сканирование свежих wheel, sdist и VSIX проходят. |
| P2 | Provenance benchmark не содержал dirty tree, harness и adapter state. | Исправлено/закрыто: dry-run содержит dirty/status/diff/repository-state hashes, hash harness и хеши всех пяти adapters. |
| P3 | В первоначальной проверке не осталось дефекта реализации P3. | Отложенные проверки перед публикацией приведены ниже; открытых находок P0-P2 нет. |

### Доказательства повторной проверки

- Windows core: `uv run --project components/symbraid python -m unittest discover -s components/symbraid/tests -p test_*.py -v` успешно выполнил 33 теста с одним Linux-only skip, включая live-проверки Qdrant и LanceDB.
- Ubuntu 24.04 под WSL: suite текущего дерева успешно выполнил 33 теста с одним Windows-only skip; проверки регистра путей Linux и обе live-проверки backend прошли.
- VS Code: `npm.cmd test --prefix extensions/vscode-symbraid` прошёл extension- и webview-тесты, включая регрессии executable-string injection и ожидаемого завершения watcher.
- MCP: `scripts/verify_mcp.py` выполнил настоящий stdio handshake в Windows и Ubuntu и вернул ровно `index_status`, `list_index_sources` и `semantic_search`. Тесты HTTP authentication, origin, host, loopback и project isolation прошли в обоих core-запусках.
- Архивы: `py -3.12 -m unittest scripts/test_release_archive.py -v` успешно выполнил четыре теста. Scanner принял свежие wheel/sdist `symbraid-0.3.0` и текущий VSIX после проверки содержимого.
- Benchmark: `py -3.12 benchmarks/run.py --dry-run` честно сохранил статус `not_executed`; он сообщил о dirty tree, непустых diff/repository-state hashes, hash harness, пяти adapter hashes и нуле uncollected adapter hashes.
- Hygiene и версии: регистронезависимый fixed-string поиск нашёл ноль вхождений запрещённого локального имени пользователя. `py -3.12 scripts/check_versions.py` сообщил версии core/extension `0.3.0` и timestamped-версию canonical plugin.

### Отложенные P3 и действия перед публикацией

- Повторно соберите публикуемые артефакты из hosted clean checkout и сохраните CI logs и checksums; проверенный dry-run корректно помечает текущее дерево как dirty.
- Scanner проверяет содержимое членов архива размером до 2 MiB. Перед добавлением более крупного файла примените streaming scan или отдельную проверку.
- Ни один competitor adapter не запускался. Сохраняйте `not_executed`, пока `--execute` не создаст raw artifacts по документированной воспроизводимой процедуре.
- Повторите проверку доступности точного имени и legal/trademark review непосредственно перед публикацией; датированные технические сведения ниже сохранены и не являются юридическим разрешением.

## Проверка доступности точного имени (2026-09-02)

Техническая проверка доступности 2026-09-02 не нашла точных публикаций нового
публичного имени: поиск репозиториев GitHub дал 0 точных совпадений,
https://pypi.org/project/symbraid/ вернул HTTP 404, точный поиск пакета npm
https://www.npmjs.com/package/symbraid вернул HTTP 404, точный поиск VS
Marketplace дал 0, а запрос MCP Registry для
io.github.symbraid-project/symbraid вернул HTTP 404.

Это только техническая информация о доступности, а не проверка товарных знаков
или юридическое разрешение. Повторите проверку непосредственно перед выбором
имени для релиза, пакета, расширения или MCP-идентификатора.
