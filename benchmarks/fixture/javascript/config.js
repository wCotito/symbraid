export function parseConfig(environment) {
  return {
    host: environment.APP_HOST ?? "127.0.0.1",
    port: Number(environment.APP_PORT ?? "8080"),
    debug: (environment.APP_DEBUG ?? "false").toLowerCase() === "true",
  };
}
