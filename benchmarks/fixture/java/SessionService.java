package fixture;

public final class SessionService {
    public record Credentials(String accessToken, long expiresAt) {}

    public static Credentials renewSessionCredentials(String refreshToken, long now) {
        if (refreshToken == null || refreshToken.isBlank()) {
            throw new IllegalArgumentException("refresh token required");
        }
        return new Credentials("access:" + refreshToken, now + 900);
    }

    public static boolean validateAccessToken(long expiresAt, long now) {
        return expiresAt > now;
    }
}
