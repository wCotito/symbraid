"""Authentication helpers for the benchmark fixture."""


def renew_session_credentials(refresh_token: str, now: int) -> dict[str, object]:
    """Issue short-lived credentials after accepting a refresh token."""
    if not refresh_token:
        raise ValueError("refresh token required")
    return {"access_token": f"access:{refresh_token}", "expires_at": now + 900}


def validate_access_token(access_token: dict[str, object], now: int) -> bool:
    """Reject missing, malformed, or expired access tokens."""
    expires_at = access_token.get("expires_at")
    return isinstance(expires_at, int) and expires_at > now
