#include <stdexcept>
#include <string>

struct Credentials {
    std::string access_token;
    long expires_at;
};

Credentials renew_session_credentials(const std::string& refresh_token, long now) {
    if (refresh_token.empty()) throw std::invalid_argument("refresh token required");
    return {"access:" + refresh_token, now + 900};
}

bool validate_access_token(long expires_at, long now) {
    return expires_at > now;
}
