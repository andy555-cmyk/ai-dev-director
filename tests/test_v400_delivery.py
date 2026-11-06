"""v4 delivery: plan -> 3 owner approvals -> release, with fake planner / builder / screen check (no real CLIs)."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import delivery, planning, vision_qa


def sample_plan(n_tasks=4):
    doc = '목적과 대상, 핵심 기능, 만들지 않는 것, 완료 조건을 적은 충분히 긴 문서입니다. ' * 2
    tasks = []
    for i in range(1, n_tasks + 1):
        tid = 'T%03d' % i
        paths = ['README.md'] if i == n_tasks else ['app/main.js', 'styles.css']
        tasks.append({'id': tid, 'title': '작업 %d' % i, 'detail': '내용', 'depends_on': ['T%03d' % (i - 1)] if i > 1 else [],
                      'allowed_paths': paths, 'required_outputs': paths[:1], 'acceptance': ['확인'], 'screens': ['S01']})
    return {'title': '조기축구 출석부', 'summary': '출석과 회비를 한 곳에서',
            'docs': {k: doc for k in planning.DOCS},
            'screens': [{'id': 'S01', 'name': '홈', 'route': '/', 'purpose': '요약'},
                        {'id': 'S02', 'name': '회원', 'route': '/members', 'purpose': '명단'}],
            'tasks': tasks, 'wireframes': {'S01': '<!doctype html><p>홈</p>', 'S02': '<!doctype html><p>회원</p>'}}


def test_validate_rejects_unsafe_paths_and_missing_readme():
    bad = sample_plan()
    bad['tasks'][0]['allowed_paths'] = ['../etc/passwd']
    bad['tasks'][0]['required_outputs'] = []
    with pytest.raises(planning.PlanError):
        planning.validate(bad)
    no_readme = sample_plan()
    no_readme['tasks'][-1]['allowed_paths'] = no_readme['tasks'][-1]['required_outputs'] = ['app/x.js']
    with pytest.raises(planning.PlanError, match='README'):
        planning.validate(no_readme)


def test_validate_rejects_cycles():
    p = sample_plan()
    p['tasks'][0]['depends_on'] = ['T004']
    with pytest.raises(planning.PlanError):
        planning.validate(p)


def test_create_plan_retries_once_then_writes_files(tmp_path):
    calls = []

    def runner(**kw):
        calls.append(kw)
        body = 'nope' if len(calls) == 1 else '```json\n' + json.dumps(sample_plan(), ensure_ascii=False) + '\n```'
        return SimpleNamespace(timed_out=False, exit_code=0, stdout=json.dumps({'result': body}))

    folder = tmp_path / 'plan' / 'v001'
    plan, man = planning.create_plan('조기축구 앱', folder, executable='/bin/echo', runner=runner)
    assert len(calls) == 2 and '이전 응답의 문제' in calls[1]['stdin_data']
    assert '--tools' in calls[0]['argv'] and '--strict-mcp-config' in calls[0]['argv']
    assert (folder / 'spec' / 'tasks.json').is_file() and (folder / 'wireframes' / 'S02.html').is_file()
    assert man['plan_hash'] == planning.manifest(folder)['plan_hash']


class Harness:
    def __init__(self, tmp_path, monkeypatch, judge_verdict='pass'):
        self.tmp = tmp_path
        monkeypatch.setattr(vision_qa, 'REJECTIONS', tmp_path / 'rejections.jsonl')
        monkeypatch.setattr(planning, 'render_wireframes', lambda folder, screens: {'ok': True, 'pages': []})
        self.verdict = judge_verdict
        self.builds = []
        self.runner = delivery.DeliveryRunner(lambda: None, store=delivery.DeliveryStore(tmp_path / 'deliveries'),
                                              planner=self.planner, measure=self.measure, judge=self.judge)
        self.runner._build = self.build

    def planner(self, goal, folder, taste='', feedback=None):
        plan = sample_plan()
        if feedback:
            plan['summary'] = '의견 반영: ' + feedback[-1]
        return plan, planning.write_plan(plan, Path(folder))

    def build(self, d, task, fix=None, base=None):
        self.builds.append((task['id'], bool(fix), d.get('pending_owner_fix')))
        wt = self.tmp / ('wt%d' % len(self.builds))
        shutil.copytree(planning.TEMPLATE, wt)
        (wt / 'README.md').write_text('# 앱\n', encoding='utf-8')
        return str(wt), ''

    def measure(self, url, out, paths=None, sizes='', wait_ms=0, seed=None):
        self.seeds = getattr(self, 'seeds', []) + [seed]
        Path(out).mkdir(parents=True, exist_ok=True)
        shot = Path(out) / 'home.png'
        shot.write_bytes(b'\x89PNG fake')
        return {'ok': True, 'pages': [{'path': p, 'size': '390x844', 'screenshot': str(shot), 'defects': []} for p in paths]}

    def judge(self, goal, report, workdir):
        return {'verdict': self.verdict, 'score': 90 if self.verdict != 'fail' else 10, 'problems': [], 'summary': 'ok',
                'screens': [p['screenshot'] for p in report['pages']]}


def test_full_delivery_stops_exactly_three_times(tmp_path, monkeypatch):
    h = Harness(tmp_path, monkeypatch)
    r = h.runner
    d = r.start(str(tmp_path / 'app'), '조기축구회 출석과 회비 관리 앱')
    assert (Path(d['project_path']) / 'index.html').is_file()     # empty folder got the web template
    d = r.run(d['delivery_id'])
    assert d['phase'] == 'WAIT_PLAN_APPROVAL' and len(d['tasks']) == 4
    with pytest.raises(ValueError):
        r.approve(d['delivery_id'], 'plan', plan_hash='wrong')
    with pytest.raises(ValueError):
        r.approve(d['delivery_id'], 'release')
    r.approve(d['delivery_id'], 'plan', plan_hash=d['plan_hash'])
    d = r.run(d['delivery_id'])
    assert d['phase'] == 'WAIT_SCREEN_APPROVAL'
    assert [t['status'] for t in d['tasks'].values()] == ['done', 'done', 'todo', 'todo']
    r.feedback(d['delivery_id'], '첫 화면 글자를 더 크게')
    assert (tmp_path / 'rejections.jsonl').is_file() and '더 크게' in vision_qa.taste_rules()
    d = r.run(d['delivery_id'])
    assert d['phase'] == 'WAIT_RELEASE_APPROVAL'
    assert h.builds[2][2] == '첫 화면 글자를 더 크게'           # owner note reached the next build
    assert Path(d['release']['zip']).is_file()
    d = r.approve(d['delivery_id'], 'release')
    assert d['phase'] == 'READY' and d['release']['exported']['copied']
    assert (Path(d['project_path']) / 'README.md').is_file()
    assert [a['what'] for a in d['approvals']] == ['plan', 'release']     # screen stage answered with a note


def test_plan_change_after_approval_fails_closed(tmp_path, monkeypatch):
    h = Harness(tmp_path, monkeypatch)
    r = h.runner
    d = r.run(r.start(str(tmp_path / 'app'), '조기축구회 출석 앱')['delivery_id'])
    r.approve(d['delivery_id'], 'plan', plan_hash=d['plan_hash'])
    (Path(d['plan_dir']) / 'spec' / 'prd.md').write_text('바뀜', encoding='utf-8')
    d = r.run(d['delivery_id'])
    assert d['phase'] == 'FAILED' and '기획 파일이 바뀌었' in d['reason']


def test_screen_fail_is_repaired_then_blocks(tmp_path, monkeypatch):
    h = Harness(tmp_path, monkeypatch, judge_verdict='fail')
    r = h.runner
    d = r.run(r.start(str(tmp_path / 'app'), '조기축구회 출석 앱')['delivery_id'])
    r.approve(d['delivery_id'], 'plan', plan_hash=d['plan_hash'])
    d = r.run(d['delivery_id'])
    assert d['phase'] == 'FAILED' and 'T001' in d['reason']
    assert [b[1] for b in h.builds] == [False, True, True]           # build + 2 visual repairs, then stop
    d = r.resume(d['delivery_id'])
    assert d['phase'] == 'BUILDING'


def test_plan_feedback_replans(tmp_path, monkeypatch):
    h = Harness(tmp_path, monkeypatch)
    r = h.runner
    d = r.run(r.start(str(tmp_path / 'app'), '조기축구회 출석 앱')['delivery_id'])
    r.feedback(d['delivery_id'], '회비 화면을 먼저')
    d = r.run(d['delivery_id'])
    assert d['phase'] == 'WAIT_PLAN_APPROVAL' and d['plan_version'] == 2 and '회비 화면을 먼저' in d['summary']


def test_store_rejects_bad_ids(tmp_path):
    store = delivery.DeliveryStore(tmp_path)
    for bad in ('../x', 'DLV-../../x', 'run-1'):
        with pytest.raises(ValueError):
            store.folder(bad)


def test_builder_references_are_markdown(tmp_path, monkeypatch):
    from core.builder_context import referenced_documents
    h = Harness(tmp_path, monkeypatch)
    r = h.runner
    d = r.run(r.start(str(tmp_path / 'app'), '조기축구회 출석 앱')['delivery_id'])
    order = delivery.DeliveryRunner._order(r, d, r._spec(d)['tasks'][0])
    docs = referenced_documents(order)
    assert len(docs) == 5 and any('T004' in v for v in docs.values())


def test_demo_data_fills_screens_and_reaches_builder(tmp_path, monkeypatch):
    h = Harness(tmp_path, monkeypatch)
    orig = h.planner

    def planner(goal, folder, taste='', feedback=None):
        plan = sample_plan()
        plan['demo_data'] = {'version': 1, 'members': [{'name': '가상 회원'}]}
        return plan, planning.write_plan(planning.validate(plan), Path(folder))
    h.runner.planner = planner
    r = h.runner
    d = r.run(r.start(str(tmp_path / 'app'), '조기축구회 출석 앱')['delivery_id'])
    assert (Path(d['plan_dir']) / 'spec' / 'demo_data.json').is_file()
    assert '가상 회원' in Path(r._tasks_md(d)).read_text(encoding='utf-8')
    r.approve(d['delivery_id'], 'plan', plan_hash=d['plan_hash'])
    r.run(d['delivery_id'])
    assert any(s and s.endswith('demo_data.json') for s in h.seeds) and None in h.seeds   # filled + empty


def test_demo_data_must_be_versioned():
    p = sample_plan()
    p['demo_data'] = {'members': []}
    with pytest.raises(planning.PlanError, match='demo_data'):
        planning.validate(p)
