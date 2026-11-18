"""Serve invented browser collection fixtures on IPv4 loopback only."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SITE = Path(__file__).parent
ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/consent/early": ("consent-early.html", "text/html; charset=utf-8"),
    "/consent/gated": ("consent-gated.html", "text/html; charset=utf-8"),
    "/dynamic": ("dynamic.html", "text/html; charset=utf-8"),
    "/unknown": ("unknown.html", "text/html; charset=utf-8"),
    "/assets/consent.js": ("consent.js", "text/javascript; charset=utf-8"),
    "/assets/dynamic.js": ("dynamic.js", "text/javascript; charset=utf-8"),
}
CONSENT_SOURCES = {"early", "gated"}
CONSENT_EVENTS = {"load", "accept"}


class FixtureHandler(BaseHTTPRequestHandler):
    def reply(self, status, content_type, body=b""):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; connect-src 'self'; "
            "form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        request = urlsplit(self.path)
        if request.path == "/policy/blocked":
            self.reply(
                403,
                "text/plain; charset=utf-8",
                b"Synthetic fixture: policy response unavailable on this route.\n",
            )
            return
        if request.path == "/events/optional":
            fields = parse_qs(request.query, keep_blank_values=True)
            if (
                set(fields) == {"source", "event"}
                and len(fields["source"]) == 1
                and fields["source"][0] in CONSENT_SOURCES
                and len(fields["event"]) == 1
                and fields["event"][0] in CONSENT_EVENTS
            ):
                self.reply(204, "text/plain; charset=utf-8")
            else:
                self.reply(400, "text/plain; charset=utf-8", b"Unexpected fixture event\n")
            return
        route = ROUTES.get(request.path)
        if route is None:
            self.reply(404, "text/plain; charset=utf-8", b"Unknown fixture route\n")
            return
        filename, content_type = route
        self.reply(200, content_type, (SITE / filename).read_bytes())

    do_HEAD = do_GET

    def do_POST(self):
        self.reply(405, "text/plain; charset=utf-8", b"Fixture does not accept submissions\n")

    def log_request(self, code="-", size="-"):
        # Browser developer tools show the requests. The server stores no event log.
        pass


def build_server(port=0):
    return ThreadingHTTPServer(("127.0.0.1", port), FixtureHandler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0, help="Loopback port. Zero selects a free port.")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    with build_server(args.port) as server:
        print(f"http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
