"""v4 DeliveryRunner: one line -> approved plan -> task-by-task build with real screen checks -> release bundle.

The existing Orchestrator still builds every task (isolated worktree, Scope Guard, tests, independent review).
This module only decides WHAT to build next, LOOKS at the result, and stops for the owner exactly three times:
plan approval, mid-way screen approval, release approval. Nothing here weakens the Orchestrator's own gates.

State lives in data/deliveries/<id>/delivery.json (atomic writes); a restart continues from the saved phase.
"""
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core import planning, vision_qa
from core.bootstrap import prepare_project

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / 'data' / 'deliveries'
WAITING = {'WAIT_PLAN_APPROVAL', 'WAIT_SCREEN_APPROVAL', 'WAIT_RELEASE_APPROVAL'}
TERMINAL = {'READY', 'STOPPED', 'FAILED'}
ACTIVE = {'PLANNING', 'BUILDING', 'PACKAGING'}
APPROVALS = {'plan': 'WAIT_PLAN_APPROVAL', 'screen': 'WAIT_SCREEN_APPROVAL', 'release': 'WAIT_RELEASE_APPROVAL'}
DEFAULT_BUDGET = {'minutes': 240, 'build_repairs': 2, 'visual_repairs': 2, 'cli_calls': 160}
_LOCKS: Dict[str, threading.Lock] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DeliveryStore:
    def __init__(self, base: Optional[Path] = None):
        self.base = Path(base or BASE)

    def folder(self, delivery_id: str) -> Path:
        if not delivery_id.startswith('DLV-') or '/' in delivery_id or '..' in delivery_id:
            raise ValueError('잘못된 납품 id')
        return self.base / delivery_id

    def load(self, delivery_id: str) -> Optional[Dict[str, Any]]:
        try:
            return json.loads((self.folder(delivery_id) / 'delivery.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def save(self, d: Dict[str, Any]) -> None:
        folder = self.folder(d['delivery_id'])
        folder.mkdir(parents=True, exist_ok=True)
        d['updated_at'] = _now()
        tmp = folder / ('delivery.json.%d.tmp' % os.getpid())
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, folder / 'delivery.json')

    def event(self, d: Dict[str, Any], kind: str, text: str, **extra) -> None:
        row = {'at': _now(), 'kind': kind, 'text': text, **extra}
        with (self.folder(d['delivery_id']) / 'events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    def events(self, delivery_id: str, limit: int = 40) -> List[Dict[str, Any]]:
        try:
            lines = (self.folder(delivery_id) / 'events.jsonl').read_text(encoding='utf-8').splitlines()
        except OSError:
            return []
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
        return out

    def all(self) -> List[Dict[str, Any]]:
        rows = []
        if self.base.is_dir():
            for p in self.base.iterdir():
                d = self.load(p.name) if p.name.startswith('DLV-') else None
                if d:
                    rows.append(d)
        return sorted(rows, key=lambda d: d.get('created_at', ''), reverse=True)


def init_project_from_template(project: str) -> str:
    """Empty folder -> git repo with the zero-dependency web template committed. Existing work is never touched."""
    root = Path(prepare_project(project))
    visible = [p for p in root.iterdir() if p.name not in ('.git', '.DS_Store', '.director_worktrees')]
    if visible:
        return str(root)
    shutil.copytree(planning.TEMPLATE, root, dirs_exist_ok=True)
    (root / '.gitignore').write_text('.director_worktrees/\nnode_modules/\n.DS_Store\n', encoding='utf-8')
    env = dict(os.environ, GIT_AUTHOR_NAME='AI DEV', GIT_AUTHOR_EMAIL='ai-dev@localhost',
               GIT_COMMITTER_NAME='AI DEV', GIT_COMMITTER_EMAIL='ai-dev@localhost')
    subprocess.run(['git', 'add', '-A'], cwd=root, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-qm', 'AI DEV v4 web template'], cwd=root, check=True, capture_output=True, env=env)
    return str(root)


def web_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Static web apps verify with node:test (no installs). The Director's config, never the project's."""
    cfg = json.loads(json.dumps(config))
    cfg.setdefault('verification', {})['test_command'] = ['node', '--test', '--test-reporter=tap']
    cfg['verification']['build_command'] = None
    safety = cfg.setdefault('safety', {})
    safety['approved_commands'] = sorted(set(safety.get('approved_commands') or []) | {'node'})
    return cfg


class DeliveryRunner:
    def __init__(self, orchestrator_factory: Callable[[], Any], store: Optional[DeliveryStore] = None,
                 notify: Optional[Callable[[str], None]] = None, planner=planning.create_plan,
                 measure=vision_qa.measure, judge=vision_qa.judge):
        self.factory = orchestrator_factory
        self.store = store or DeliveryStore()
        self.notify = notify or (lambda text: None)
        self.planner, self.measure, self.judge = planner, measure, judge

    # ------------------------------------------------------------------ lifecycle
    def start(self, project: str, goal: str, budget: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        goal = (goal or '').strip()
        if not 5 <= len(goal) <= 2000:
            raise ValueError('만들 앱을 5~2000자로 적어 주세요')
        project = init_project_from_template(project)
        d = {'delivery_id': 'DLV-' + datetime.now().strftime('%y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:6].upper(),
             'project_path': project, 'goal': goal, 'phase': 'PLANNING', 'created_at': _now(), 'started_ts': time.time(),
             'budget': {**DEFAULT_BUDGET, **(budget or {})}, 'plan_version': 0, 'plan_hash': None, 'approvals': [],
             'feedback': [], 'tasks': {}, 'last_accepted': None, 'screen_checkpoint_after': None,
             'stop_requested': False, 'reason': None, 'release': None, 'title': '', 'summary': ''}
        self.store.save(d)
        self.store.event(d, 'start', '새 앱 만들기: ' + goal[:200])
        return d

    def approve(self, delivery_id: str, what: str, plan_hash: Optional[str] = None, by: str = '대표') -> Dict[str, Any]:
        d = self._need(delivery_id)
        if APPROVALS.get(what) != d['phase']:
            raise ValueError('지금은 %s 승인 단계가 아닙니다(현재 %s)' % (what, d['phase']))
        if what == 'plan':
            if not plan_hash or plan_hash != d['plan_hash'] or plan_hash != self._plan_hash_now(d):
                raise ValueError('승인하려는 기획이 현재 기획과 다릅니다. 화면을 새로 고친 뒤 다시 승인하세요')
            d['phase'] = 'BUILDING'
        elif what == 'screen':
            d['phase'] = 'BUILDING'
        else:
            rel = d.get('release') or {}
            if not rel.get('zip') or _sha(Path(rel['zip'])) != rel.get('sha256'):
                raise ValueError('출시 묶음이 바뀌었습니다. 다시 묶은 뒤 승인하세요')
            d['phase'] = 'READY'
            d['release']['exported'] = self._export(d)
        d['approvals'].append({'what': what, 'by': by, 'at': _now(), 'plan_hash': d.get('plan_hash')})
        self.store.save(d)
        self.store.event(d, 'approve', {'plan': '기획 승인', 'screen': '중간 화면 승인', 'release': '출시 승인'}[what])
        return d

    def feedback(self, delivery_id: str, text: str) -> Dict[str, Any]:
        """Owner says what is wrong. Plan stage -> re-plan. Screen stage -> next work gets the note; the taste log
        keeps it for later judgements."""
        text = (text or '').strip()[:1000]
        if not text:
            raise ValueError('의견을 적어 주세요')
        d = self._need(delivery_id)
        d['feedback'].append({'at': _now(), 'phase': d['phase'], 'text': text})
        _taste_log(d, text)
        if d['phase'] == 'WAIT_PLAN_APPROVAL':
            d['phase'] = 'PLANNING'
        elif d['phase'] == 'WAIT_SCREEN_APPROVAL':
            d['pending_owner_fix'] = text
            d['phase'] = 'BUILDING'
        self.store.save(d)
        self.store.event(d, 'feedback', '대표 의견: ' + text[:200])
        return d

    def stop(self, delivery_id: str) -> Dict[str, Any]:
        d = self._need(delivery_id)
        d['stop_requested'] = True
        if d['phase'] not in TERMINAL:
            d['phase'], d['reason'] = 'STOPPED', '대표가 멈춤'
        self.store.save(d)
        self.store.event(d, 'stop', '멈춤')
        return d

    def resume(self, delivery_id: str) -> Dict[str, Any]:
        d = self._need(delivery_id)
        if d['phase'] in ('STOPPED', 'FAILED'):
            d['phase'] = d.get('resume_phase') or ('BUILDING' if d.get('plan_hash') and any(
                a['what'] == 'plan' for a in d['approvals']) else 'PLANNING')
            d['stop_requested'], d['reason'] = False, None
            self.store.save(d)
            self.store.event(d, 'resume', '이어서 진행')
        return d

    def run(self, delivery_id: str) -> Dict[str, Any]:
        """Advance until the delivery waits for the owner or ends. Safe to call again after a crash."""
        lock = _LOCKS.setdefault(delivery_id, threading.Lock())
        if not lock.acquire(blocking=False):
            return self._need(delivery_id)
        try:
            while True:
                d = self._need(delivery_id)
                if d.get('stop_requested') or d['phase'] in WAITING | TERMINAL:
                    return d
                if (time.time() - d.get('started_ts', time.time())) / 60 > d['budget']['minutes']:
                    return self._end(d, 'FAILED', '시간 예산(%d분)을 다 썼습니다' % d['budget']['minutes'])
                step = {'PLANNING': self._plan, 'BUILDING': self._build_next, 'PACKAGING': self._package}[d['phase']]
                try:
                    step(d)
                except Exception as exc:     # fail-closed, keep the state for a resume
                    d = self._need(delivery_id)
                    d['resume_phase'] = d['phase']
                    self._end(d, 'FAILED', '%s 중 오류: %s' % (d['phase'], str(exc)[:400]))
                    return self._need(delivery_id)
        finally:
            lock.release()

    # ------------------------------------------------------------------ PLAN
    def _plan(self, d):
        d['plan_version'] += 1
        folder = self.store.folder(d['delivery_id']) / 'plan' / ('v%03d' % d['plan_version'])
        self.store.event(d, 'plan', '기획서를 쓰는 중(%d번째)' % d['plan_version'])
        self.notify('[기획] %s' % d['goal'][:100])
        plan, man = self.planner(d['goal'], folder, taste=vision_qa.taste_rules(),
                                 feedback=[f['text'] for f in d['feedback']])
        shots = {}
        try:
            report = planning.render_wireframes(folder, plan['screens'])
            for page in report.get('pages', []):
                shots.setdefault(page['path'].strip('/').replace('.html', ''), []).append(page['screenshot'])
        except Exception as exc:
            self.store.event(d, 'warn', '와이어프레임 캡처 실패: %s' % str(exc)[:200])
        d.update(plan_dir=str(folder), plan_hash=man['plan_hash'], title=plan.get('title', ''),
                 summary=plan.get('summary', ''), wireframe_shots=shots, phase='WAIT_PLAN_APPROVAL',
                 tasks={t['id']: {'status': 'todo', 'title': t['title'], 'attempts': [], 'screens': t.get('screens', [])}
                        for t in plan['tasks']})
        mid = max(1, len(plan['tasks']) // 2)
        d['screen_checkpoint_after'] = planning.topo_order(plan['tasks'])[mid - 1]
        self.store.save(d)
        self.store.event(d, 'wait', '기획 승인을 기다립니다: %s · 화면 %d개 · 작업 %d개' % (
            d['title'], len(plan['screens']), len(plan['tasks'])))

    def _plan_hash_now(self, d) -> Optional[str]:
        try:
            return planning.manifest(Path(d['plan_dir']))['plan_hash']
        except (KeyError, OSError):
            return None

    def _spec(self, d) -> Dict[str, Any]:
        return json.loads((Path(d['plan_dir']) / 'spec' / 'tasks.json').read_text(encoding='utf-8'))

    # ------------------------------------------------------------------ BUILD -> RUN&SEE -> FIX
    def _build_next(self, d):
        if self._plan_hash_now(d) != d['plan_hash']:
            return self._end(d, 'FAILED', '승인한 뒤 기획 파일이 바뀌었습니다')
        spec = self._spec(d)
        tasks = {t['id']: t for t in spec['tasks']}
        todo = [tid for tid in planning.topo_order(spec['tasks']) if d['tasks'][tid]['status'] != 'done']
        if not todo:
            d['phase'] = 'PACKAGING'
            self.store.save(d)
            return
        tid = todo[0]
        task, state = tasks[tid], d['tasks'][tid]
        state['status'] = 'building'
        self.store.save(d)
        self.notify('[작업 %s] %s' % (tid, task['title']))
        self.store.event(d, 'task', '%s 시작: %s' % (tid, task['title']), task=tid)
        candidate, why = self._build(d, task, fix=None)
        visual_tries = 0
        while candidate:
            gate = self._see(d, task, candidate, tid, final=False)
            if gate['passed']:
                break
            if visual_tries >= d['budget']['visual_repairs']:
                candidate, why = None, '화면 검수를 %d번 고쳐도 통과 못 함: %s' % (visual_tries, '; '.join(gate['reasons'])[:300])
                break
            visual_tries += 1
            self.store.event(d, 'fix', '%s 화면 고치기 %d: %s' % (tid, visual_tries, '; '.join(gate['reasons'])[:300]), task=tid)
            fixed, why = self._build(d, task, fix=gate, base=candidate)
            candidate = fixed
        d = self._need(d['delivery_id'])
        state = d['tasks'][tid]
        if not candidate:
            state['status'] = 'blocked'
            d['resume_phase'] = 'BUILDING'
            return self._end(d, 'FAILED', '%s 막힘: %s' % (tid, why))
        state['status'] = 'done'
        d['last_accepted'] = candidate
        d.pop('pending_owner_fix', None)
        self.store.save(d)
        self.store.event(d, 'done', '%s 완료' % tid, task=tid)
        if tid == d.get('screen_checkpoint_after') and not any(a['what'] == 'screen' for a in d['approvals']):
            d['phase'] = 'WAIT_SCREEN_APPROVAL'
            self.store.save(d)
            self.store.event(d, 'wait', '중간 화면 확인을 기다립니다')

    def _order(self, d, task, fix=None):
        from schemas.order import OrderSchema
        plan_dir = Path(d['plan_dir'])
        refs = [str(plan_dir / 'spec' / (k + '.md')) for k in planning.DOCS] + [str(plan_dir / 'spec' / 'tasks.json')]
        owner = d.get('pending_owner_fix')
        context = ('정적 웹앱(빌드 도구 없음). 기획 문서는 reference_paths에 있다. 화면 주소는 해시(#/...).\n'
                   '대표 취향 규칙:\n' + vision_qa.taste_rules()[:3500])
        if owner:
            context += '\n\n대표가 중간 확인에서 남긴 의견(반드시 반영): ' + owner
        if fix:
            v = fix.get('verdict') or {}
            problems = '\n'.join('- [%s] %s → %s' % (p.get('screen', ''), p.get('what', ''), p.get('fix', ''))
                                 for p in (v.get('problems') or [])[:12])
            goal = ('%s 화면 결함 고치기. 측정·판정 결과:\n%s\n%s' % (task['id'], '; '.join(fix['reasons']), problems))[:3000]
            paths = sorted(set(task['allowed_paths']) | {'styles.css', 'index.html'})
            return OrderSchema(goal=goal, allowed_paths=paths, required_outputs=[], reference_paths=refs,
                               acceptance_criteria=['측정 결함(겹침·잘림·작은 글자·콘솔 오류) 0', '기존 테스트 통과'],
                               context=context, max_files_changed=6, max_diff_lines=600)
        goal = '%s %s\n%s' % (task['id'], task['title'], task.get('detail', ''))
        return OrderSchema(goal=goal[:3000], allowed_paths=list(task['allowed_paths']),
                           required_outputs=list(task.get('required_outputs') or []), reference_paths=refs,
                           acceptance_criteria=list(task.get('acceptance') or []) + ['node --test 통과'],
                           context=context, max_files_changed=max(5, len(task['allowed_paths'])), max_diff_lines=800)

    def _build(self, d, task, fix=None, base=None):
        """One task (or one fix) through the existing Orchestrator, with build retries. Returns (worktree, why)."""
        from core import autopilot
        from core.mission import MissionRunner
        from core.state_machine import State
        base = base or d.get('last_accepted')
        why = ''
        for attempt in range(d['budget']['build_repairs'] + 1):
            if self._need(d['delivery_id']).get('stop_requested'):
                return None, '멈춤'
            orch = self.factory()
            order = self._order(d, task, fix)
            if why and not fix:
                order.context = (order.context or '') + '\n\n직전 시도가 실패한 이유(고쳐서 다시): ' + why[:1500]
            gate = autopilot.entry_gate(order, d['project_path'], orch.head, cwd=base or d['project_path'])
            if gate['escalate']:
                return None, '사람 확인 필요: ' + gate['escalate'][:300]
            rid = orch.reserve_run_id(d['project_path'], gate['order'].goal)
            self._record_attempt(d, task['id'], {'run_id': rid, 'kind': 'fix' if fix else 'build', 'at': _now()})
            try:
                orch.run(d['project_path'], gate['order'].goal, run_id=rid, order=gate['order'], base_worktree=base)
            except Exception as exc:
                why = 'Orchestrator 오류: %s' % str(exc)[:300]
                continue
            ev = MissionRunner._evidence(orch, rid)
            self._record_attempt(d, task['id'], {'run_id': rid, 'final_state': ev.get('final_state'),
                                                 'worktree': ev.get('worktree_path'), 'tests': ev.get('tests')}, update=True)
            if ev.get('final_state') == State.PASS and ev.get('worktree_path'):
                return ev['worktree_path'], ''
            why = '%s: %s' % (ev.get('final_state'), (ev.get('stop_detail') or ev.get('summary') or '')[:600])
            self.store.event(d, 'retry', '%s 다시 시도(%d): %s' % (task['id'], attempt + 1, why[:200]), task=task['id'])
        return None, why

    def _record_attempt(self, d, tid, row, update=False):
        fresh = self._need(d['delivery_id'])
        attempts = fresh['tasks'][tid]['attempts']
        if update and attempts and attempts[-1].get('run_id') == row.get('run_id'):
            attempts[-1].update(row)
        else:
            attempts.append(row)
        self.store.save(fresh)
        d['tasks'] = fresh['tasks']

    def _routes(self, d, screen_ids=None) -> List[str]:
        spec = self._spec(d)
        routes = ['/#' + s['route'] for s in spec['screens'] if not screen_ids or s['id'] in screen_ids]
        return routes or ['/#/']

    def _see(self, d, task, worktree, tag, final=False) -> Dict[str, Any]:
        from core.static_serve import serve
        out = self.store.folder(d['delivery_id']) / 'evidence' / tag / datetime.now().strftime('%H%M%S')
        sizes = '1440x900,1280x800,390x844' if final else '1440x900,390x844'
        routes = self._routes(d, None if final else (task or {}).get('screens'))
        with serve(worktree) as url:
            report = self.measure(url, str(out), paths=routes, sizes=sizes, wait_ms=1500)
        verdict = None
        if report.get('ok'):
            goal = '%s\n이번 작업: %s' % (d['goal'], (task or {}).get('title', '최종 검수'))
            verdicts = []
            pages = report.get('pages', [])
            for i in range(0, len(pages), 4):        # every screenshot is judged, four at a time
                part = dict(report, pages=pages[i:i + 4])
                verdicts.append(self.judge(goal, part, str(out)))
            verdict = _merge_verdicts(verdicts)
        gate = vision_qa.screen_gate(report, verdict)
        (out / 'gate.json').write_text(json.dumps({'report': report, 'gate': gate}, ensure_ascii=False, indent=2), encoding='utf-8')
        fresh = self._need(d['delivery_id'])
        shots = [p['screenshot'] for p in report.get('pages', []) if p.get('screenshot')]
        if task:
            fresh['tasks'][task['id']].update(screens_checked=len(shots), last_shots=shots[:6],
                                              screen_passed=gate['passed'], screen_reasons=gate['reasons'][:6])
        fresh['latest_shots'] = shots[:8] or fresh.get('latest_shots')
        self.store.save(fresh)
        d.update(fresh)
        self.store.event(d, 'see', '%s 화면 검수 %s · %d장%s' % (tag, '통과' if gate['passed'] else '불합격', len(shots),
                                                          '' if gate['passed'] else ' · ' + '; '.join(gate['reasons'])[:200]),
                         task=(task or {}).get('id'), shots=shots[:6])
        return gate

    # ------------------------------------------------------------------ PACKAGE
    def _package(self, d):
        wt = d.get('last_accepted')
        if not wt or not Path(wt).is_dir():
            return self._end(d, 'FAILED', '완성된 작업본이 없습니다')
        gate = self._see(d, None, wt, 'final', final=True)
        if not gate['passed']:
            tries = d.get('final_fix_tries', 0)
            if tries >= d['budget']['visual_repairs']:
                return self._end(d, 'FAILED', '최종 화면 검수 불합격: ' + '; '.join(gate['reasons'])[:400])
            spec = self._spec(d)
            pseudo = {'id': 'FINAL', 'title': '최종 화면 다듬기', 'allowed_paths': sorted({p for t in spec['tasks'] for p in t['allowed_paths']}),
                      'screens': [s['id'] for s in spec['screens']]}
            d['final_fix_tries'] = tries + 1
            self.store.save(d)
            fixed, why = self._build(d, pseudo, fix=gate, base=wt)
            d = self._need(d['delivery_id'])
            if not fixed:
                return self._end(d, 'FAILED', '최종 화면 고치기 실패: ' + why[:300])
            d['last_accepted'] = fixed
            self.store.save(d)
            return
        if not (Path(wt) / 'README.md').is_file():
            return self._end(d, 'FAILED', 'README.md가 없습니다')
        rel = self.store.folder(d['delivery_id']) / 'release'
        rel.mkdir(parents=True, exist_ok=True)
        zpath = rel / 'app.zip'
        files = _app_files(Path(wt))
        sums = {}
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in files:
                rp = str(f.relative_to(wt))
                z.write(f, rp)
                sums[rp] = _sha(f)
        (rel / 'checksums.json').write_text(json.dumps(sums, indent=2), encoding='utf-8')
        d['release'] = {'zip': str(zpath), 'sha256': _sha(zpath), 'files': len(files), 'worktree': wt, 'at': _now(),
                        'screens_checked': len(gate.get('verdict', {}).get('screens') or []) if gate.get('verdict') else 0}
        d['phase'] = 'WAIT_RELEASE_APPROVAL'
        self.store.save(d)
        self.store.event(d, 'wait', '출시 묶음 준비 완료(%d개 파일). 출시 승인을 기다립니다' % len(files))

    def _export(self, d) -> Dict[str, Any]:
        """After release approval: copy the app into the project folder only if the owner did not change it."""
        project = Path(d['project_path'])
        dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=project,
                               capture_output=True, text=True).stdout.strip()
        if dirty:
            return {'copied': False, 'why': '프로젝트 폴더에 직접 고친 파일이 있어 덮어쓰지 않았습니다. release/app.zip을 쓰세요'}
        wt = Path(d['release']['worktree'])
        n = 0
        for f in _app_files(wt):
            target = project / f.relative_to(wt)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            n += 1
        return {'copied': True, 'files': n, 'to': str(project)}

    # ------------------------------------------------------------------ helpers
    def _end(self, d, phase, reason):
        d['phase'], d['reason'] = phase, reason
        self.store.save(d)
        self.store.event(d, 'end', '%s: %s' % (phase, reason))
        self.notify('[납품] %s: %s' % (phase, reason))
        return d

    def _need(self, delivery_id) -> Dict[str, Any]:
        d = self.store.load(delivery_id)
        if not d:
            raise ValueError('납품 기록이 없습니다: ' + delivery_id)
        return d


def _app_files(root: Path) -> List[Path]:
    skip = {'.git', '.director_worktrees', 'node_modules', '__pycache__', '.DS_Store'}
    return sorted(p for p in root.rglob('*') if p.is_file() and not any(part in skip for part in p.relative_to(root).parts))


def _merge_verdicts(vs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not vs:
        return None
    order = {'fail': 0, 'pass_with_notes': 1, 'pass': 2}
    worst = min(vs, key=lambda v: order.get(v.get('verdict'), 0))
    return {'verdict': worst.get('verdict', 'fail'), 'score': min(int(v.get('score') or 0) for v in vs),
            'problems': sum((list(v.get('problems') or []) for v in vs), [])[:20],
            'summary': ' / '.join(v.get('summary', '') for v in vs)[:600],
            'screens': sum((list(v.get('screens') or []) for v in vs), [])}


def _taste_log(d, text):
    path = vision_qa.REJECTIONS
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'at': _now(), 'delivery_id': d['delivery_id'], 'phase': d['phase'],
                                'goal': d['goal'][:200], 'comment': text}, ensure_ascii=False) + '\n')
    except OSError:
        pass
