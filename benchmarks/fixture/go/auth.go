package fixture

import "fmt"

func RenewSessionCredentials(refreshToken string, now int64) (string, int64) {
	if refreshToken == "" {
		panic("refresh token required")
	}
	return fmt.Sprintf("access:%s", refreshToken), now + 900
}

func ValidateAccessToken(expiresAt, now int64) bool {
	return expiresAt > now
}
