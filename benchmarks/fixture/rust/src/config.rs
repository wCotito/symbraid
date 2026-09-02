use std::collections::HashMap;

pub fn parse_config(environment: &HashMap<String, String>) -> (String, u16, bool) {
    let host = environment.get("APP_HOST").cloned().unwrap_or_else(|| "127.0.0.1".into());
    let port = environment.get("APP_PORT").and_then(|value| value.parse().ok()).unwrap_or(8080);
    let debug = environment.get("APP_DEBUG").map(|value| value == "true").unwrap_or(false);
    (host, port, debug)
}
