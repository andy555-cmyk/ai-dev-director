"""0.3.7 HayDay mac patch: auth detection, effective roles, Grok isolation, HUD layout file."""
from pathlib import Path
from unittest.mock import Mock
import json

import core.desktop_diagnostics as diag
from core import role_settings
from core.grok_research import ISOLATION_ENV

ROOT = Path(__file__).resolve().parents[1]


def test_claude_long_lived_token_is_subscription(monkeypatch):
    out = json.dumps({'loggedIn': True, 'authMethod': 'oauth_token', 'apiProvider': 'firstParty'})
    monkeypatch.setattr(diag, 'probe', Mock(side_effect=[(0, '2.1.0 (Claude Code)', False), (0, out, False)]))
    row = diag._cli('claude', '/bin/claude')
    assert row['auth'] == 'logged_in' and row['billing'] == 'subscription'


def test_claude_api_key_still_blocked(monkeypatch):
    out = json.dumps({'loggedIn': True, 'authMethod': 'api_key'})
    monkeypatch.setattr(diag, 'probe', Mock(side_effect=[(0, '2.1.0', False), (0, out, False)]))
    assert diag._cli('claude', '/bin/claude')['auth'] == 'api_billing'


def test_grok_models_line_decides_login(monkeypatch):
    monkeypatch.setattr(diag, 'probe', Mock(side_effect=[(0, 'grok 1.0.70', False),
                                                          (0, 'You are logged in with grok.com.\n', False)]))
    assert diag._cli('grok', '/bin/grok')['auth'] == 'logged_in'
    monkeypatch.setattr(diag, 'probe', Mock(side_effect=[(0, 'grok 1.0.70', False),
                                                          (0, 'You are not authenticated.\n', False)]))
    assert diag._cli('grok', '/bin/grok')['auth'] == 'not_logged_in'


def _cfg(head, builder, reviewer):
    return {'head': {'provider': head}, 'builder': {'provider': builder}, 'reviewer': {'provider': reviewer}}


def test_effective_roles_substitute_missing_cli():
    using, notes = role_settings.effective(_cfg('claude', 'antigravity', 'codex'), {'claude', 'openai'})
    assert using == {'head': 'claude', 'builder': 'openai', 'reviewer': 'claude'}
    assert {n['role'] for n in notes} == {'builder', 'reviewer'}
    using, notes = role_settings.effective(_cfg('claude', 'antigravity', 'codex'), {'claude', 'openai', 'antigravity'})
    assert notes == [] and using['builder'] == 'antigravity'


def test_grok_isolation_env_turns_off_claude_and_cursor_imports():
    for host in ('CLAUDE', 'CURSOR'):
        for kind in ('MCPS', 'HOOKS', 'AGENTS', 'RULES', 'SKILLS'):
            assert ISOLATION_ENV['GROK_%s_%s_ENABLED' % (host, kind)] == 'false'


def test_polish_css_is_served_and_linked():
    html = (ROOT / 'console' / 'index.html').read_text(encoding='utf-8')
    server = (ROOT / 'companion_server.py').read_text(encoding='utf-8')
    assert '/polish.css' in html and "'/polish.css': 'polish.css'" in server
    css = (ROOT / 'console' / 'polish.css').read_text(encoding='utf-8')
    assert '#panel-now>*' in css and 'flex-shrink:0' in css


def test_mac_app_is_native_window_not_browser_tab():
    # 0.4.1: the app owns a WKWebView window, starts the engine as its child with BROWSER=true and stops it on quit.
    shell = (ROOT / 'packaging' / 'macos' / 'AppShell.swift').read_text(encoding='utf-8')
    assert 'WKWebView' in shell and '"--background"' in shell and 'env["BROWSER"] = "true"' in shell
    assert 'applicationShouldTerminate' in shell and 'mac_bootstrap.py' in shell
    build = (ROOT / 'packaging' / 'macos' / 'build_bundle.py').read_text(encoding='utf-8')
    assert 'AppShell.swift' in build and "'CFBundleIconFile':'AppIcon'" in build
    assert (ROOT / 'packaging' / 'macos' / 'AppIcon.icns').is_file()
    assert not (ROOT / 'packaging' / 'macos' / 'launcher').exists()
