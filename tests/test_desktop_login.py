"""Login dispatch, shell quoting and HTTP boundaries, without a real authentication flow."""
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import desktop_login as login
from tests.test_v301_companion_http import http_server, request


@pytest.fixture
def login_env(tmp_path, monkeypatch):
    executable = tmp_path / "로그인 도구 ' $(unused)"
    executable.write_text('#!/bin/sh\nfor arg do printf "arg:%s\\n" "$arg"; done\n'
                          'test -z "${OPENAI_API_KEY+x}" || exit 42\n'
                          'test -z "${CLAUDE_CODE_OAUTH_TOKEN+x}" || exit 43\n')
    executable.chmod(0o755)
    monkeypatch.setattr(login.sys, 'platform', 'darwin')
    monkeypatch.setattr(login, 'resolve_cli', lambda provider: str(executable))
    monkeypatch.setattr(login, '_LAST_OPENED', {})
    return executable


@pytest.mark.parametrize('provider,args', [
    ('claude', ('auth', 'login', '--claudeai')), ('codex', ('login',)), ('agy', ()), ('grok', ('login', '--oauth')),
])
def test_command_uses_official_flow_quotes_paths_and_removes_api_credentials(tmp_path, monkeypatch, login_env, provider, args):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-secret-api-value')
    monkeypatch.setenv('CLAUDE_CODE_OAUTH_TOKEN', 'test-secret-oauth-value')
    workspace = tmp_path / "빈 폴더 ' $(unused)"
    workspace.mkdir()
    body = login.login_script(provider, str(login_env), workspace)
    assert 'test-secret' not in body
    script = tmp_path / 'login.command'; script.write_text(body)
    result = subprocess.run(['/bin/bash', str(script)], capture_output=True, text=True, timeout=3)
    assert result.returncode == 0
    assert tuple(line[4:] for line in result.stdout.splitlines() if line.startswith('arg:')) == args
    assert not (tmp_path / 'unused').exists()


def test_dispatch_opens_terminal_without_capturing_auth_output(tmp_path, monkeypatch, login_env):
    runner = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(login.subprocess, 'run', runner)
    result = login.open_login('claude', {}, tmp_path)
    assert result['status'] == 'opened'
    argv = runner.call_args.args[0]
    assert argv[:3] == ['/usr/bin/open', '-a', 'Terminal']
    script = Path(argv[3])
    assert script.stat().st_mode & 0o777 == 0o700
    assert runner.call_args.kwargs['stdout'] == subprocess.DEVNULL
    assert runner.call_args.kwargs['stderr'] == subprocess.DEVNULL
    with pytest.raises(login.LoginError) as exc:
        login.open_login('claude', {}, tmp_path)
    assert exc.value.code == 409 and runner.call_count == 1
    assert 'token' not in json.dumps(result).lower()


def test_failed_dispatch_cleans_only_generated_command(tmp_path, monkeypatch, login_env):
    monkeypatch.setattr(login.subprocess, 'run', Mock(side_effect=OSError('private diagnostic')))
    with pytest.raises(login.LoginError) as exc:
        login.open_login('codex', {}, tmp_path)
    assert exc.value.code == 500 and 'private diagnostic' not in str(exc.value)
    assert not list((tmp_path / 'data/cli-login').glob('*.command'))
    assert not login._LAST_OPENED


@pytest.mark.parametrize('provider', ['codex; touch /tmp/unsafe', '', None, [], 'other'])
def test_unknown_provider_cannot_launch_or_write(tmp_path, monkeypatch, provider):
    before = set(tmp_path.iterdir())
    runner = Mock(); monkeypatch.setattr(login.subprocess, 'run', runner)
    with pytest.raises(login.LoginError):
        login.open_login(provider, {}, tmp_path)
    runner.assert_not_called()
    assert set(tmp_path.iterdir()) == before


def test_configured_role_executable_is_used_and_missing_cli_is_explained(tmp_path, monkeypatch, login_env):
    monkeypatch.setattr(login, 'resolve_cli', lambda provider: None)
    assert login.executable_for('codex', {'reviewer': {'provider':'openai','executable':str(login_env)}}) == str(login_env)
    with pytest.raises(login.LoginError):
        login.executable_for('codex', {})


def test_http_auth_origin_and_payload_boundaries(http_server, monkeypatch):
    dispatch = Mock(return_value={'status':'opened','provider':'codex','message':'로그인 창을 열었습니다.'})
    monkeypatch.setattr(login, 'open_login', dispatch)
    headers = {'Content-Type':'application/json','X-Solomon-Bridge':'test-token'}
    body = json.dumps({'provider':'codex'})
    assert request(http_server, 'POST', '/ops/auth/login', body, {'Content-Type':'application/json'})[0] == 403
    for extra in ({'Origin':'https://evil.example'}, {'Origin':'null'}, {'Host':'evil.example'}):
        assert request(http_server, 'POST', '/ops/auth/login', body, dict(headers, **extra))[0] == 403
    for invalid in ('[]', '{broken', '{}', ' ' * 257, '{"provider":"codex","command":"anything"}', '{"provider":"codex","email":"private@example.com"}'):
        assert request(http_server, 'POST', '/ops/auth/login', invalid, headers)[0] == 400
    assert request(http_server, 'POST', '/ops/auth/login', body, {'X-Solomon-Bridge':'test-token'})[0] == 400
    dispatch.assert_not_called()
    code, data = request(http_server, 'POST', '/ops/auth/login', body, headers)
    assert code == 202 and json.loads(data)['status'] == 'opened'
    dispatch.assert_called_once()
    assert dispatch.call_args.args[0] == 'codex'


def test_http_dispatch_failure_does_not_claim_login_success(http_server, monkeypatch):
    monkeypatch.setattr(login, 'open_login', Mock(side_effect=login.LoginError('CLI 설치가 필요합니다.')))
    code, data = request(http_server, 'POST', '/ops/auth/login', '{"provider":"codex"}',
                         {'Content-Type':'application/json','X-Solomon-Bridge':'test-token'})
    assert code == 400 and 'error' in json.loads(data) and 'status' not in json.loads(data)
