namespace Fixture;

public static class SessionService
{
    public static (string AccessToken, long ExpiresAt) RenewSessionCredentials(string refreshToken, long now)
    {
        if (string.IsNullOrWhiteSpace(refreshToken)) throw new ArgumentException("refresh token required");
        return ($"access:{refreshToken}", now + 900);
    }

    public static bool ValidateAccessToken(long expiresAt, long now) => expiresAt > now;
}
