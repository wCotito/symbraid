#include <string>
#include <unordered_map>

struct Config {
    std::string host;
    int port;
    bool debug;
};

Config parse_config(const std::unordered_map<std::string, std::string>& environment) {
    const auto host = environment.contains("APP_HOST") ? environment.at("APP_HOST") : "127.0.0.1";
    return {host, 8080, environment.contains("APP_DEBUG") && environment.at("APP_DEBUG") == "true"};
}
