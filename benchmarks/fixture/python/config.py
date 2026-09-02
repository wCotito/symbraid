"""Configuration parser for the benchmark fixture."""


def parse_config(environment: dict[str, str]) -> dict[str, object]:
    return {
        "host": environment.get("APP_HOST", "127.0.0.1"),
        "port": int(environment.get("APP_PORT", "8080")),
        "debug": environment.get("APP_DEBUG", "false").lower() == "true",
    }
