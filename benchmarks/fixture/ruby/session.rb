module FixtureSession
  def self.renew_session_credentials(refresh_token, now)
    raise ArgumentError, 'refresh token required' if refresh_token.to_s.empty?

    { access_token: "access:#{refresh_token}", expires_at: now + 900 }
  end

  def self.validate_access_token(access_token, now)
    access_token[:expires_at].is_a?(Integer) && access_token[:expires_at] > now
  end
end
