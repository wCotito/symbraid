namespace Fixture;

public static class Config
{
    public static (string Host, int Port, bool Debug) ParseConfig(IReadOnlyDictionary<string, string> environment)
    {
        var host = environment.GetValueOrDefault("APP_HOST", "127.0.0.1");
        var port = int.TryParse(environment.GetValueOrDefault("APP_PORT", "8080"), out var value) ? value : 8080;
        var debug = environment.GetValueOrDefault("APP_DEBUG", "false") == "true";
        return (host, port, debug);
    }
}
