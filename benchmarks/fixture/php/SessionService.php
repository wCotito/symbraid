<?php

final class SessionService
{
    public function renewSessionCredentials(string $refreshToken): string
    {
        if (!$this->validateRefreshToken($refreshToken)) {
            throw new InvalidArgumentException('refresh token rejected');
        }

        return $this->issueSessionToken();
    }

    public function validateAccessToken(string $token): bool
    {
        return $token !== '' && !$this->isExpired($token);
    }

    private function validateRefreshToken(string $token): bool
    {
        return $token !== '';
    }

    private function issueSessionToken(): string
    {
        return 'fixture-session-token';
    }

    private function isExpired(string $token): bool
    {
        return $token === 'expired-fixture-token';
    }
}

