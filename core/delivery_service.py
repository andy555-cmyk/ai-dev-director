"""One shared DeliveryRunner for the console (companion) and the `director.py deliver` command.

The console never blocks: start / approve / feedback return at once and the runner advances in a daemon thread
until the delivery waits for the owner again. Screenshots are served only if they sit inside data/deliveries.
"""
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from core import delivery

_RUNNER = None
_THREADS: Dict[str, threading.Thread] = {}
_GUARD = threading.Lock()


def runner(notify=None) -> delivery.DeliveryRunner:
    global _RUNNER
    if _RUNNER is None or notify:
        from director import load_config
        from core.orchestrator import Orchestrator
        r = delivery.DeliveryRunner(lambda: Orchestrator(config=delivery.web_config(load_config())), notify=notify)
        if notify:
            return r
        _RUNNER = r
    return _RUNNER


def advance(delivery_id: str) -> bool:
    """Run in the background unless a thread for this delivery is already alive."""
    with _GUARD:
        t = _THREADS.get(delivery_id)
        if t and t.is_alive():
            return False
        t = threading.Thread(target=_safe_run, args=(delivery_id,), name='delivery-' + delivery_id, daemon=True)
        _THREADS[delivery_id] = t
        t.start()
        return True


def _safe_run(delivery_id):
    try:
        runner().run(delivery_id)
    except Exception:        # run() already records failures; never kill the console
        pass


def running(delivery_id: str) -> bool:
    t = _THREADS.get(delivery_id)
    return bool(t and t.is_alive())


def view(d: Dict[str, Any], events: bool = False) -> Dict[str, Any]:
    tasks = d.get('tasks') or {}
    done = sum(1 for t in tasks.values() if t.get('status') == 'done')
    out = {k: d.get(k) for k in ('delivery_id', 'goal', 'title', 'summary', 'phase', 'reason', 'plan_hash', 'plan_version',
                                 'created_at', 'updated_at', 'approvals', 'feedback', 'release', 'project_path')}
    out.update(progress={'done': done, 'total': len(tasks)}, running=running(d['delivery_id']),
               tasks=[{'id': k, **{x: v.get(x) for x in ('title', 'status', 'screen_passed', 'screen_reasons', 'screens_checked')},
                       'shots': [shot_url(d, s) for s in (v.get('last_shots') or [])[:4]]} for k, v in tasks.items()],
               latest_shots=[shot_url(d, s) for s in (d.get('latest_shots') or [])[:8]],
               wireframes={k: [shot_url(d, s) for s in v[:2]] for k, v in (d.get('wireframe_shots') or {}).items()})
    if d.get('plan_dir'):
        out['plan_docs'] = plan_docs(d)
    if events:
        out['events'] = runner().store.events(d['delivery_id'], 60)
    return out


def plan_docs(d) -> Dict[str, str]:
    from core import planning
    docs = {}
    for k in planning.DOCS:
        try:
            docs[k] = (Path(d['plan_dir']) / 'spec' / (k + '.md')).read_text(encoding='utf-8')[:6000]
        except OSError:
            pass
    return docs


def shot_url(d, path: str) -> str:
    try:
        rel = Path(path).resolve().relative_to(runner().store.folder(d['delivery_id']).resolve())
    except (ValueError, OSError):
        return ''
    return '/ops/deliveries/%s/file/%s' % (d['delivery_id'], rel.as_posix())


def file_path(delivery_id: str, rel: str) -> Optional[Path]:
    """Only PNG files inside this delivery's own folder."""
    base = runner().store.folder(delivery_id).resolve()
    p = (base / rel).resolve()
    if base not in p.parents or p.suffix.lower() != '.png' or not p.is_file():
        return None
    return p


def listing() -> List[Dict[str, Any]]:
    return [view(d) for d in runner().store.all()[:20]]
