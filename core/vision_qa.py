"""v4 RUN&SEE: look at the running app the way a person would.

1. `measure()` runs scripts/qa/see.mjs (headless Chrome over CDP, no extra installs) and returns measured defects
   plus one PNG per page/size.
2. `judge()` attaches those screenshots to a read-only Codex CLI call and asks for a strict JSON verdict that
   combines the measured defects with what the model sees (layout, empty states, owner taste rules).
3. `screen_gate()` is fail-closed: no report, no screenshots, a crashed judge or unparseable JSON is NOT a pass.

Only subscription CLIs are used (API keys are stripped by get_sanitized_env); the app must be on localhost.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.env_utils import get_sanitized_env, resolve_cli
from core.process_runner import ProcessTreeRunner

ROOT = Path(__file__).resolve().parent.parent
SEE = ROOT / 'scripts' / 'qa' / 'see.mjs'
TASTE = ROOT / 'taste' / 'design_rules.md'
# Owner rejections live under data/ so app updates (which replace the engine folder) keep them.
REJECTIONS = ROOT / 'data' / 'taste_rejections.jsonl'
BLOCKING = {'blank_page', 'leaked_value', 'navigation_error', 'console_error', 'overlap', 'horizontal_scroll', 'broken_image',
            'off_screen', 'audit_failed', 'screenshot_failed'}
VERDICT_KEYS = {'verdict', 'score', 'problems', 'summary'}


def measure(url: str, out_dir: str, paths: Optional[List[str]] = None, sizes: str = '1440x900,390x844',
            wait_ms: int = 2000, min_font: int = 13, timeout: float = 180.0, seed: Optional[str] = None) -> Dict[str, Any]:
    node = shutil.which('node')
    if not node:
        return {'ok': False, 'error': 'Node.js가 없어 화면 검사를 못 합니다.'}
    argv = [node, str(SEE), '--url', url, '--out', str(out_dir), '--sizes', sizes,
            '--wait', str(int(wait_ms)), '--min-font', str(int(min_font))]
    if paths:
        argv += ['--paths', ','.join(paths)]
    if seed:
        argv += ['--seed', str(seed)]
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'ok': False, 'error': '화면 검사 시간 초과'}
    line = (res.stdout or '').strip().splitlines()[-1:] or ['']
    try:
        report = json.loads(line[0])
    except ValueError:
        return {'ok': False, 'error': '화면 검사 결과를 읽지 못했습니다.', 'stderr': (res.stderr or '')[-400:]}
    return report


def taste_rules() -> str:
    try:
        text = TASTE.read_text(encoding='utf-8')[:6000]
    except OSError:
        text = ''
    try:
        rows = [json.loads(l) for l in REJECTIONS.read_text(encoding='utf-8').splitlines()[-10:] if l.strip()]
    except (OSError, ValueError):
        rows = []
    if rows:
        text += '\n\n## 대표가 최근 반려한 것(같은 실수 금지)\n' + '\n'.join('- ' + str(r.get('comment', ''))[:200] for r in rows)
    return text


def _summary(report: Dict[str, Any]) -> str:
    rows = []
    for page in report.get('pages', []):
        kinds = ', '.join('%s×%d' % (d['kind'], d['count']) for d in page.get('defects', [])) or '측정 결함 없음'
        rows.append('- %s @ %s: %s' % (page.get('path'), page.get('size'), kinds))
        for d in page.get('defects', [])[:4]:
            rows.append('    %s: %s' % (d['kind'], json.dumps(d.get('items', [])[:3], ensure_ascii=False)[:300]))
    return '\n'.join(rows)


def judge_prompt(goal: str, report: Dict[str, Any], screens: List[str]) -> str:
    return (
        '너는 출시 전 화면 검수자다. 첨부 이미지는 실제 실행한 앱 화면 캡처다(순서대로: '
        + ', '.join(Path(s).name for s in screens) + ').\n'
        '파일을 고치거나 명령을 실행하지 마라. 판정만 한다.\n\n'
        'ROADMAP/GOAL:\n' + goal[:3000] + '\n\n'
        '측정 도구가 찾은 결함(DOM 측정, 사실):\n' + _summary(report) + '\n\n'
        '대표 취향 규칙(어기면 문제로 적어라):\n' + (taste_rules() or '(없음)') + '\n\n'
        '완료 조건 중 화면으로 볼 수 없는 것(문서·명령·테스트 결과)은 판정 대상이 아니다(다른 단계가 확인함).\n'
        '검수 범위: 「이번 작업」이 있으면 그 작업의 완료 조건만 본다. 뒤 작업에서 만들 기능·내용이 아직 없는 것은 '
        '문제가 아니다(적지 마라). 「최종 검수」면 앱 전체를 목표에 비춰 본다.\n'
        '판정 기준: 화면이 깨짐·겹침·잘림·빈 화면·읽기 힘든 작은 글자·이번 범위와 다른 화면이면 fail. '
        '사소한 미감 문제만 있으면 pass_with_notes. 첨부 이미지가 안 보이거나 비어 있으면 fail.\n'
        '첨부한 화면만 판정한다. 첨부하지 않은 화면·클릭 동작·저장 기능의 증거가 없다는 이유로 fail 하지 마라'
        '(이동·콘솔 오류는 측정 도구가 따로 확인했고, 기능은 자동 테스트가 확인했다).\n'
        '캡처는 첫 화면 높이만 찍는다. 화면 아래·위에 고정된 메뉴 밑으로 내용이 이어지는 것은 스크롤하면 보이므로 문제가 아니다'
        '(끝까지 내려도 가려지는지는 측정 도구가 확인한다. 측정 결함에 overlap이 없으면 가림 문제로 적지 마라).\n'
        '반드시 마지막에 아래 JSON 하나만 ```json 블록으로 출력:\n'
        '{"verdict":"pass|pass_with_notes|fail","score":0-100,'
        '"problems":[{"screen":"파일명","severity":"high|medium|low","what":"무엇이 문제","fix":"어떻게 고칠지"}],'
        '"summary":"한 문장"}\n'
    )


def parse_verdict(text: str) -> Optional[Dict[str, Any]]:
    blocks = re.findall(r'```json\s*(\{.*?\})\s*```', text or '', re.S) or re.findall(r'(\{[^{}]*"verdict".*\})', text or '', re.S)
    for raw in reversed(blocks):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if isinstance(data, dict) and VERDICT_KEYS <= set(data) and data['verdict'] in ('pass', 'pass_with_notes', 'fail'):
            return data
    return None


def judge(goal: str, report: Dict[str, Any], workdir: str, executable: Optional[str] = None,
          timeout: float = 600.0, max_images: int = 6) -> Dict[str, Any]:
    screens = [p['screenshot'] for p in report.get('pages', []) if p.get('screenshot') and Path(p['screenshot']).exists()]
    screens = screens[:max_images]
    if not screens:
        return {'verdict': 'fail', 'score': 0, 'problems': [], 'summary': '캡처가 없어 판정할 수 없습니다.', 'judge': 'none'}
    exe = executable or resolve_cli('codex')
    if not exe:
        return {'verdict': 'fail', 'score': 0, 'problems': [], 'summary': 'Codex CLI가 없어 화면 판정을 못 했습니다.', 'judge': 'none'}
    argv = [exe, 'exec', '--sandbox', 'read-only', '--skip-git-repo-check', '-C', str(workdir)]
    for shot in screens:
        argv += ['-i', shot]
    argv.append('-')    # prompt on stdin: `-i` takes several values and would swallow a positional prompt
    res = ProcessTreeRunner.run(argv=argv, cwd=str(workdir), env=get_sanitized_env(), timeout=timeout,
                                no_output_timeout=timeout, heartbeat_interval=30,
                                stdin_data=judge_prompt(goal, report, screens), usage_provider='OPENAI')
    verdict = parse_verdict((res.stdout or '') + '\n' + (res.stderr or '')[-4000:]) if not res.timed_out else None
    if not verdict:
        return {'verdict': 'fail', 'score': 0, 'problems': [], 'judge': 'codex',
                'summary': '화면 판정 응답이 없거나 형식이 깨졌습니다(fail-closed).'}
    verdict['judge'] = 'codex'
    verdict['screens'] = screens
    return verdict


def screen_gate(report: Dict[str, Any], verdict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine measurement and model verdict. Any blocking measured defect or a model fail blocks the step."""
    if not report or not report.get('ok'):
        return {'passed': False, 'reason': (report or {}).get('error') or '화면 검사 결과 없음'}
    blocking = sorted({d['kind'] for p in report.get('pages', []) for d in p.get('defects', []) if d['kind'] in BLOCKING})
    small = sum(d['count'] for p in report.get('pages', []) for d in p.get('defects', []) if d['kind'] == 'small_text')
    reasons = ['측정 결함: ' + ', '.join(blocking)] if blocking else []
    if small:
        reasons.append('작은 글자 %d곳' % small)
    if not verdict or verdict.get('verdict') == 'fail':
        reasons.append('화면 판정 fail' + (': ' + verdict.get('summary', '') if verdict else ''))
    return {'passed': not blocking and not small and bool(verdict) and verdict.get('verdict') in ('pass', 'pass_with_notes'),
            'reasons': reasons, 'verdict': verdict}
