"""Serve a folder on 127.0.0.1 (random free port) for the screen check, then stop. The Director owns this server,
so no generated code runs a server of its own in v4 phase 1 (static web apps only)."""
import contextlib
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _Quiet(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript',
                      '.css': 'text/css', '.svg': 'image/svg+xml', '.json': 'application/json'}

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 128


@contextlib.contextmanager
def serve(folder):
    root = Path(folder).resolve()
    if not root.is_dir():
        raise FileNotFoundError(str(root))
    httpd = _Server(('127.0.0.1', 0), functools.partial(_Quiet, directory=str(root)))
    thread = threading.Thread(target=httpd.serve_forever, name='director-static', daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:%d/' % httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()
