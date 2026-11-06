"""v4 PLAN: one line -> product plan the owner approves before any code is built.

Output (plan/v001/): spec/prd.md, spec/screens.md, spec/data.md, spec/design.md, spec/tasks.json, wireframes/<id>.html,
wireframes/*.png (rendered by the screen check), plan_manifest.json (sha256 of every file = the approval target).

The planning CLI runs with no tools, no MCP servers and no user settings/hooks: it only returns text.
"""
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.env_utils import get_sanitized_env, resolve_cli
from core.process_runner import ProcessTreeRunner

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'templates' / 'web_static'
DOCS = ('prd', 'screens', 'data', 'design')
TASK_ID = re.compile(r'^T\d{3}$')
SCREEN_ID = re.compile(r'^S\d{2}$')
MAX_TASKS = 40


class PlanError(ValueError):
    pass


def claude_text_argv(executable: str) -> List[str]:
    """Claude Code in print mode with every tool, MCP server and user setting (hooks, CLAUDE.md) switched off."""
    return [executable, '--print', '--output-format', 'json', '--tools', '', '--strict-mcp-config',
            '--mcp-config', '{"mcpServers":{}}', '--setting-sources', '', '--no-session-persistence',
            '--disable-slash-commands']


def template_listing() -> str:
    rows = []
    for p in sorted(TEMPLATE.rglob('*')):
        if p.is_file():
            rows.append('- ' + str(p.relative_to(TEMPLATE)))
    return '\n'.join(rows)


def plan_prompt(goal: str, taste: str, feedback: Optional[List[str]] = None) -> str:
    fb = ''
    if feedback:
        fb = '\n대표가 이전 기획에 남긴 의견(반드시 반영):\n' + '\n'.join('- ' + f for f in feedback[-10:]) + '\n'
    return (
        '너는 제품 기획자다. 대표가 한 줄로 말한 앱을 정적 웹앱으로 기획한다. 도구 없이 글로만 답한다.\n\n'
        '대표의 한 줄: ' + goal.strip()[:2000] + '\n' + fb + '\n'
        '기술 조건(바꾸지 마라):\n'
        '- 빌드 도구·패키지 없음. index.html + styles.css + app/*.js(ES 모듈) + tests/*.test.mjs(node:test)\n'
        '- 데이터는 브라우저 localStorage(app/store.js가 이미 있음: load/save/exportJson/importJson/memoryStorage). '
        '서버·로그인·결제·외부 API 없음. JSON 백업 내보내기/가져오기 제공\n'
        '- 화면 이동은 해시 주소(#/members 등). app/main.js의 ROUTES에 화면을 등록한다\n'
        '- 계산·저장 로직은 DOM 없는 순수 함수 모듈로 분리해 node:test로 시험한다\n'
        '이미 있는 뼈대 파일:\n' + template_listing() + '\n\n'
        '대표 취향 규칙(기획·디자인 방향에 반영):\n' + (taste[:5000] or '(없음)') + '\n\n'
        '작업(tasks) 규칙:\n'
        '- 6~14개. 하나는 15분 안팎, 바꾸는 파일 3~5개. id는 T001부터\n'
        '- 첫 작업은 모든 화면의 빈 틀과 이동 메뉴(실행 가능한 화면을 먼저)\n'
        '- 각 작업: allowed_paths(바꿀 파일 정확히), required_outputs(반드시 생기는 파일), acceptance(검사 가능한 문장), '
        'screens(이 작업 뒤 확인할 화면 id), depends_on\n'
        '- 마지막 작업은 README.md(실행 방법·기능 설명·백업 방법)\n'
        '- 저장 데이터는 store.js의 KEY(app-data-v1)에 data 문서 구조 그대로 둔다. 화면 검수는 demo_data를 그 자리에 넣고 채워진 화면을 본다\n'
        '- 화면 문구 끝에 마침표 금지, 최소 13px 글자, 휴대전화 390px 폭에서도 쓰기 좋게\n\n'
        '와이어프레임: 화면마다 하나의 완결된 HTML(인라인 CSS만, 스크립트·외부 파일 없음). 실제 한국어 문구와 '
        '예시 데이터(가상 이름)로 배치를 보여준다. 회색 상자만 있는 그림 금지. 1440px와 390px 모두 깨지지 않게\n\n'
        '출력: 아래 JSON 하나만 ```json 블록으로. 다른 말 금지.\n'
        '{"title":"앱 이름","summary":"한 문장",'
        '"docs":{"prd":"마크다운: 목적·대상·핵심 기능·만들지 않는 것·완료 조건",'
        '"screens":"마크다운: 화면별 목적·요소·상태(빈 목록·오류·완료)",'
        '"data":"마크다운: 저장 구조(JSON 예시)·계산 규칙",'
        '"design":"마크다운: 색·글자 크기·배치 원칙·금지 사항"},'
        '"screens":[{"id":"S01","name":"홈","route":"/","purpose":"..."}],'
        '"tasks":[{"id":"T001","title":"...","detail":"구현할 내용","depends_on":[],'
        '"allowed_paths":["app/main.js"],"required_outputs":["app/main.js"],"acceptance":["..."],"screens":["S01"]}],'
        '"wireframes":{"S01":"<!doctype html>..."},'
        '"demo_data":{"version":1,"...":"data 문서의 저장 구조 그대로, 모든 화면이 채워 보일 만큼의 예시(가상 이름)"}}\n'
    )


def extract_json(text: str) -> Dict[str, Any]:
    blocks = re.findall(r'```json\s*(\{.*\})\s*```', text or '', re.S)
    candidates = blocks + ([text.strip()] if (text or '').strip().startswith('{') else [])
    for raw in reversed(candidates):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    raise PlanError('기획 응답에서 JSON을 찾지 못했습니다')


def _safe_rel(path: str) -> bool:
    p = Path(path)
    return bool(path) and not p.is_absolute() and '..' not in p.parts and not path.startswith(('.', '/')) \
        and not any(part.startswith('.') for part in p.parts)


def validate(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Fail-closed structural checks. Returns the normalised plan or raises PlanError."""
    problems = []
    docs = plan.get('docs') or {}
    for key in DOCS:
        if not isinstance(docs.get(key), str) or len(docs[key].strip()) < 40:
            problems.append('문서 누락 또는 너무 짧음: ' + key)
    screens = plan.get('screens') or []
    screen_ids = [s.get('id') for s in screens if isinstance(s, dict)]
    if not 1 <= len(screens) <= 12 or len(set(screen_ids)) != len(screen_ids) or not all(SCREEN_ID.match(str(i)) for i in screen_ids):
        problems.append('화면 목록이 비었거나 id가 잘못됨(S01 형식, 중복 금지)')
    for s in screens:
        if not str(s.get('route', '')).startswith('/'):
            problems.append('화면 주소는 /로 시작해야 함: ' + str(s.get('id')))
    tasks = plan.get('tasks') or []
    ids = [t.get('id') for t in tasks if isinstance(t, dict)]
    if not 1 <= len(tasks) <= MAX_TASKS or len(set(ids)) != len(ids) or not all(TASK_ID.match(str(i)) for i in ids):
        problems.append('작업 목록이 비었거나 id가 잘못됨(T001 형식, 중복 금지, 최대 %d개)' % MAX_TASKS)
    known = set(ids)
    for t in tasks:
        tid = t.get('id')
        for key in ('title', 'detail'):
            if not str(t.get(key, '')).strip():
                problems.append('%s: %s 없음' % (tid, key))
        paths = list(t.get('allowed_paths') or [])
        if not paths or not all(_safe_rel(p) for p in paths):
            problems.append('%s: allowed_paths가 비었거나 안전하지 않은 경로' % tid)
        if not set(t.get('required_outputs') or []) <= set(paths):
            problems.append('%s: required_outputs는 allowed_paths 안에 있어야 함' % tid)
        if not t.get('acceptance'):
            problems.append('%s: acceptance 없음' % tid)
        if not set(t.get('depends_on') or []) <= known - {tid}:
            problems.append('%s: 없는 작업에 의존' % tid)
        if not set(t.get('screens') or []) <= set(screen_ids):
            problems.append('%s: 없는 화면 참조' % tid)
    if not problems:
        order_ids = topo_order(tasks)            # raises on a cycle
        if order_ids[-1:] and 'README.md' not in sum((list(t.get('allowed_paths') or []) for t in tasks), []):
            problems.append('README.md를 쓰는 작업이 없음')
    demo = plan.get('demo_data')
    if demo is not None and (not isinstance(demo, dict) or demo.get('version') != 1 or len(json.dumps(demo)) > 200_000):
        problems.append('demo_data는 version 1인 저장 데이터 객체여야 함(200KB 이하)')
    wf = plan.get('wireframes') or {}
    for sid in screen_ids:
        if not isinstance(wf.get(sid), str) or '<' not in wf.get(sid, ''):
            problems.append('와이어프레임 누락: ' + str(sid))
    if problems:
        raise PlanError('; '.join(problems[:12]))
    return plan


def topo_order(tasks: List[Dict[str, Any]]) -> List[str]:
    deps = {t['id']: set(t.get('depends_on') or []) for t in tasks}
    order, done = [], set()
    pending = [t['id'] for t in tasks]
    while pending:
        ready = [i for i in pending if deps[i] <= done]
        if not ready:
            raise PlanError('작업 의존 관계에 순환이 있음: ' + ', '.join(pending))
        for i in ready:
            order.append(i)
            done.add(i)
        pending = [i for i in pending if i not in done]
    return order


def write_plan(plan: Dict[str, Any], folder: Path) -> Dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    spec = folder / 'spec'
    spec.mkdir(exist_ok=True)
    for key in DOCS:
        (spec / (key + '.md')).write_text(plan['docs'][key].strip() + '\n', encoding='utf-8')
    tasks = [{**t, 'order': i} for i, t in enumerate(sorted(plan['tasks'], key=lambda t: topo_order(plan['tasks']).index(t['id'])))]
    (spec / 'tasks.json').write_text(json.dumps({'schema_version': 1, 'title': plan.get('title', ''),
                                                 'summary': plan.get('summary', ''), 'screens': plan['screens'],
                                                 'tasks': tasks}, ensure_ascii=False, indent=2), encoding='utf-8')
    if isinstance(plan.get('demo_data'), dict):
        (spec / 'demo_data.json').write_text(json.dumps(plan['demo_data'], ensure_ascii=False, indent=2), encoding='utf-8')
    wf = folder / 'wireframes'
    wf.mkdir(exist_ok=True)
    for s in plan['screens']:
        (wf / (s['id'] + '.html')).write_text(plan['wireframes'][s['id']], encoding='utf-8')
    return manifest(folder)


def manifest(folder: Path) -> Dict[str, Any]:
    files = {}
    for p in sorted(folder.rglob('*')):
        if p.is_file() and p.name != 'plan_manifest.json' and 'shots' not in p.relative_to(folder).parts:
            files[str(p.relative_to(folder))] = hashlib.sha256(p.read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    data = {'files': files, 'plan_hash': digest}
    (folder / 'plan_manifest.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    return data


def render_wireframes(folder: Path, screens: List[Dict[str, Any]]) -> Dict[str, Any]:
    """PNG of every wireframe at desktop and phone width (owner looks at pictures, not HTML)."""
    from core.static_serve import serve
    from core.vision_qa import measure
    with serve(folder / 'wireframes') as url:
        return measure(url, str(folder / 'wireframes' / 'shots'), paths=['/' + s['id'] + '.html' for s in screens],
                       sizes='1440x900,390x844', wait_ms=800)


def create_plan(goal: str, folder: Path, taste: str = '', feedback: Optional[List[str]] = None,
                executable: Optional[str] = None, timeout: float = 900.0, runner=None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Ask the planner once, retry once with the validation error. Returns (plan, manifest)."""
    exe = executable or resolve_cli('claude')
    if not exe:
        raise PlanError('Claude CLI가 없어 기획을 만들 수 없습니다')
    run = runner or ProcessTreeRunner.run
    folder.mkdir(parents=True, exist_ok=True)
    prompt = plan_prompt(goal, taste, feedback)
    last_error = ''
    for attempt in range(2):
        text_in = prompt if not last_error else prompt + '\n\n이전 응답의 문제(고쳐서 다시 전체 JSON 출력): ' + last_error
        res = run(argv=claude_text_argv(exe), cwd=str(folder.parent), env=get_sanitized_env(), timeout=timeout,
                  no_output_timeout=timeout, heartbeat_interval=30, stdin_data=text_in, usage_provider='ANTHROPIC')
        if res.timed_out or res.exit_code != 0:
            last_error = 'CLI 실패(exit %s)' % res.exit_code
            continue
        try:
            envelope = json.loads(res.stdout)
            body = envelope.get('result', '') if isinstance(envelope, dict) else ''
            if isinstance(envelope, dict) and envelope.get('is_error'):
                raise PlanError('CLI 오류 응답: ' + str(body)[:200])
            plan = validate(extract_json(body))
        except (ValueError, PlanError) as exc:
            last_error = str(exc)[:1500]
            continue
        man = write_plan(plan, folder)
        return plan, man
    raise PlanError('기획 생성 실패: ' + last_error)
