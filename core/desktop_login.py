"""Open allowlisted subscription-login commands; never collect credentials or CLI output."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from core.env_utils import FORBIDDEN_API_KEYS, resolve_cli


PROVIDERS = {
    'claude': ('Claude Code', ('auth', 'login', '--claudeai')),
    'codex': ('OpenAI Codex', ('login',)),
    'agy': ('Antigravity', ()),
    'grok': ('Grok', ('login', '--oauth')),
}
ALIASES = {'claude': 'claude', 'anthropic': 'claude', 'codex': 'codex',
           'openai': 'codex', 'agy': 'agy', 'antigravity': 'agy', 'google': 'agy'}
# Login must use the user's interactive account flow, not an inherited API credential.
AUTH_ENV = tuple(FORBIDDEN_API_KEYS) + (
    'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN', 'CODEX_ACCESS_TOKEN',
    'AGY_ADC_AUTH', 'GOOGLE_APPLICATION_CREDENTIALS',
    'GROK_AUTH_PROVIDER_COMMAND', 'GROK_AUTH_PROVIDER_ACCESS_TOKEN', 'GROK_AUTH_PROVIDER_REFRESH_TOKEN',
)
_LOCK = threading.Lock()
_LAST_OPENED = {}


class LoginError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def executable_for(provider, config):
    executable = None
    for role in ('head', 'builder', 'reviewer'):
        settings = config.get(role) or {}
        if isinstance(settings, dict) and ALIASES.get(str(settings.get('provider', '')).lower()) == provider:
            if settings.get('executable'):
                executable = str(settings['executable'])
                break
    executable = executable or resolve_cli(provider)
    if not executable:
        raise LoginError('CLI가 설치되어 있지 않습니다. 공식 설치 안내를 먼저 확인하세요.')
    path = shutil.which(os.path.expanduser(executable))
    if not path or not Path(path).is_file() or not os.access(path, os.X_OK):
        raise LoginError('CLI 실행 파일을 찾을 수 없습니다. 설치 경로를 확인하세요.')
    return str(Path(path).absolute())


def login_script(provider, executable, workspace):
    label, args = PROVIDERS[provider]
    command = ['/usr/bin/env']
    for key in AUTH_ENV:
        command.extend(('-u', key))
    command.extend(('PATH=' + os.environ.get('PATH', '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin'),
                    executable, *args))
    intro = label + ' 계정 로그인 · 비밀번호와 인증 코드는 공식 로그인 화면에 직접 입력하세요.'
    if provider == 'agy':
        intro += ' 기존 로그인은 CLI에서 확인하고 계정을 관리하세요.'
    return '\n'.join((
        '#!/bin/bash', 'set -u', 'umask 077',
        'cd -- ' + shlex.quote(str(workspace)) + ' || exit 1',
        "printf '%s\\n' " + shlex.quote(intro),
        shlex.join(command), 'login_result=$?',
        "printf '\\n%s\\n' " + shlex.quote('로그인을 마쳤다면 AI Dev Director에서 「로그인 완료 · 연결 확인」을 누르세요.'),
        'exit "$login_result"', '',
    ))


def open_login(provider, config, engine_root):
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise LoginError('지원하지 않는 AI입니다.')
    if sys.platform != 'darwin':
        raise LoginError('로그인 창 열기는 macOS에서 지원합니다.')
    executable = executable_for(provider, config)
    # Prevent a double-click from opening two OAuth callback listeners.
    with _LOCK:
        now = time.monotonic()
        if now - _LAST_OPENED.get(provider, float('-inf')) < 5:
            raise LoginError('로그인 창을 열고 있습니다. 열린 터미널을 확인하세요.', 409)
        directory = Path(engine_root) / 'data' / 'cli-login'
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        workspace = directory / 'workspace'
        workspace.mkdir(exist_ok=True, mode=0o700)
        # Generated files contain commands only; no login output, account IDs or tokens.
        fd, filename = tempfile.mkstemp(prefix=provider + '-', suffix='.command', dir=directory)
        script = Path(filename)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(login_script(provider, executable, workspace))
            script.chmod(0o700)
            result = subprocess.run(
                ['/usr/bin/open', '-a', 'Terminal', str(script)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=8, check=False,
            )
            if result.returncode:
                raise LoginError('로그인 터미널을 열지 못했습니다. 잠시 후 다시 시도하세요.', 500)
        except (OSError, subprocess.SubprocessError):
            script.unlink(missing_ok=True)
            raise LoginError('로그인 터미널을 열지 못했습니다. 잠시 후 다시 시도하세요.', 500) from None
        except LoginError:
            script.unlink(missing_ok=True)
            raise
        _LAST_OPENED[provider] = time.monotonic()
    message = PROVIDERS[provider][0] + ' 로그인 창을 열었습니다. 터미널과 공식 브라우저에서 로그인한 뒤 연결을 다시 확인하세요.'
    if provider == 'agy':
        message += ' Antigravity의 로그인 여부는 CLI에서 직접 확인합니다.'
    return {'status': 'opened', 'provider': provider, 'message': message}
