"""「앱 열어 보기」(0.4.2): serve a delivered static web app on its own local port so the owner can use it.

- One small HTTP server per delivery, bound to 127.0.0.1 only. The port is derived from the delivery id, so the
  same app keeps the same address (and the same browser storage) across restarts.
- Serves the finished project folder; before release approval, the latest accepted worktree.
- Example data: when the plan has spec/demo_data.json, a first visit with empty storage gets it in localStorage
  (`app-data-v1`, the v4 template key) so the screens are not blank. The owner's own edits are never overwritten.
- Dot folders (.git, .director_worktrees, ...) are never served.
"""
import functools
import http.server
import json
import threading
import zlib
from pathlib import Path
from typing import Any, Dict, Optional

STORAGE_KEY = 'app-data-v1'
PORT_BASE, PORT_SPAN = 18100, 800
_SERVERS: Dict[str, Dict[str, Any]] = {}
_GUARD = threading.Lock()


def app_root(d: Dict[str, Any]) -> Optional[Path]:
    """Folder that holds the app's index.html, or None."""
    candidates = []
    if d.get('phase') != 'READY' and d.get('last_accepted'):
        candidates.append(Path(d['last_accepted']))
    if d.get('project_path'):
        candidates.append(Path(d['project_path']))
    for c in candidates:
        if (c / 'index.html').is_file():
            return c.resolve()
    return None


def demo_data(d: Dict[str, Any]) -> Optional[str]:
    if not d.get('plan_dir'):
        return None
    p = Path(d['plan_dir']) / 'spec' / 'demo_data.json'
    try:
        text = p.read_text(encoding='utf-8')
        json.loads(text)
        return text
    except (OSError, ValueError):
        return None


def seed_script(demo: Optional[str]) -> str:
    if not demo:
        return ''
    return ('<script>(function(){try{if(!localStorage.getItem(%s))localStorage.setItem(%s,%s);}catch(e){}})();</script>'
            % (json.dumps(STORAGE_KEY), json.dumps(STORAGE_KEY), json.dumps(demo).replace('</', '<\\/')))


class _Handler(http.server.SimpleHTTPRequestHandler):
    seed = ''

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def _blocked(self) -> bool:
        path = self.path.split('?', 1)[0].split('#', 1)[0]
        return any(part.startswith('.') for part in path.split('/') if part)

    def do_HEAD(self):
        if self._blocked():
            return self.send_error(404)
        return super().do_HEAD()

    def do_GET(self):
        if self._blocked():
            return self.send_error(404)
        path = self.path.split('?', 1)[0].split('#', 1)[0]
        if self.seed and path in ('/', '/index.html'):
            try:
                html = (Path(self.directory) / 'index.html').read_text(encoding='utf-8')
            except OSError:
                return self.send_error(404)
            low = html.lower()
            at = low.find('<head>')
            html = html[:at + 6] + self.seed + html[at + 6:] if at >= 0 else self.seed + html
            body = html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


class _Server(http.server.ThreadingHTTPServer):
    # Browsers fetch a module app's ~10 files at once; the stdlib backlog of 5 resets some of them (blank screen).
    request_queue_size = 128
    daemon_threads = True


def port_for(delivery_id: str) -> int:
    return PORT_BASE + zlib.crc32(delivery_id.encode('utf-8')) % PORT_SPAN


def open_preview(d: Dict[str, Any]) -> Dict[str, Any]:
    """Start (or reuse) the preview server for a delivery and return its URL."""
    ident = d['delivery_id']
    root = app_root(d)
    if root is None:
        raise ValueError('아직 열어 볼 앱 화면이 없습니다')
    seed = seed_script(demo_data(d))
    with _GUARD:
        cur = _SERVERS.get(ident)
        if cur and cur['root'] == root and cur['seed'] == seed and cur['thread'].is_alive():
            return {'url': cur['url'], 'root': str(root), 'demo': bool(seed)}
        if cur:
            _stop(cur)
        handler = type('PreviewHandler', (_Handler,), {'seed': seed})
        factory = functools.partial(handler, directory=str(root))
        server, start = None, port_for(ident)
        for i in range(40):
            port = PORT_BASE + (start - PORT_BASE + i) % PORT_SPAN
            try:
                server = _Server(('127.0.0.1', port), factory)
                break
            except OSError:
                continue
        if server is None:
            raise ValueError('열어 볼 포트를 찾지 못했습니다')
        t = threading.Thread(target=server.serve_forever, name='preview-' + ident, daemon=True)
        t.start()
        url = 'http://127.0.0.1:%d/' % server.server_address[1]
        _SERVERS[ident] = {'server': server, 'thread': t, 'root': root, 'seed': seed, 'url': url}
        return {'url': url, 'root': str(root), 'demo': bool(seed)}


def _stop(entry):
    try:
        entry['server'].shutdown()
        entry['server'].server_close()
    except Exception:
        pass


def stop_all():
    with _GUARD:
        for entry in _SERVERS.values():
            _stop(entry)
        _SERVERS.clear()
