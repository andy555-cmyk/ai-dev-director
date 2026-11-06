import json
from pathlib import Path
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import desktop_diagnostics as diag, grok_research as grok, usage
from tests.test_v301_companion_http import http_server, request


def result(text='분석 결과 https://example.com/source', **changes):
    values = dict(exit_code=0, timed_out=False, stdout=json.dumps({'text': text}), stderr='', duration_sec=1)
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.fixture
def service(tmp_path, monkeypatch):
    executable = tmp_path / 'official-grok-stub'
    executable.write_text('stub'); executable.chmod(0o755)
    monkeypatch.setattr(grok, 'resolve_cli', lambda name: str(executable))
    return grok.GrokResearch(tmp_path / 'engine')


def test_research_command_has_web_only_tools_and_no_prompt_in_argv():
    command = grok.research_command('/bin/grok', '/tmp/질문 파일.txt')
    assert command[command.index('--tools') + 1] == 'web_search,web_fetch'
    assert command[command.index('--sandbox') + 1] == 'read-only'
    assert command[command.index('--permission-mode') + 1] == 'dontAsk'
    assert '--no-subagents' in command and '--always-approve' not in command
    for tool in ('Bash', 'Edit', 'Write', 'Read', 'Grep', 'MCPTool'):
        assert any(command[i:i+2] == ['--deny', tool] for i in range(len(command)-1))


def test_analysis_result_persisted_duplicate_request_does_not_call_twice(service, monkeypatch):
    monkeypatch.setenv('XAI_API_KEY', 'private-test-key')
    monkeypatch.setenv('GROK_AUTH_PROVIDER_COMMAND', 'private-auth-command')
    def run(argv, **kwargs):
        question = Path(argv[argv.index('--prompt-file') + 1])
        assert question.read_text() == '분석할 공개 질문입니다'
        assert question.parent == Path(kwargs['cwd'])
        assert question.stat().st_mode & 0o777 == 0o600
        assert 'XAI_API_KEY' not in kwargs['env']
        assert 'GROK_AUTH_PROVIDER_COMMAND' not in kwargs['env']
        assert '분석할 공개 질문입니다' not in argv
        return result()
    runner = Mock(side_effect=run); monkeypatch.setattr(grok.ProcessTreeRunner, 'run', runner)
    request_id = 'request-00000001'
    assert service.start('분석할 공개 질문입니다', request_id)['status'] == 'accepted'
    service.thread.join(timeout=3)
    snapshot = service.snapshot()
    assert snapshot['job']['state'] == 'completed' and snapshot['job']['answer'].startswith('분석 결과')
    assert 'answer' not in snapshot['history'][0]
    service.start('분석할 공개 질문입니다', request_id)
    runner.assert_called_once()
    with pytest.raises(grok.ResearchError): service.start('다른 분석 질문입니다', request_id)
    restored = grok.GrokResearch(service.directory.parent.parent)
    assert restored.snapshot()['job']['answer'] == snapshot['job']['answer']
    assert 'private-test-key' not in json.dumps(snapshot)
    assert usage.provider_of('/Users/test/.grok/bin/grok') == 'GROK'


def test_concurrent_requests_block_and_cancel_targets_only_own_process(service, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def run(argv, **kwargs):
        entered.set(); release.wait(timeout=3)
        kwargs['on_heartbeat'](12345, 1)
        return result()
    monkeypatch.setattr(grok.ProcessTreeRunner, 'run', run)
    kill = Mock(); monkeypatch.setattr(grok.ProcessTreeRunner, 'kill_process_tree', kill)
    service.start('첫 번째 분석 질문입니다', 'request-11111111')
    assert entered.wait(timeout=1)
    with pytest.raises(grok.ResearchError) as exc: service.start('두 번째 분석 질문입니다', 'request-22222222')
    assert exc.value.code == 409
    service.cancel('request-11111111'); release.set(); service.thread.join(timeout=3)
    kill.assert_called_once_with(12345)
    assert service.snapshot()['job']['state'] == 'cancelled'
    assert service.snapshot()['job']['answer'] == ''


@pytest.mark.parametrize('changes', [
    {'exit_code':1,'stderr':'secret-token https://login.example/?code=private'},
    {'timed_out':True}, {'stdout':'not-json secret-token'}, {'stdout':'{}'},
    {'stdout':json.dumps({'text':'x'*48001})},
])
def test_failures_never_display_raw_auth_or_fake_success(changes):
    with pytest.raises(grok.ResearchError) as exc: grok.answer_from(result(**changes))
    assert 'secret-token' not in str(exc.value) and 'code=private' not in str(exc.value)


def test_failed_call_is_saved_as_failure(service, monkeypatch):
    monkeypatch.setattr(grok.ProcessTreeRunner, 'run', Mock(side_effect=OSError('private-token')))
    service.start('공개 자료를 조사해 주세요', 'request-failure')
    service.thread.join(timeout=3)
    job = service.snapshot()['job']
    assert job['state'] == 'failed' and job['finished_at'] and not job['answer']
    assert 'private-token' not in json.dumps(job)


@pytest.mark.parametrize('question,request_id', [('', 'valid-id-123'), ('짧음','valid-id-123'), ('x'*6001,'valid-id-123'),
                                                               ('정상적인 분석 질문','../escape'), (None,'valid-id-123')])
def test_invalid_input_never_launches(service, monkeypatch, question, request_id):
    runner = Mock(); monkeypatch.setattr(grok.ProcessTreeRunner, 'run', runner)
    with pytest.raises(grok.ResearchError): service.start(question,request_id)
    runner.assert_not_called()
    assert not service.directory.exists()


def test_interrupted_jobs_are_not_automatically_replayed(service):
    job = {'id':'request-interrupted','state':'running','question':'이전 분석 질문','answer':''}
    service._save(job)
    restored = grok.GrokResearch(service.directory.parent.parent)
    assert restored.snapshot()['job']['state'] == 'interrupted'
    assert restored.thread is None


def test_grok_diagnostic_does_not_guess_authentication(monkeypatch):
    probe = Mock(return_value=(0,'grok 1.0.46',False))
    monkeypatch.setattr(diag,'probe',probe)
    row = diag._cli('grok','/bin/grok')
    assert row['installed'] and row['version']=='1.0.46' and row['auth']=='manual_check'
    # 0.3.7: one extra non-generating `grok models` probe; output without a sign-in line is still not guessed.
    assert row['billing']=='unknown' and probe.call_count==2 and probe.call_args_list[1][0][0][1]=='models'


def test_http_grok_requires_local_authenticated_valid_request(http_server, monkeypatch):
    fake = SimpleNamespace(snapshot=Mock(return_value={'installed':True,'job':None}),
                           start=Mock(return_value={'status':'accepted'}),cancel=Mock(return_value={'status':'cancelling'}))
    monkeypatch.setattr(grok,'manager',lambda root:fake)
    headers = {'X-Solomon-Bridge':'test-token','Content-Type':'application/json'}
    body = json.dumps({'question':'새로운 분석 질문입니다','request_id':'request-http-test'})
    assert request(http_server,'GET','/ops/grok')[0]==403
    assert request(http_server,'POST','/ops/grok/research',body)[0]==403
    for extra in ({'Host':'evil.example'},{'Origin':'https://evil.example'},{'Origin':'null'}):
        assert request(http_server,'POST','/ops/grok/research',body,dict(headers,**extra))[0]==403
    for invalid in ('{}','[]','{broken',' '*40001,'{"question":"text","request_id":"request-http","command":"anything"}'):
        assert request(http_server,'POST','/ops/grok/research',invalid,headers)[0]==400
    fake.start.assert_not_called()
    assert request(http_server,'GET','/ops/grok',headers=headers)[0]==200
    assert request(http_server,'POST','/ops/grok/research',body,headers)[0]==202
    fake.start.assert_called_once_with('새로운 분석 질문입니다','request-http-test')
    assert request(http_server,'POST','/ops/grok/cancel','{"request_id":"request-http-test"}',headers)[0]==202
    assert request(http_server,'GET','/grok.js')[0]==200 and request(http_server,'GET','/grok.css')[0]==200
    code, html=request(http_server,'GET','/')
    assert code==200 and b'id="grok-card"' in html
