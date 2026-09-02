module FixtureConfig
  def self.parse_config(environment)
    {
      host: environment.fetch('APP_HOST', '127.0.0.1'),
      port: environment.fetch('APP_PORT', '8080').to_i,
      debug: environment.fetch('APP_DEBUG', 'false') == 'true'
    }
  end
end
