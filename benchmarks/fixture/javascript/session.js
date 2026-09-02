export function renewSessionCredentials(refreshToken, now) {
  if (!refreshToken) throw new Error("refresh token required");
  return { accessToken: `access:${refreshToken}`, expiresAt: now + 900 };
}

export function validateAccessToken(accessToken, now) {
  return Number.isInteger(accessToken?.expiresAt) && accessToken.expiresAt > now;
}
