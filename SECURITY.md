# Безопасность

Не публикуйте API keys, содержимое Windows Credential Manager, `config.json` с
локальными путями, model cache, vector indexes или исходный код индексируемых
закрытых проектов.

Секреты Code Index должны передаваться только через stdin-флаги CLI и храниться
через `keyring`. Сообщения об уязвимостях не должны включать реальные credentials
или private payload из Qdrant/LanceDB.

Code Index изменяет только созданные им managed sources. Изменение неизвестного
внешнего индекса или добавление mutating MCP tools считается security regression.
