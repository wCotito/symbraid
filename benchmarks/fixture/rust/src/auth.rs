pub fn renew_session_credentials(refresh_token: &str, now: i64) -> (String, i64) {
    assert!(!refresh_token.is_empty(), "refresh token required");
    (format!("access:{refresh_token}"), now + 900)
}

pub fn validate_access_token(expires_at: i64, now: i64) -> bool {
    expires_at > now
}
