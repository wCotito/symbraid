package fixture

import "strconv"

func ParseConfig(environment map[string]string) (string, int, bool) {
	host := environment["APP_HOST"]
	if host == "" {
		host = "127.0.0.1"
	}
	port, err := strconv.Atoi(environment["APP_PORT"])
	if err != nil {
		port = 8080
	}
	return host, port, environment["APP_DEBUG"] == "true"
}
