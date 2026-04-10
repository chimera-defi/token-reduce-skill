#!/usr/bin/env python3
"""Minimal telemetry receiver for token-reduce opt-in payloads."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class TelemetryHandler(BaseHTTPRequestHandler):
    output_path: Path
    ingest_path: str

    def _write_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != self.ingest_path:
            self._write_json(404, {"ok": False, "error": "not_found"})
            return
        content_length = int(self.headers.get("content-length", "0") or "0")
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8", errors="ignore"))
        except json.JSONDecodeError:
            self._write_json(400, {"ok": False, "error": "invalid_json"})
            return

        event = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "client_ip": self.client_address[0],
            "payload": payload,
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
        self._write_json(200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._write_json(200, {"ok": True})
            return
        self._write_json(404, {"ok": False, "error": "not_found"})

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--path", default="/ingest")
    parser.add_argument("--output", default="./artifacts/token-reduction/ingest.jsonl")
    args = parser.parse_args()

    TelemetryHandler.output_path = Path(args.output).expanduser().resolve()
    TelemetryHandler.ingest_path = args.path

    server = HTTPServer((args.host, args.port), TelemetryHandler)
    print(
        json.dumps(
            {
                "listening": f"http://{args.host}:{args.port}{args.path}",
                "health": f"http://{args.host}:{args.port}/healthz",
                "output": str(TelemetryHandler.output_path),
            },
            indent=2,
        )
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
