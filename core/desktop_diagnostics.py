"""On-demand, bounded local checks. Never return raw auth output or credentials."""
import importlib.metadata
import json
import platform
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from core.env_utils import get_sanitized_env, resolve_cli
from core.process_runner import ProcessTreeRunner

VERSION = '0.4.0'
_CACHE = None
_LOCK = threading.Lock()
PROVIDERS = {'claude': 'claude', 'openai': 'codex', 'antigravity': 'agy'}
HELP = {'claude': 'claude auth login', 'codex': 'codex login',
        'agy': 'Antigravity에서 CLI 설치 및 로그인 상태를 직접 확인하세요.',
        'grok': 'grok login --oauth'}
HUMAN = {'claude': 'Claude Code', 'codex': 'Codex', 'agy': 'Antigravity', 'grok': 'Grok'}


def probe(argv):
    try:
        r = ProcessTreeRunner._run_process(argv=argv, env=get_sanitized_env(), timeout=4,
                                  no_output_timeout=4, heartbeat_interval=5)
        return r.exit_code, (r.stdout + '\n' + r.stderr)[:16000], r.timed_out
    except Exception:
        # Exception text and auth output may contain credentials or account details.
        return None, '', False


def _cli(name, executable):
    result = {'name': name, 'installed': bool(executable), 'version': None,
              'auth': 'missing', 'billing': 'unknown', 'help': HELP[name]}
    if not executable:
        return result
    code, output, timed_out = probe([executable, '--version'])
    version = re.search(r'\b\d+\.\d+(?:\.\d+)?\b', output)
    result['version'] = version.group() if code == 0 and version else None
    result['responding'] = code == 0 and not timed_out
    result['auth'] = 'manual_check' if name in ('agy', 'grok') else 'unknown'
    if name == 'agy':
        return result  # No documented non-interactive auth probe; never guess.
    if name == 'grok':
        # `grok models` lists models without a generation call and starts with the sign-in line.
        code, output, timed_out = probe([executable, 'models'])
        lower = output.lower()
        if not timed_out and code == 0 and 'not authenticated' in lower:
            result['auth'] = 'not_logged_in'
        elif not timed_out and code == 0 and 'you are logged in' in lower:
            result.update(auth='logged_in', billing='subscription')
        return result
    args = ['auth', 'status'] if name == 'claude' else ['login', 'status']
    code, output, timed_out = probe([executable, *args])
    if timed_out or code is None:
        result['auth'] = 'timeout' if timed_out else 'unknown'
        return result
    if name == 'claude':
        try:
            auth = json.loads(output.strip())
        except (ValueError, TypeError):
            auth = {}
        if not isinstance(auth, dict):
            auth = {}
        method = auth.get('authMethod', '')
        if method in ('api_key', 'api_key_helper', 'third_party'):
            result.update(auth='api_billing', billing='api_or_external')
        elif method == 'claude.ai' and code == 0 and auth.get('loggedIn') is not False:
            result.update(auth='logged_in', billing='subscription')
        elif method == 'oauth_token' and code == 0 and auth.get('loggedIn') is not False:
            # `claude setup-token` long-lived token: issued only to Pro/Max subscriptions, billed to the plan.
            result.update(auth='logged_in', billing='subscription', auth_detail='long_lived_token')
        elif code == 1 or auth.get('loggedIn') is False or method == 'none':
            result['auth'] = 'not_logged_in'
    else:
        lower = output.lower()
        if code == 0 and 'api key' in lower:
            result.update(auth='api_billing', billing='api_or_external')
        elif code == 0 and 'logged in using chatgpt' in lower:
            result.update(auth='logged_in', billing='subscription')
        elif code == 1 and ('not logged in' in lower or 'not authenticated' in lower):
            result['auth'] = 'not_logged_in'
    return result


def collect(config):
    if not isinstance(config, dict):
        raise ValueError('설정은 YAML 객체여야 합니다.')
    roles, paths, warnings = {}, {}, []
    for role in ('head', 'builder', 'reviewer'):
        settings = config.get(role) or {}
        if not isinstance(settings, dict):
            raise ValueError('역할 설정은 YAML 객체여야 합니다.')
        raw = str(settings.get('provider', '')).lower()
        name = {'codex': 'codex', 'openai': 'codex', 'claude': 'claude',
                'anthropic': 'claude', 'antigravity': 'agy', 'google': 'agy'}.get(raw)
        roles[role] = name or 'unknown'
        if name:
            executable = settings.get('executable') or resolve_cli(name)
            if name in paths and paths[name] != executable:
                warnings.append('동일 AI의 역할별 실행 경로가 다릅니다. 설정을 확인하세요.')
            paths[name] = executable
    for name in HELP:
        if name not in paths:
            paths[name] = resolve_cli(name)
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(lambda item: _cli(*item), paths.items()))
    by_name = {r['name']: r for r in rows}
    installed = sum(r['installed'] for r in rows)
    confirmed = sum(r['auth'] == 'logged_in' and r.get('responding') for r in rows)
    blockers = []
    if sys.version_info < (3, 9):
        blockers.append('Python 3.9 이상이 필요합니다.')
    git = shutil.which('git')
    git_ok = bool(git and probe([git, '--version'])[0] == 0)
    if not git_ok:
        blockers.append('Git 설치와 실행 상태를 확인하세요.')
    dependencies = {}
    for package in ('PyYAML', 'click', 'pydantic', 'psutil', 'pytest'):
        try:
            dependencies[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            dependencies[package] = None
            blockers.append(package + ' 설치가 필요합니다.')
    if installed < 2:
        blockers.append('AI CLI를 최소 두 개 설치하세요.')
    notices = []
    if 'unknown' not in roles.values():
        # Missing CLI -> the run substitutes another installed AI (ProviderManager.resolve_roles). Show that.
        from core.role_settings import CLI_NAMES, effective
        available = {p for p, cli in CLI_NAMES.items() if by_name.get(cli, {}).get('installed')}
        to_cli = {'openai': 'codex', 'claude': 'claude', 'antigravity': 'agy'}
        cfg = {r: {'provider': {'codex': 'openai', 'agy': 'antigravity'}.get(n, n)} for r, n in roles.items()}
        using, subs = effective(cfg, available)
        for sub in subs:
            asked, using_name = to_cli[sub['requested']], HUMAN[to_cli[sub['using']]]
            if asked in {to_cli[p] for p in available}:
                notices.append(sub['role'].upper() + ': ' + HUMAN[asked] + '가 다른 역할로 옮겨 '
                               + using_name + '가 대신 맡습니다.')
            else:
                notices.append(sub['role'].upper() + ': ' + HUMAN[asked] + ' CLI가 없어 ' + using_name + '가 대신 맡습니다.')
        roles = {r: to_cli[p] for r, p in using.items()}
    for role, name in roles.items():
        if name == 'unknown':
            blockers.append(role.upper() + ' 역할의 제공자 설정을 확인하세요.')
        elif not by_name.get(name, {}).get('installed'):
            warnings.append(role.upper() + ' 역할의 CLI가 없습니다. 역할 조정 또는 대체 도구를 확인하세요.')
    if roles.get('builder') == roles.get('reviewer'):
        warnings.append('구현과 검수를 같은 AI가 맡습니다. 독립성이 낮습니다.')
    if roles.get('head') == roles.get('reviewer'):
        warnings.append('지휘와 검수를 같은 AI가 맡습니다. 독립성이 낮습니다.')
    for row in rows:
        if row['name'] not in roles.values():
            continue
        if row['auth'] == 'api_billing':
            blockers.append(row['name'] + ': 구독 로그인이 아닌 API/외부 인증입니다.')
        elif row['auth'] != 'logged_in' or not row.get('responding'):
            warnings.append(row['name'] + ': 설치·구독 로그인 상태를 추가 확인하세요.')
    ready = not blockers and all(by_name.get(name, {}).get('auth') == 'logged_in'
                                 and by_name[name].get('responding') for name in roles.values())
    return {'product': 'ai-dev-director-macos', 'version': VERSION,
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'platform': platform.system(), 'architecture': platform.machine(),
            'python': platform.python_version(), 'git_ok': git_ok,
            'dependencies': dependencies, 'roles': roles, 'providers': rows,
            'installed_count': installed, 'confirmed_subscription_count': confirmed,
            'status': 'blocked' if blockers else ('ready' if ready else 'needs_check'),
            'blockers': blockers, 'warnings': warnings, 'notices': notices,
            'scope': '설치 및 로그인 점검입니다. 실제 AI 작업 성공·사용량·요금은 검증하지 않습니다.'}


def cached():
    return _CACHE


def refresh(config):
    global _CACHE
    if not _LOCK.acquire(blocking=False):
        return None
    try:
        report = collect(config)
        _CACHE = report
        return report
    finally:
        _LOCK.release()
