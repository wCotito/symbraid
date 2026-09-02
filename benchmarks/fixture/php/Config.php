<?php

final class Config
{
    public static function parseConfig(array $environment): array
    {
        return [
            'endpoint' => $environment['APP_ENDPOINT'] ?? 'https://example.invalid',
            'timeout' => (int) ($environment['APP_TIMEOUT'] ?? 30),
        ];
    }
}

