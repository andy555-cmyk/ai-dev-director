import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler

import pytest
from dashboard_server import DashboardAlreadyRunning, DashboardServer, DashboardHandler


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

    def log_message(self, *args):
        pass


def test_duplicate_active_listener_still_rejected():
    first = DashboardServer(('127.0.0.1', 0), HealthHandler)
    try:
        with pytest.raises(DashboardAlreadyRunning):
            DashboardServer(first.server_address, HealthHandler)
    finally:
        first.server_close()


def test_closed_terminal_does_not_break_http_response(monkeypatch):
    import http.server
    def broken_log(*args): raise OSError(5, 'revoked Terminal')
    monkeypatch.setattr(http.server.BaseHTTPRequestHandler,'log_message',broken_log)
    class Handler(DashboardHandler):
        def do_GET(self): self._send_json({'ok':True})
    server=DashboardServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port),timeout=3) as response:
            assert response.status==200 and b'"ok": true' in response.read()
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX TIME_WAIT reuse')
def test_immediate_restart_after_serving_a_request():
    server = DashboardServer(('127.0.0.1', 0), HealthHandler)
    address = server.server_address
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with urllib.request.urlopen('http://127.0.0.1:' + str(address[1]), timeout=3) as response:
            assert response.read() == b'OK'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    restarted = DashboardServer(address, HealthHandler)
    restarted.server_close()
