"""Desktop additions: actual failure cases, privacy boundary and upgrade preservation."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from core import desktop_diagnostics as diag
from core.result_manager import evidence_gate


@pytest.fixture
def diagnostic_env(monkeypatch):
    monkeypatch.setattr(diag, 'resolve_cli', lambda name: '/bin/' + name)
    monkeypatch.setattr(diag.shutil, 'which', lambda name: '/bin/' + name)
    monkeypatch.setattr(diag.importlib.metadata, 'version', lambda name: '1.0')
    monkeypatch.setattr(diag, '_CACHE', None)
    cfg = {'head': {'provider': 'claude'}, 'builder': {'provider': 'codex'},
           'reviewer': {'provider': 'claude'}}
    return cfg


def fake_probe(argv):
    if '--version' in argv:
        return 0, 'version 2.1.3', False
    if argv[-2:] == ['auth', 'status']:
        return 0, json.dumps({'loggedIn': True, 'authMethod': 'claude.ai',
                             'email': 'private@example.com', 'token': 'secret-token'}), False
    return 0, 'Logged in using ChatGPT', False


def test_report_uses_auth_and_excludes_private_output(monkeypatch, diagnostic_env):
    monkeypatch.setattr(diag, 'probe', fake_probe)
    report = diag.refresh(diagnostic_env)
    assert report['status'] == 'ready'
    assert report['confirmed_subscription_count'] == 2
    assert any('독립성' in w for w in report['warnings'])
    output = json.dumps(report)
    for value in ('private@example.com', 'secret-token', '/bin/claude'):
        assert value not in output
    assert diag.cached() == report


@pytest.mark.parametrize('case,expected', [('api', 'blocked'), ('timeout', 'needs_check'), ('malformed', 'needs_check')])
def test_unknown_or_api_auth_is_never_ready(monkeypatch, diagnostic_env, case, expected):
    def probe(argv):
        if argv[-2:] == ['auth', 'status']:
            if case == 'api':
                return 0, '{"loggedIn":true,"authMethod":"api_key"}', False
            if case == 'timeout':
                return None, 'secret-token', True
            return 0, '{broken secret-token', False
        return fake_probe(argv)
    monkeypatch.setattr(diag, 'probe', probe)
    report = diag.collect(diagnostic_env)
    assert report['status'] == expected
    assert 'secret-token' not in json.dumps(report)


def test_missing_cli_blocks_but_agy_auth_remains_manual(monkeypatch, diagnostic_env):
    monkeypatch.setattr(diag, 'probe', fake_probe)
    monkeypatch.setattr(diag, 'resolve_cli', lambda name: None if name == 'codex' else '/bin/' + name)
    report = diag.collect(diagnostic_env)
    assert report['status'] == 'needs_check'
    assert next(p for p in report['providers'] if p['name'] == 'agy')['auth'] == 'manual_check'
    monkeypatch.setattr(diag, 'resolve_cli', lambda name: '/bin/claude' if name == 'claude' else None)
    assert diag.collect(diagnostic_env)['status'] == 'blocked'


def test_probe_has_hard_timeout_and_does_not_use_ai_ledger(monkeypatch):
    runner = Mock(return_value=SimpleNamespace(exit_code=0, stdout='2.1.0', stderr='', timed_out=False))
    monkeypatch.setattr(diag.ProcessTreeRunner, '_run_process', runner)
    monkeypatch.setenv('OPENAI_API_KEY', 'not-for-cli')
    assert diag.probe(['/bin/codex', '--version'])[0] == 0
    assert runner.call_args.kwargs['timeout'] == 4
    assert 'OPENAI_API_KEY' not in runner.call_args.kwargs['env']


def test_incomplete_or_failed_evidence_cannot_display_pass():
    evidence = {'canonical_containment': 'PASS', 'verification': 'PASS', 'baseline': 'PASS',
                'regression': 'PASS', 'reviewer_verdict': 'pass', 'reasons': []}
    assert evidence_gate(evidence) == 'PASS'
    for key in ('canonical_containment', 'verification', 'baseline', 'regression', 'reviewer_verdict'):
        incomplete = dict(evidence); del incomplete[key]
        assert evidence_gate(incomplete) == 'MISSING'
        failed = dict(evidence); failed[key] = 'FAIL'
        assert evidence_gate(failed) == 'FAIL'
    assert evidence_gate({'reasons': []}) == 'MISSING'
    assert evidence_gate({}) == 'MISSING'
    assert evidence_gate(dict(evidence, reasons=['blocked'])) == 'FAIL'


def installer():
    spec = importlib.util.spec_from_file_location('install_support', Path(__file__).parents[1] / 'packaging/macos/install_support.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def prepare_upgrade(tmp_path):
    state, source = tmp_path / 'state', tmp_path / 'source'
    old = state / 'engine';old.mkdir(parents=True); source.mkdir()
    (old / 'config.yaml').write_text('user: keep')
    (old / 'companion.json').write_text('{"port":8081}')
    (old / 'obsolete.py').write_text('old')
    (old / 'data').mkdir();(old / 'data/private.db').write_text('user-data')
    (source / 'config.yaml').write_text('default: replace')
    (source / 'new.py').write_text('new')
    return state, source


def test_upgrade_preserves_settings_data_and_old_code(tmp_path):
    state, source = prepare_upgrade(tmp_path)
    engine = installer().install_engine(source, state, '0.2.0')
    assert (engine / 'config.yaml').read_text() == 'user: keep'
    assert (engine / 'data/private.db').read_text() == 'user-data'
    assert (engine / 'data').is_symlink()
    assert not (engine / 'obsolete.py').exists()
    backups = list((state / 'backups').glob('engine-*'))
    assert len(backups) == 1 and (backups[0] / 'obsolete.py').exists()
    assert (backups[0] / 'config.yaml').read_text() == 'user: keep'
    installer().install_engine(source, state, '0.2.0')
    assert len(list((state / 'backups').iterdir())) == 1


def test_failed_staging_keeps_old_engine(tmp_path, monkeypatch):
    state, source = prepare_upgrade(tmp_path)
    module = installer()
    monkeypatch.setattr(module.shutil, 'copytree', Mock(side_effect=OSError('disk full')))
    with pytest.raises(OSError):module.install_engine(source, state, '0.2.0')
    assert (state / 'engine/obsolete.py').exists()
    assert (state / 'engine/data/private.db').read_text() == 'user-data'
    assert not list(state.glob('.engine-staging-*'))


def test_interrupted_install_recovers_backup(tmp_path):
    state, source = prepare_upgrade(tmp_path)
    backup = state / 'backups/engine-previous';backup.parent.mkdir();(state / 'engine').rename(backup)
    engine = installer().install_engine(source, state, '0.2.0')
    assert (engine / 'config.yaml').read_text() == 'user: keep'
    assert (engine / 'data/private.db').read_text() == 'user-data'

from tests.test_v301_companion_http import http_server, request


def test_diagnostics_http_requires_token_and_local_origin(http_server, monkeypatch):
    fake = {'version': '0.2.0', 'status': 'needs_check'}
    monkeypatch.setattr(diag, 'refresh', lambda config: fake)
    monkeypatch.setattr(diag, 'cached', lambda: fake)
    assert request(http_server, 'GET', '/ops/diagnostics')[0] == 403
    assert request(http_server, 'POST', '/ops/diagnostics', body='')[0] == 403
    headers = {'X-Solomon-Bridge': 'test-token', 'Origin': 'https://evil.example'}
    assert request(http_server, 'POST', '/ops/diagnostics', body='', headers=headers)[0] == 403
    headers.pop('Origin')
    code, body = request(http_server, 'POST', '/ops/diagnostics', body='', headers=headers)
    assert code == 200 and json.loads(body)['report'] == fake
    assert request(http_server, 'POST', '/ops/diagnostics', body='{}', headers=headers)[0] == 400
    code, body = request(http_server, 'GET', '/ops/diagnostics', headers=headers)
    assert code == 200 and 'csrf' not in json.loads(body)
    assert request(http_server, 'GET', '/setup')[0] == 200
    assert request(http_server, 'GET', '/setup.js')[0] == 200
    code, body = request(http_server, 'GET', '/health')
    assert code == 200 and json.loads(body)['product'] == 'ai-dev-director-macos'


def test_malformed_role_settings_rejected():
    with pytest.raises(ValueError):diag.collect({'head': 'not-a-mapping'})


def test_same_version_new_build_replaces_engine(tmp_path):
    source, state = tmp_path / 'src', tmp_path / 'state'
    source.mkdir()
    (source / 'a.txt').write_text('old')
    (source / '.source-build-id').write_text('b1')
    engine = installer().install_engine(source, state, '0.4.0')
    assert (engine / 'a.txt').read_text() == 'old'
    (source / 'a.txt').write_text('new')
    installer().install_engine(source, state, '0.4.0')              # same build id: kept
    assert (engine / 'a.txt').read_text() == 'old'
    (source / '.source-build-id').write_text('b2')
    engine = installer().install_engine(source, state, '0.4.0')      # new build of the same version: replaced
    assert (engine / 'a.txt').read_text() == 'new'
