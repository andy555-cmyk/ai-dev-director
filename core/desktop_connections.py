"""Connection badges with explicit evidence, never inferred from installation alone."""
from datetime import datetime, timezone
from contextlib import closing
import sqlite3

NAMES = ('claude', 'codex', 'agy', 'grok')
PROVIDERS = {'ANTHROPIC': 'claude', 'OPENAI': 'codex', 'GOOGLE': 'agy'}
MAX_AGE = 600


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError):
        return None


def connection_rows(report, evidence=None, now=None):
    now = now or datetime.now(timezone.utc)
    evidence = evidence or {}
    report = report or {}
    checked = report.get('checked_at')

    def fresh(value):
        at = _time(value)
        return at is not None and -30 <= (now - at).total_seconds() <= MAX_AGE

    rows = []
    for name in NAMES:
        cli = next((p for p in report.get('providers', []) if p.get('name') == name), None)
        event = evidence.get(name) or {}
        row = {'name': name, 'state': 'unknown', 'label': '확인 필요',
               'reason': '아직 연결을 점검하지 않았습니다.', 'checked_at': checked,
               'verified_by': None}

        def mark(state, reason, by=None, at=checked):
            row.update(state=state, label={'connected': '연결됨', 'disconnected': '연결 안됨',
                                          'unknown': '확인 필요'}[state],
                       reason=reason, verified_by=by, checked_at=at)

        auth = cli.get('auth') if cli else None
        if cli and fresh(checked) and not cli.get('installed'):
            mark('disconnected', 'CLI가 설치되어 있지 않습니다.')
        elif cli and fresh(checked) and cli.get('responding') is False:
            mark('disconnected', 'CLI 실행 확인에 실패했습니다. 설치 경로를 점검하세요.')
        elif cli and fresh(checked) and auth == 'not_logged_in':
            mark('disconnected', '계정 로그인이 필요합니다.')
        elif cli and fresh(checked) and auth == 'api_billing':
            mark('disconnected', 'API 인증 상태입니다. 구독 계정으로 로그인하세요.')
        elif event.get('success') and fresh(event.get('checked_at')):
            mark('connected', '최근 10분 이내 실제 AI 응답을 확인했습니다.', 'response', event['checked_at'])
        elif event.get('failed') and fresh(event.get('checked_at')) and (
                not _time(checked) or _time(event['checked_at']) > _time(checked)):
            mark('unknown', '최근 AI 실행에 실패했습니다. 연결을 다시 점검하세요.', at=event['checked_at'])
        elif cli and fresh(checked) and auth == 'logged_in' and cli.get('responding') is True:
            mark('connected', 'CLI 실행과 구독 계정 로그인을 확인했습니다.', 'login')
        elif not fresh(checked):
            mark('unknown', '마지막 점검이 만료됐습니다. 다시 점검하세요.' if checked else row['reason'])
        elif cli and auth == 'timeout':
            mark('unknown', '로그인 점검 시간이 초과됐습니다. 다시 점검하세요.')
        elif cli and auth == 'manual_check':
            mark('unknown', 'CLI 설치됨 · 로그인과 최근 실제 응답은 확인이 필요합니다.')
        elif cli:
            mark('unknown', 'CLI 설치됨 · 로그인 상태를 확인하지 못했습니다.')
        rows.append(row)
    return rows


def _recent_calls():
    # Read only metadata from this app's work ledger, never CLI auth files or prompt/answer text.
    from core.db_path import get_db_path
    db = get_db_path()
    if not db.exists():
        return {}
    result = {}
    try:
        with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=2)) as conn:
            for provider, name in PROVIDERS.items():
                row = conn.execute('''SELECT status, ended_at, output_chars FROM ai_usage
                    WHERE provider=? AND source='live' AND ended_at IS NOT NULL
                    ORDER BY id DESC LIMIT 1''', (provider,)).fetchone()
                if row:
                    result[name] = {'success': row[0] == 'OK' and (row[2] or 0) > 0,
                                    'failed': row[0] in ('ERROR', 'TIMEOUT'), 'checked_at': row[1]}
    except sqlite3.Error:
        pass
    return result


def snapshot(report, engine_root):
    evidence = _recent_calls()
    from core.grok_research import manager
    try:
        job = manager(engine_root).snapshot().get('job') or {}
        evidence['grok'] = {'success': job.get('state') == 'completed' and bool(job.get('answer')),
                            'failed': job.get('state') == 'failed', 'checked_at': job.get('finished_at')}
        from core.grok_pipeline import live_snapshot
        records = (live_snapshot(engine_root) or {}).get('records', [])
        terminal = [r for r in records if r.get('finished_at') and r.get('state') not in ('queued','running','cancelling')]
        if terminal:
            last = terminal[-1]
            if (last.get('finished_at') or '') > (job.get('finished_at') or ''):
                evidence['grok'] = {'success':last.get('state')=='completed' and bool(last.get('summary')),
                                    'failed':last.get('state') in ('failed','unavailable'), 'checked_at':last['finished_at']}
    except (OSError, ValueError):
        pass
    return {'providers': connection_rows(report, evidence), 'checked_at': (report or {}).get('checked_at')}
