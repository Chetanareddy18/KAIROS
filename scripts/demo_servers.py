"""Demo "company systems" for the live connector demo: an FTP server and a REST API.

    python scripts/demo_servers.py

  FTP   127.0.0.1:2121   user kairos / password from DEMO_FTP_PASS (default kairos-demo)
        serves data/demo/ftp  (logistics_*.csv.gz)
  REST  127.0.0.1:8090   GET /api/v1/kpis?page=N&since=ISO   (Bearer token from DEMO_API_TOKEN)

To show "only new files are fetched", copy another .csv.gz into data/demo/ftp/kpis
while KAIROS is running and press Sync on the Data Sources page.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "data" / "demo"
FTP_PASS = os.getenv("DEMO_FTP_PASS", "kairos-demo")
API_TOKEN = os.getenv("DEMO_API_TOKEN", "demo-token")
PAGE_SIZE = 100


def run_ftp() -> None:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    auth = DummyAuthorizer()
    auth.add_user("kairos", FTP_PASS, str(DEMO / "ftp"), perm="elr")      # read-only account
    handler = type("DemoFTP", (FTPHandler,), {"authorizer": auth, "banner": "ACME logistics export server"})
    FTPServer(("127.0.0.1", 2121), handler).serve_forever()


class Api(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/api/v1/kpis":
            return self._send(404, {"error": "not found"})
        if self.headers.get("Authorization") != f"Bearer {API_TOKEN}":
            return self._send(401, {"error": "bad token"})
        q = parse_qs(url.query)
        records = json.loads((DEMO / "support_api.json").read_text())
        since = q.get("since", [None])[0]
        if since:                                   # ISO timestamp, compare in the records' own format
            since = since[:19] + "Z"
            records = [r for r in records if r["hour"] >= since]
        page = int(q.get("page", ["1"])[0])
        chunk = records[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
        self._send(200, {"data": chunk, "page": page, "total": len(records)})

    def _send(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args):
        print("[rest]", fmt % args)


def main() -> None:
    if not (DEMO / "support_api.json").exists():
        raise SystemExit("run `python scripts/generate_demo_sources.py` first")
    os.environ.setdefault("DEMO_FTP_PASS", FTP_PASS)
    threading.Thread(target=run_ftp, daemon=True).start()
    print(f"FTP  on ftp://127.0.0.1:2121  (user kairos, password {FTP_PASS!r})")
    print(f"REST on http://127.0.0.1:8090/api/v1/kpis  (Bearer {API_TOKEN!r})")
    print("set DEMO_FTP_PASS and DEMO_API_TOKEN in KAIROS's .env to the same values. Ctrl+C to stop.")
    ThreadingHTTPServer(("127.0.0.1", 8090), Api).serve_forever()


if __name__ == "__main__":
    main()
