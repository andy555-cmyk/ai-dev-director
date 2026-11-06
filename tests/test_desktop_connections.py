from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from core import desktop_connections as connections, desktop_diagnostics as diag, usage
from tests.test_v301_companion_http import http_server, request

NOW = datetime(2026, 11, 6, 8, tzinfo=timezone.utc)


def report(auth='logged_in', **fields):
    return {'checked_at': NOW.isoformat(), 'providers': [dict(name='grok', installed=True,
            responding=True, auth=auth, **fields)]}


def row(value, evidence=None, now=NOW):
    return connections.connection_rows(value, evidence, now)[3]


@pytest.mark.parametrize('auth,installed,responding,state,reason', [
    ('logged_in', True, True, 'connected', '구독 계정'),
    ('missing', False, False, 'disconnected', '설치'),
    ('logged_in', True, False, 'disconnected', '실행 확인'),
    ('not_logged_in', True, True, 'disconnected', '로그인'),
    ('api_billing', True, True, 'disconnected', 'API 인증'),
    ('manual_check', True, True, 'unknown', '확인이 필요'),
    ('timeout', True, True, 'unknown', '초과'),
    ('unknown', True, True, 'unknown', '확인하지 못'),
])
def test_connection_state_and_visible_reason(auth, installed, responding, state, reason):
    data=report(auth);data['providers'][0].update(installed=installed, responding=responding)
    result=row(data)
    assert result['state']==state and reason in result['reason']
    assert result['label']=={'connected':'연결됨','disconnected':'연결 안됨','unknown':'확인 필요'}[state]


def test_installation_or_old_success_is_not_a_connection():
    success={'grok':{'success':True,'checked_at':(NOW-timedelta(minutes=11)).isoformat()}}
    assert row(report('manual_check'),success)['state']=='unknown'
    assert row(report(), now=NOW+timedelta(minutes=11))['state']=='unknown'
    assert row(None)['state']=='unknown'


def test_fresh_response_is_evidence_for_manual_providers_and_expires():
    success={'grok':{'success':True,'checked_at':NOW.isoformat()}}
    result=row(report('manual_check'),success)
    assert result['state']=='connected' and result['verified_by']=='response'
    assert row(report('not_logged_in'),success)['state']=='disconnected'
    assert row(None,success)['state']=='connected'
    assert row(report(),now=NOW-timedelta(minutes=1))['state']=='unknown'  # Future report invalid.


def test_newer_failure_invalidates_old_confirmation_without_claiming_logout():
    evidence={'grok':{'failed':True,'checked_at':(NOW+timedelta(seconds=30)).isoformat()}}
    result=row(report(),evidence,now=NOW+timedelta(seconds=40))
    assert result['state']=='unknown' and '실행에 실패' in result['reason']


def test_only_latest_live_finished_call_is_used_and_no_output_is_returned():
    usage.set_context(role='BUILDER', stage='BUILDING')
    ident=usage.call_started(['agy'],'private prompt')
    usage.call_finished(ident,['agy'],'private prompt',SimpleNamespace(exit_code=0,stdout='private answer',stderr='',duration_sec=1,timed_out=False))
    evidence=connections._recent_calls()
    assert evidence['agy']['success'] is True
    assert 'private' not in json.dumps(evidence)
    ident=usage.call_started(['agy'],'second private prompt')
    usage.call_failed(ident,Exception('private error'))
    assert connections._recent_calls()['agy']['failed'] is True


def test_diagnostics_connections_are_authenticated_and_contain_only_safe_evidence(http_server,monkeypatch):
    monkeypatch.setattr(diag,'cached',lambda:report('manual_check'))
    monkeypatch.setattr(connections,'_recent_calls',lambda:{})
    from core import grok_research
    monkeypatch.setattr(grok_research,'manager',lambda root:SimpleNamespace(snapshot=lambda:{'job':{
        'state':'completed','answer':'private answer','question':'private question','finished_at':NOW.isoformat()}}))
    assert request(http_server,'GET','/ops/diagnostics')[0]==403
    code,body=request(http_server,'GET','/ops/diagnostics',headers={'X-Solomon-Bridge':'test-token'})
    data=json.loads(body)
    assert code==200 and len(data['connections']['providers'])==4
    assert 'private' not in body.decode()
    assert 'csrf' not in data
