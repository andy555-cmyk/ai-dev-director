"""macOS launcher: protected upgrade, dependency fingerprint, health check and shutdown."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser
from install_support import install_engine

VERSION = '0.4.4'
URL = 'http://127.0.0.1:8081'


def health():
    try:
        with urllib.request.urlopen(URL + '/health', timeout=1) as r:
            return json.load(r).get('product') == 'ai-dev-director-macos'
    except (OSError, ValueError):
        return False


def open_screen():
    # `open` hands the URL to the default browser and brings it forward; webbrowser.open can stay silent when the
    # launcher runs detached from Finder.
    if os.environ.get('BROWSER') == 'true':      # headless restart (reinstall/QA): no window on the owner's screen
        return
    try:
        subprocess.run(['/usr/bin/open', URL], timeout=10)
    except (OSError, subprocess.SubprocessError):
        webbrowser.open(URL)


def main():
    resources, state = map(Path, sys.argv[1:3])
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'launcher.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if health():
                open_screen()
                print('이미 실행 중입니다. 화면을 열었습니다.', flush=True)
            else:
                print('이미 시작하는 중입니다. 잠시 뒤 화면이 열립니다.', flush=True)
            return 0
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', 8081)) == 0:
                if health():
                    open_screen()
                    print('기존 AI DEV DIRECTOR 화면을 열었습니다.', flush=True)
                    return 0
                print('8081 포트가 사용 중입니다. 해당 프로그램을 종료한 뒤 다시 실행하세요.')
                return 1
        app = install_engine(resources / 'engine', state, VERSION)
        virtual = state / 'venv'
        python = virtual / 'bin/python'
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(virtual)
        fingerprint = hashlib.sha256((app / 'requirements.txt').read_bytes()).hexdigest()
        stamp = virtual / 'director-requirements.sha256'
        if not stamp.exists() or stamp.read_text() != fingerprint:
            subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(app / 'requirements.txt')], check=True)
            stamp.write_text(fingerprint)
        env = dict(os.environ)
        env['PATH'] = str(virtual / 'bin') + os.pathsep + env.get('PATH', '')
        config = app / 'config.yaml'
        marker = state / 'mac-config-v1'
        if not marker.exists():
            # Preserve an existing user configuration; only remove the shipped Windows examples.
            subprocess.run([str(python), '-c',
                'import yaml,sys; p=sys.argv[1]; d=yaml.safe_load(open(p)); '
                's=d.get("solomon",{}); '
                'd.update(solomon={"allowed_roots":[],"denied":[sys.argv[2]]}) if s.get("allowed_roots")==["D:/work"] else None; '
                'open(p,"w").write(yaml.safe_dump(d,allow_unicode=True,sort_keys=False))',
                str(config), str(app)], check=True)
            marker.touch()
        print('\nAI DEV DIRECTOR macOS Preview ' + VERSION + '\n설정: ' + str(config), flush=True)
        print('업데이트 백업: ' + str(state / 'backups'), flush=True)
        print('진단: ' + URL + '/setup\n종료: 화면의 시스템 중지 또는 Control+C\n', flush=True)
        # The browser service must not retain a Terminal TTY: closing that window revokes its descriptors and
        # BaseHTTPRequestHandler can otherwise fail while logging a request, before sending any HTTP response.
        server = subprocess.Popen([str(python), 'companion_server.py'], cwd=app, env=env, start_new_session=True,
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def open_when_ready():
            for _ in range(60):
                if server.poll() is not None:
                    return
                if health():
                    open_screen()
                    return
                time.sleep(0.5)
            print('서버 실행을 확인하지 못했습니다. 터미널의 오류를 확인하세요.', flush=True)
        threading.Thread(target=open_when_ready, daemon=True).start()
        try:
            return server.wait()
        except KeyboardInterrupt:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGINT)
                try:
                    server.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGTERM)
                    server.wait(timeout=5)
            return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('실행에 실패했습니다: ' + str(exc), file=sys.stderr)
        if sys.stdin and sys.stdin.isatty():
            input('엔터를 누르면 종료합니다.')
        raise SystemExit(1)
