"""Resilient static file server for the Smart PDA Generator.

Replaces `python -m http.server`, which is single-threaded and dies when a
browser drops a connection mid-request.

  * Threaded      - one stalled/aborted request can't take the server down.
  * Fault tolerant- client disconnects are swallowed instead of raising.
  * No-cache      - always serves the latest build, so a plain refresh is
                    enough; no more Ctrl+Shift+R to escape stale JavaScript.

Usage:  python serve.py [port]      (default 5500)
"""

import os
import socket
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
ROOT = os.path.dirname(os.path.abspath(__file__))
# The app under development.
APP = "Smart_PDA_GeneratorV2.html"


class Handler(SimpleHTTPRequestHandler):
    # A client that opens a socket and then stops talking must not pin a worker
    # thread forever. socketserver applies this to the connection, so a silent
    # or half-open peer is dropped instead of wedging the server.
    timeout = 30

    def end_headers(self):
        # Never let the browser cache the app while we're iterating on it
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_head(self):
        # Drop conditional-request headers so we never answer "304 Not Modified"
        # with a stale copy — every request gets the file as it is on disk now.
        for header in ("If-Modified-Since", "If-None-Match"):
            if header in self.headers:
                del self.headers[header]
        # The root URL is the app, not a directory listing. Rewrite it before the
        # base class resolves the path, so http://localhost:PORT/ opens the
        # generator. Everything else (data/, regression_matrix.html) is untouched.
        path, sep, query = self.path.partition("?")
        if path in ("", "/", "/index.html"):
            self.path = "/" + APP + sep + query
        return super().send_head()

    # Re-locking the regression baseline used to mean a browser download followed
    # by a manual copy into data/. That is the kind of two-step nobody does, so the
    # baseline drifts and the matrix stops meaning anything. This makes it one
    # click from the harness. Deliberately narrow: localhost only, one exact path,
    # JSON only, size-capped, and it keeps a timestamped copy of what it replaced.
    SAVE_PATH = "/data/regression_baseline.json"
    MAX_SAVE = 8 * 1024 * 1024

    def do_PUT(self):
        if self.path != self.SAVE_PATH:
            self.send_error(404, "Only " + self.SAVE_PATH + " may be written")
            return
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self.send_error(403, "Local requests only")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.send_error(400, "Bad Content-Length")
            return
        if length <= 0 or length > self.MAX_SAVE:
            self.send_error(413, "Body must be 1 byte to %d" % self.MAX_SAVE)
            return
        body = self.rfile.read(length)
        try:
            import json
            parsed = json.loads(body.decode("utf-8"))
            if not isinstance(parsed, dict) or "cases" not in parsed:
                raise ValueError("not a baseline payload (no 'cases')")
        except Exception as e:
            self.send_error(400, "Not a valid baseline: %s" % e)
            return

        target = os.path.join(ROOT, "data", "regression_baseline.json")
        # Never overwrite the old baseline without keeping it — it is the only
        # record of what the engine used to produce.
        if os.path.exists(target):
            import shutil, time
            backup = target.replace(".json", ".%s.bak.json" % time.strftime("%Y%m%d-%H%M%S"))
            shutil.copy2(target, backup)
        with open(target, "wb") as fh:
            fh.write(body)
        msg = ('{"ok":true,"bytes":%d,"cases":%d}'
               % (len(body), len(parsed.get("cases") or {}))).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)

    def handle_one_request(self):
        # A browser that closes a connection early — or goes silent — must never
        # take the server down or hold the thread. Drop the connection and move on.
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError,
                TimeoutError, socket.timeout):
            self.close_connection = True
        except OSError as e:                     # any other socket-level fault
            sys.stderr.write("socket error, dropping connection: %s\n" % e)
            self.close_connection = True

    def handle(self):
        # Belt and braces: never let an exception escape into the accept loop
        try:
            super().handle()
        except Exception as e:
            sys.stderr.write("request aborted: %s\n" % e)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


class Server(ThreadingHTTPServer):
    daemon_threads = True      # worker threads never block shutdown
    allow_reuse_address = True  # restart immediately without TIME_WAIT errors


def main():
    httpd = Server(("", PORT), partial(Handler, directory=ROOT))
    print("Smart PDA Generator -> http://localhost:%d/" % PORT)
    print("Serving %s (threaded, no-cache). Ctrl+C to stop." % ROOT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
