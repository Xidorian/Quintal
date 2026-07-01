"""Local ingest receiver for browser-session collection.

The tool channel that returns JavaScript results to the assistant has a tiny output
cap, so paging dozens of listing cards back through it doesn't scale. Instead the page
POSTs extracted rows straight to this loopback server, which maps them through the site
adapter and upserts into data/listings.jsonl. Data flows page → 127.0.0.1, never through
the assistant's context.

Security: binds to 127.0.0.1 only, and CORS is restricted to the two portals' origins
(not '*') so a random site you visit while it's running can't push rows. It's meant to be
run briefly during a collection session and stopped afterwards.
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..logconf import get_logger
from . import idealista, imovirtual, store

log = get_logger()
ADAPTERS = {a.name: a for a in (idealista, imovirtual)}
ALLOWED_ORIGINS = {
    "https://www.idealista.pt",
    "https://www.imovirtual.com",
}
DEFAULT_STORE = "data/listings.jsonl"


def ingest_rows(site: str, rows: list[dict], store_path: str) -> tuple[int, int]:
    """Map extracted rows through the adapter and upsert. Returns (added, updated)."""
    if site not in ADAPTERS:
        raise ValueError(f"unknown site: {site}")
    raw = [ADAPTERS[site].to_raw(row) for row in rows]
    return store.upsert(store_path, raw)


def _make_handler(store_path: str):
    class Handler(BaseHTTPRequestHandler):
        def _cors(self) -> None:
            origin = self.headers.get("Origin", "")
            if origin in ALLOWED_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            # Chrome Private Network Access: a public HTTPS page → localhost preflight is
            # blocked unless the server explicitly opts in here.
            self.send_header("Access-Control-Allow-Private-Network", "true")

        def _json(self, code: int, body: dict) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self) -> None:  # CORS preflight
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {"ok": True})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/ingest":
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                site = body.get("site")
                rows = body.get("rows", [])
                if not isinstance(rows, list):
                    raise ValueError("rows must be a list")
                added, updated = ingest_rows(site, rows, store_path)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            log.info(
                "received rows",
                extra={
                    "event": "received",
                    "ctx_site": site,
                    "ctx_added": added,
                    "ctx_updated": updated,
                },
            )
            self._json(200, {"added": added, "updated": updated})

        def log_message(self, *args) -> None:  # silence default stderr access log
            pass

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8231, store_path: str = DEFAULT_STORE) -> None:
    httpd = ThreadingHTTPServer((host, port), _make_handler(store_path))
    log.info(
        "receiver listening", extra={"event": "receiver_up", "ctx_url": f"http://{host}:{port}"}
    )
    print(f"Quintal receiver on http://{host}:{port}  (POST /ingest, GET /health)")
    httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Quintal local ingest receiver")
    parser.add_argument("--port", type=int, default=8231)
    parser.add_argument("--store", default=DEFAULT_STORE)
    args = parser.parse_args()
    serve(port=args.port, store_path=args.store)


if __name__ == "__main__":
    main()
