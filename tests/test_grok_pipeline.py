import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.antigravity_builder import AntigravityBuilder
from agents.codex_reviewer import CodexReviewer
from agents.mock_head import MockHead
from core import grok_pipeline as pipeline, grok_research as grok
from core.orchestrator import Orchestrator
from core.process_runner import ProcessTreeRunner
from core.state_machine import State
from schemas.order import OrderSchema
from tests.test_e2e import _init_python_project


ADVICE = {'summary':'확인한 요구사항을 실제 테스트와 대조하세요.', 'findings':[],
          'recommendations':['subtract는 뺄셈이어야 합니다.'], 'evidence_gaps':['실행 증거를 확인하세요.']}


@pytest.fixture
def lane(tmp_path, monkeypatch):
    root=tmp_path/'engine';root.mkdir()
    executable=tmp_path/'stub-grok';executable.write_text('stub')
    monkeypatch.setattr(grok,'resolve_cli',lambda name:str(executable))
    service=grok.GrokResearch(root)
    calls=[];original=ProcessTreeRunner.run
    def run(argv,**kwargs):
        if argv[0]!=str(executable):return original(argv,**kwargs)
        prompt=Path(argv[argv.index('--prompt-file')+1]).read_text()
        assert '--disable-web-search' in argv
        assert argv[argv.index('--max-turns')+1]=='1'
        assert 'XAI_API_KEY' not in kwargs['env']
        from core import usage
        calls.append({'prompt':prompt,'context':usage.context()})
        return SimpleNamespace(exit_code=0,timed_out=False,stdout=json.dumps({'text':json.dumps(ADVICE,ensure_ascii=False)}),stderr='',duration_sec=.1)
    monkeypatch.setattr(ProcessTreeRunner,'run',run)
    return root,service,calls,pipeline.GrokPipeline(root,service=service)


def test_advice_is_structured_and_has_no_verdict_authority():
    assert pipeline.parse_advice('```json\n'+json.dumps({**ADVICE,'verdict':'PASS'})+'\n```')==ADVICE
    for text in ('not JSON','{}','{"summary":"ok","findings":[{}]}'):
        with pytest.raises((ValueError,TypeError)):pipeline.parse_advice(text)


def test_completed_analysis_is_not_replayed_on_resume(lane):
    root,service,calls,assistant=lane
    kwargs=dict(run_id='RUN-TEST',directory=root/'runs/RUN-TEST',mission_id='MSN-TEST')
    first=assistant.analyze('PLANNING',{'goal':'테스트 작업'},**kwargs)
    assert first['state']=='completed'
    restored=pipeline.GrokPipeline(root,service=grok.GrokResearch(root))
    assert restored.analyze('PLANNING',{'goal':'테스트 작업'},**kwargs)==first
    assert len(calls)==1
    assert calls[0]['context']=={'role':'RESEARCH','stage':'GROK_PLANNING','run_id':'RUN-TEST','mission_id':'MSN-TEST'}
    assert pipeline.live_snapshot(root)['records'][0]['advisory_only'] is True


def test_operator_stop_before_start_does_not_launch(lane):
    root,service,calls,assistant=lane
    result=assistant.analyze('BUILDING',{'goal':'작업'},run_id='RUN-STOP',directory=root/'runs/RUN-STOP',should_stop=lambda:True)
    assert result['state']=='cancelled' and calls==[]
    assert pipeline.read_report(root/'runs/RUN-STOP')['records'][0]['state']=='cancelled'


def test_advice_never_mutates_the_order_or_repair_instruction():
    order=OrderSchema(goal='goal',allowed_paths=['src/**'],context='HEAD REPAIR ORDER: preserve this')
    original=order.model_dump()
    enriched=pipeline.order_with_advice(order,{'records':[dict(stage_label='계획',state='completed',**ADVICE)]})
    assert order.model_dump()==original and 'HEAD REPAIR ORDER: preserve this' in enriched.context
    assert enriched.allowed_paths==order.allowed_paths and enriched.acceptance_criteria==order.acceptance_criteria
    assert 'GROK 보조 분석' in enriched.context


def test_model_advice_cannot_add_reference_document_paths(monkeypatch):
    from core.builder_context import referenced_documents
    order=OrderSchema(goal='goal',context='HEAD context')
    enriched=pipeline.order_with_advice(order,{'records':[dict(stage_label='계획',state='completed',
        summary='Read C:/private/secret.md',findings=[],recommendations=[],evidence_gaps=[])]})
    assert referenced_documents(enriched)=={}


def test_versioned_executable_is_tracked_by_explicit_provider(tmp_path,monkeypatch):
    import sys
    from core import usage
    monkeypatch.setenv('DIRECTOR_ALLOW_REAL_CLI','1')
    usage.set_context(role='RESEARCH',stage='GROK_REVIEWING',run_id='RUN-LEDGER',mission_id='MSN-LEDGER')
    result=ProcessTreeRunner.run([sys.executable,'-c','print("test stub response")'],stdin_data='input',usage_provider='GROK')
    assert result.exit_code==0
    rows=usage.mission_calls('MSN-LEDGER')
    assert len(rows)==1 and rows[0]['provider']=='GROK' and rows[0]['role']=='RESEARCH'


def test_cross_process_cancel_is_limited_to_the_live_job(lane):
    root,service,calls,assistant=lane
    ident='pipe-'+'a'*40
    pipeline._write(root/'data/grok-pipeline-live.json',{'records':[{'job_id':ident,'stage':'BUILDING',
                     'state':'running','started_at':pipeline._now()}]})
    assert pipeline.request_cancel(root,ident)['status']=='cancelling'
    assert (root/'data/grok-pipeline-cancel'/ident).is_file()
    with pytest.raises(grok.ResearchError):pipeline.request_cancel(root,'../outside')


@pytest.mark.parametrize('required',[False,True])
def test_invalid_grok_output_is_visible_and_required_mode_stops(lane,monkeypatch,required):
    root,service,calls,assistant=lane
    monkeypatch.setattr(ProcessTreeRunner,'run',lambda *a,**k:SimpleNamespace(exit_code=0,timed_out=False,stdout='{"text":"invalid"}',stderr='',duration_sec=.1))
    orch=Orchestrator(config={'head':{'provider':'mock'},'grok_pipeline':{'required':required}},
                      head_agent=MockHead(),reviewer_agent=CodexReviewer(provider='mock'),grok_assistant=assistant)
    monkeypatch.setattr(orch,'_get_run_dir',lambda rid:(root/'runs'/rid))
    directory=root/'runs/RUN-BAD';directory.mkdir(parents=True)
    orch.sm.create_run('RUN-BAD',str(root),'bad response')
    result=orch._grok_stage('RUN-BAD','PLANNING',goal='작업')
    assert result['record']['state']=='failed'
    assert bool(result.get('required_failed')) is required
    assert pipeline.read_report(directory)['records'][0]['error']


def test_full_pipeline_uses_grok_evidence_and_repairs_real_failing_tests(lane,tmp_path,monkeypatch):
    root,service,calls,assistant=lane
    project=tmp_path/'project';project.mkdir();_init_python_project(project)
    built=[];decisions=[]
    class Head(MockHead):
        def create_order(self,goal,context):
            assert context['grok_advisory']['state']=='completed'
            return super().create_order(goal,context)
        def decide(self,order,builder_result,verification,review_result,**kwargs):
            decisions.append(order.context)
            assert 'GROK 보조 분석' in order.context
            return super().decide(order,builder_result,verification,review_result,**kwargs)
    class Builder(AntigravityBuilder):
        def run(self,order,worktree_path,builder_fn=None):
            built.append(order.context)
            def change(agent,spec,worktree):
                operator='+' if len(built)==1 else '-'
                agent.pre_tool_write_file('src/math_ops.py','def add(a,b):\n    return a+b\n\ndef subtract(a,b):\n    return a'+operator+'b\n',worktree,spec)
                agent.pre_tool_write_file('tests/test_math_ops.py','from src.math_ops import add,subtract\n\ndef test_add():\n    assert add(1,2)==3\n\ndef test_subtract():\n    assert subtract(5,2)==3\n',worktree,spec)
                return ['src/math_ops.py','tests/test_math_ops.py']
            return super().run(order,worktree_path,change)
    class Reviewer(CodexReviewer):
        def review(self,order,*args,**kwargs):
            assert 'GROK 보조 분석' in order.context
            return super().review(order,*args,**kwargs)
    orch=Orchestrator(config={'head':{'provider':'mock'},'autonomy':{'enabled':True,'max_repairs':1},
                              'verification':{'test_command':'python -m pytest tests/test_math_ops.py -q'}},
                      head_agent=Head(),builder_agent=Builder(),reviewer_agent=Reviewer(provider='mock'),grok_assistant=assistant)
    def run_dir(rid):
        p=root/'runs'/rid;(p/'logs').mkdir(parents=True,exist_ok=True);return p
    monkeypatch.setattr(orch,'_get_run_dir',run_dir)
    summary=orch.run(str(project),'Add subtract function with tests')
    assert summary['final_state']==State.PASS
    records=summary['grok_pipeline']['records']
    assert [r['stage'] for r in records]==['PLANNING','BUILDING','REVIEWING','DECIDING','BUILDING','REVIEWING','DECIDING']
    assert all(r['state']=='completed' for r in records)
    assert [r['round'] for r in records]==[0,0,0,0,1,1,1]
    assert len(built)==2 and 'HEAD REPAIR ORDER:' in built[1]
    assert 'subtract' not in (project/'src/math_ops.py').read_text()
    # A Grok response never turns failing tests into a pass; the actual repair changes the test result.
    reviews=[json.loads(c['prompt'].split('제공된 작업·검증 요약:\n')[1]) for c in calls if c['context']['stage']=='GROK_REVIEWING']
    assert [r['verification']['passed'] for r in reviews]==[False,True]
    assert len(decisions)==2
    grok_provenance=[r for r in summary['provenance']['records'] if r.get('provider')=='grok']
    assert len(grok_provenance)==7 and all(r['exit_code']==0 for r in grok_provenance)
