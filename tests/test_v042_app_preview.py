"""0.4.2 「앱 열어 보기」: a delivered static app is served on its own local port, with example data on first visit."""
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from core import app_preview

ROOT = Path(__file__).resolve().parents[1]


def _app(tmp_path, name='proj'):
    p = tmp_path / name
    (p / '.git').mkdir(parents=True)
    (p / '.git' / 'config').write_text('secret')
    (p / 'index.html').write_text('<!doctype html><html><head><title>t</title></head><body>앱</body></html>', encoding='utf-8')
    (p / 'app.js').write_text('console.log(1)')
    return p


def _plan(tmp_path, demo):
    spec = tmp_path / 'plan' / 'spec'
    spec.mkdir(parents=True)
    if demo is not None:
        (spec / 'demo_data.json').write_text(json.dumps(demo), encoding='utf-8')
    return str(tmp_path / 'plan')


def _get(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.status, r.read().decode('utf-8')


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app_preview.stop_all()


def test_serves_ready_app_with_seed_and_hides_dot_folders(tmp_path):
    proj = _app(tmp_path)
    d = {'delivery_id': 'DLV-T1', 'phase': 'READY', 'project_path': str(proj),
         'plan_dir': _plan(tmp_path, {'version': 1, 'members': [{'id': 'm1', 'name': '</script>'}]})}
    r = app_preview.open_preview(d)
    assert r['url'].startswith('http://127.0.0.1:') and r['demo'] is True
    status, html = _get(r['url'])
    assert status == 200 and "localStorage.getItem(\"app-data-v1\")" in html and '<\\/script>' in html
    assert html.index('localStorage') < html.index('<title>')         # seed runs before the app's own scripts
    assert _get(r['url'] + 'app.js')[1] == 'console.log(1)'
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(r['url'] + '.git/config')
    assert e.value.code == 404
    assert app_preview.open_preview(d)['url'] == r['url']              # reused, same address


def test_no_demo_no_seed_and_port_is_stable(tmp_path):
    proj = _app(tmp_path)
    d = {'delivery_id': 'DLV-T2', 'phase': 'READY', 'project_path': str(proj), 'plan_dir': _plan(tmp_path, None)}
    r = app_preview.open_preview(d)
    assert r['demo'] is False and 'localStorage' not in _get(r['url'])[1]
    assert r['url'].endswith(':%d/' % app_preview.port_for('DLV-T2'))


def test_before_release_uses_latest_accepted_worktree(tmp_path):
    proj = _app(tmp_path, 'proj')
    work = _app(tmp_path, 'work')
    (work / 'index.html').write_text('<html><head></head><body>작업본</body></html>', encoding='utf-8')
    d = {'delivery_id': 'DLV-T3', 'phase': 'WAIT_SCREEN_APPROVAL', 'project_path': str(proj), 'last_accepted': str(work)}
    assert app_preview.app_root(d) == work.resolve()
    assert '작업본' in _get(app_preview.open_preview(d)['url'])[1]


def test_no_index_is_a_clear_error(tmp_path):
    d = {'delivery_id': 'DLV-T4', 'phase': 'BUILDING', 'project_path': str(tmp_path)}
    with pytest.raises(ValueError):
        app_preview.open_preview(d)


def test_console_button_and_route_are_wired():
    js = (ROOT / 'console' / 'delivery.js').read_text(encoding='utf-8')
    assert '앱 열어 보기' in js and "base+'preview'" in js and "window.open('about:blank'" in js
    server = (ROOT / 'companion_server.py').read_text(encoding='utf-8')
    assert "action == 'preview'" in server and 'app_preview.open_preview' in server
    shell = (ROOT / 'packaging' / 'macos' / 'AppShell.swift').read_text(encoding='utf-8')
    assert 'javaScriptCanOpenWindowsAutomatically = true' in shell


def test_many_files_at_once_are_all_served(tmp_path):
    """A module app loads ~10 files in parallel; none may be reset (blank screen bug found in the real app)."""
    import concurrent.futures
    proj = _app(tmp_path)
    for i in range(40):
        (proj / ('m%d.js' % i)).write_text('// %d' % i)
    r = app_preview.open_preview({'delivery_id': 'DLV-T5', 'phase': 'READY', 'project_path': str(proj)})
    with concurrent.futures.ThreadPoolExecutor(40) as ex:
        got = list(ex.map(lambda i: _get(r['url'] + 'm%d.js' % i)[1], range(40)))
    assert got == ['// %d' % i for i in range(40)]
