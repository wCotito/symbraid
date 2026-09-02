# Правила безопасности

О suspected vulnerability сообщайте приватно по процессу в [корневом
SECURITY.md](../../../SECURITY.md). Не добавляйте credentials, tokens, private
source text или данные database в public issues, logs, fixtures и benchmark
artifacts.

Core хранит один managed source на project и сохраняет старый source при
migration. MCP предоставляет только read-only инструменты. Optional HTTP
работает только на loopback, требует token и проверяет origin. Plugin и
extension не пишут index и не импортируют backend libraries.

Secrets принимаются защищённым вводом и хранятся в OS keyring. Разрешённая
headless env-ссылка может называть переменную, но value не сериализуется, не
передаётся аргументом CLI и не логируется.

