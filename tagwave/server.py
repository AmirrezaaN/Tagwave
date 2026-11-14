"""Local HTTP server between the UI (WebView2) and the Python backend.

Bound to 127.0.0.1 only. Every API/media request must carry a random per-run token,
and the Host header must match, so other programs and web pages can't use it.
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import queue
import re
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import paths
from .jobs import error_json

CHUNK = 4 * 1024 * 1024
MAX_BODY = 80 * 1024 * 1024
STATIC_TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
                ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2",
                ".woff": "font/woff", ".ttf": "font/ttf", ".png": "image/png", ".ico": "image/x-icon",
                ".json": "application/json", ".webp": "image/webp", ".jpg": "image/jpeg"}
_BLOB = re.compile(r"^/media/(blob|thumb)/([0-9a-f]{40})$")
_AUDIO = re.compile(r"^/media/audio/(f\d+)$")


class Server:
    def __init__(self, api, port: int = 0, token: str | None = None, ui_dir: str | None = None,
                 allow_hosts: tuple = ()):
        self.api = api
        self.token = token or secrets.token_urlsafe(24)
        self.ui_dir = os.path.abspath(ui_dir or paths.ui_dir())
        self.httpd = _HTTPServer(("127.0.0.1", port), _Handler)
        self.httpd.app = self
        self.port = self.httpd.server_address[1]
        self.allowed_hosts = {"127.0.0.1:%d" % self.port, "localhost:%d" % self.port, *allow_hosts}
        self._thread = None

    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d/?t=%s" % (self.port, self.token)

    def start(self) -> None:
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="http", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class _Handler(BaseHTTPRequestHandler):
    server_version = "Tagwave"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):  # silence default logging
        pass

    @property
    def app(self) -> Server:
        return self.server.app  # type: ignore[attr-defined]

    # ----------------------------------------------------------- security
    def _host_ok(self) -> bool:
        return (self.headers.get("Host") or "") in self.app.allowed_hosts

    def _token_ok(self, query: dict) -> bool:
        tok = self.headers.get("X-Tagwave-Token") or (query.get("t") or [""])[0]
        return hmac.compare_digest(tok.encode(), self.app.token.encode())

    def _deny(self, code=403):
        self._send(code, b"Forbidden", "text/plain")

    # ------------------------------------------------------------- output
    def _send(self, code: int, body: bytes, ctype: str, headers: dict | None = None):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                   {"Cache-Control": "no-store"})

    # ---------------------------------------------------------------- GET
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._deny()
        url = urlparse(self.path)
        q = parse_qs(url.query)
        path = unquote(url.path)
        try:
            if path == "/api/events":
                return self._events(q) if self._token_ok(q) else self._deny()
            if path.startswith("/media/"):
                if not self._token_ok(q):
                    return self._deny()
                m = _BLOB.match(path)
                if m:
                    return self._blob(m.group(1), m.group(2), q)
                m = _AUDIO.match(path)
                if m:
                    return self._audio(m.group(1))
                return self._send(404, b"Not found", "text/plain")
            return self._static(path)
        except KeyError:
            self._send(404, b"Not found", "text/plain")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._send(500, b"Error", "text/plain")

    def _static(self, path: str):
        root = self.app.ui_dir
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.abspath(os.path.join(root, rel))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            if "." not in os.path.basename(rel):   # SPA fallback
                full = os.path.join(root, "index.html")
            else:
                return self._send(404, b"Not found", "text/plain")
        ext = os.path.splitext(full)[1].lower()
        ctype = STATIC_TYPES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            body = f.read()
        cache = "no-cache" if ext == ".html" else "max-age=31536000, immutable"
        csp = ("default-src 'self'; img-src 'self' data: blob: https:; media-src 'self' blob:; "
               "style-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self'; "
               "script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self._send(200, body, ctype, {"Cache-Control": cache, "Content-Security-Policy": csp,
                                      "Referrer-Policy": "no-referrer"})

    def _blob(self, kind: str, blob_id: str, q: dict):
        store = self.app.api.blobs
        if kind == "thumb":
            size = int((q.get("s") or ["128"])[0])
            p, mime = store.thumbnail(blob_id, size)
            with open(p, "rb") as f:
                body = f.read()
        else:
            body = store.read(blob_id)
            mime = store.meta(blob_id)["mime"]
        self._send(200, body, mime, {"Cache-Control": "max-age=31536000, immutable"})

    def _audio(self, file_id: str):
        path, mime = self.app.api.audio_file(file_id)
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        partial = False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if not m:
                return self._send(416, b"", "text/plain", {"Content-Range": "bytes */%d" % size})
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            elif m.group(2):
                start = max(0, size - int(m.group(2)))
            if start >= size or start > end:
                return self._send(416, b"", "text/plain", {"Content-Range": "bytes */%d" % size})
            partial = True
        # Bounded responses keep file handles short-lived, so saving tags of the
        # file being played never collides with the stream.
        end = min(end, start + CHUNK - 1)
        with open(path, "rb") as f:
            f.seek(start)
            body = f.read(end - start + 1)
        headers = {"Accept-Ranges": "bytes", "Cache-Control": "no-store"}
        if partial or end < size - 1:
            headers["Content-Range"] = "bytes %d-%d/%d" % (start, start + len(body) - 1, size)
            return self._send(206, body, mime, headers)
        return self._send(200, body, mime, headers)

    def _events(self, q: dict):
        bus = self.app.api.bus
        sub = bus.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    msg = sub.get(timeout=15)
                    data = "data: " + msg.replace("\n", "\\n") + "\n\n"
                except queue.Empty:
                    data = ": keep-alive\n\n"
                self.wfile.write(data.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            bus.unsubscribe(sub)

    # --------------------------------------------------------------- POST
    def do_POST(self):
        if not self._host_ok():
            return self._deny()
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if not self._token_ok(q):
            return self._deny()
        origin = self.headers.get("Origin")
        if origin and origin.split("://", 1)[-1] not in self.app.allowed_hosts:
            return self._deny()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send(400, b"Bad request", "text/plain")
        if length > MAX_BODY:
            return self._send(413, b"Too large", "text/plain")
        body = self.rfile.read(length) if length else b""
        try:
            if url.path == "/api/call":
                req = json.loads(body.decode("utf-8") or "{}")
                result = self.app.api.call(req.get("method", ""), req.get("params") or {})
                return self._json({"ok": True, "result": result})
            if url.path == "/api/upload":
                return self._json({"ok": True, "result": self.app.api.upload_image(body)})
            return self._send(404, b"Not found", "text/plain")
        except Exception as exc:  # noqa: BLE001
            err = error_json(exc)
            if err["code"] == "error":
                traceback.print_exc()
            return self._json({"ok": False, "error": err})
