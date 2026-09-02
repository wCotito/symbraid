package fixture;

import java.util.Map;

public final class Config {
    public static String[] parseConfig(Map<String, String> environment) {
        return new String[] {
            environment.getOrDefault("APP_HOST", "127.0.0.1"),
            environment.getOrDefault("APP_PORT", "8080"),
            environment.getOrDefault("APP_DEBUG", "false")
        };
    }
}
