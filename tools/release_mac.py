"""Publish an AI Dev Director update (0.4.3) — the other developer's app shows 「업데이트」 after this.

  python3 tools/release_mac.py keygen --name 이름          # once per developer: key into the macOS keychain, prints public key
  python3 tools/release_mac.py publish --version 0.4.4 --notes "바뀐 점" [--name 이름] [--repo 주인/저장소] [--dry-run]

publish = version bump in the four version spots -> tests -> build DMG -> sign manifest with your keychain key ->
GitHub release v<version> with AI-Dev-Director-mac.dmg + AI-Dev-Director-update.json (+ SHA256SUMS.txt).
The private key never leaves the keychain item (service ai-dev-director-release-signing) and is never printed.

Two developers, nobody has to hand anything over:
  python3 tools/release_mac.py ship --notes "바뀐 점"   # anyone: tests -> commit -> push. A trusted signer also releases;
                                                      # anyone else's Mac makes its own key and pushes only the public half
  python3 tools/release_mac.py hub                     # the owner's Mac (launchd, hourly): new commits on origin/main ->
                                                      # register pushed public keys -> tests -> signed release
"""
import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DIRECTOR_TESTING', '0')
from core import ed25519  # noqa: E402
from core import updater as U  # noqa: E402

SERVICE = 'ai-dev-director-release-signing'
VERSION_SPOTS = [
    ('packaging/macos/build_bundle.py', r"^VERSION = '[\d.]+'", "VERSION = '{v}'"),
    ('packaging/macos/mac_bootstrap.py', r"^VERSION = '[\d.]+'", "VERSION = '{v}'"),
    ('core/desktop_diagnostics.py', r"^VERSION = '[\d.]+'", "VERSION = '{v}'"),
    ('console/index.html', r"macOS Preview [\d.]+", "macOS Preview {v}"),
]


def _keychain_get(name):
    r = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', SERVICE, '-a', name, '-w'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    raw = r.stdout.strip()
    if not re.fullmatch(r'[0-9a-f]{64}', raw):
        raise SystemExit('키체인 항목 형식이 맞지 않습니다: ' + SERVICE)
    return bytes.fromhex(raw)


def default_name():
    # A Korean account name is printed by `security` as hex, so look for the registered signers first.
    for name in U.TRUSTED_KEYS:
        if _keychain_get(name):
            return name
    r = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', SERVICE], capture_output=True, text=True)
    m = re.search(r'"acct"<blob>="([^"]*)"', r.stdout)
    return m.group(1) if m else getpass.getuser()


def keygen(name):
    if _keychain_get(name):
        raise SystemExit('이미 키가 있습니다 (%s). 공개키만 다시 보려면 pubkey 를 쓰세요' % name)
    secret = secrets.token_bytes(32)
    r = subprocess.run(['/usr/bin/security', 'add-generic-password', '-s', SERVICE, '-a', name, '-l',
                        'AI Dev Director 출시 서명 키', '-w', secret.hex()], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit('키체인에 저장하지 못했습니다: ' + r.stderr.strip())
    pubkey(name)


def pubkey(name):
    secret = _keychain_get(name)
    if not secret:
        raise SystemExit('키가 없습니다. 먼저 keygen --name %s' % name)
    pub = base64.b64encode(ed25519.public_key(secret)).decode()
    trusted = U.TRUSTED_KEYS.get(name) == pub
    print(json.dumps({'name': name, 'public_key': pub, 'fingerprint': U.key_fingerprint(pub),
                      'trusted_in_this_source': trusted}, ensure_ascii=False))
    if not trusted:
        print('\n이 공개키를 core/updater.py TRUSTED_KEYS 에 넣어야 다른 맥이 이 서명을 믿습니다:\n'
              "    '%s': '%s',\n" % (name, pub))


def bump(version):
    for rel, pattern, repl in VERSION_SPOTS:
        p = ROOT / rel
        text = p.read_text(encoding='utf-8')
        new, n = re.subn(pattern, repl.format(v=version), text, count=1, flags=re.M)
        if n != 1:
            raise SystemExit('판 번호 자리를 찾지 못했습니다: ' + rel)
        p.write_text(new, encoding='utf-8')


def commit_and_push(version):
    """The release tag must point at the exact source that was built: commit the bump, push, return the sha."""
    git = lambda *args: subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True)
    git('add', '-A')
    if git('diff', '--cached', '--quiet').returncode != 0:
        r = git('commit', '-m', '출시 %s' % version)
        if r.returncode != 0:
            raise SystemExit('커밋하지 못했습니다: ' + r.stderr.strip()[:300])
    branch = git('branch', '--show-current').stdout.strip() or 'main'
    r = git('push', 'origin', branch)
    if r.returncode != 0:
        raise SystemExit('코드를 GitHub 에 올리지 못했습니다(출시 중단): ' + r.stderr.strip()[:300])
    return git('rev-parse', 'HEAD').stdout.strip()


def publish(a):
    a.version = a.version or next_version()
    if not U.VERSION_RE.match(a.version):
        raise SystemExit('판 번호는 0.4.4 같은 형식입니다')
    name = a.name or default_name()
    secret = _keychain_get(name)
    if not secret:
        raise SystemExit('출시 키가 없습니다. 먼저: python3 tools/release_mac.py keygen --name ' + name)
    pub = base64.b64encode(ed25519.public_key(secret)).decode()
    if U.TRUSTED_KEYS.get(name) != pub:
        raise SystemExit('이 키(%s)가 core/updater.py TRUSTED_KEYS 에 없습니다. 넣지 않고 출시하면 다른 맥이 설치를 거부합니다' % name)
    repo = a.repo or U.DEFAULT_REPO
    bump(a.version)
    if not a.skip_tests:
        run_tests()
    subprocess.run(['/usr/bin/python3', 'packaging/macos/build_bundle.py'], cwd=ROOT, check=True)
    out = ROOT.parent / 'macos-release'
    dist = out / ('publish-' + a.version)
    dist.mkdir(parents=True, exist_ok=True)
    dmg = dist / U.ASSET
    shutil.copy2(out / 'AI_Dev_Director_macOS_Preview.dmg', dmg)
    digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
    entry = {'app': U.APP, 'platform': U.PLATFORM, 'version': a.version, 'file': U.ASSET,
             'size': dmg.stat().st_size, 'sha256': digest, 'notes': a.notes or '',
             'published_at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}
    entry = U.sign_entry(entry, secret, name)
    if U.verify_entry(entry) != name:
        raise SystemExit('서명 확인 실패')
    manifest = dist / U.MANIFEST
    manifest.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding='utf-8')
    (dist / 'SHA256SUMS.txt').write_text('%s  %s\n' % (digest, U.ASSET))
    print(json.dumps({'version': a.version, 'signer': name, 'sha256': digest, 'size': entry['size'],
                      'folder': str(dist)}, ensure_ascii=False))
    if a.dry_run:
        print('시험 실행: GitHub 에 올리지 않았습니다')
        return
    gh = U._gh()
    if not gh:
        raise SystemExit('gh 가 없습니다. brew install gh 후 gh auth login')
    target = commit_and_push(a.version)
    title = 'AI Dev Director %s' % a.version
    notes = (a.notes or '') + '\n\n출시: %s · 서명 키 %s' % (name, U.key_fingerprint(pub))
    subprocess.run([gh, 'release', 'create', 'v' + a.version, str(dmg), str(manifest), str(dist / 'SHA256SUMS.txt'),
                    '-R', repo, '--title', title, '--notes', notes, '--target', target, '--latest'], check=True)
    print('올렸습니다: https://github.com/%s/releases/tag/v%s' % (repo, a.version))


def _git(*args, check=False):
    r = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit('git %s 실패: %s' % (args[0], (r.stderr or r.stdout).strip()[:300]))
    return r


def next_version():
    """Patch + 1 over the newest release tag (or the source version when nothing is released yet)."""
    _git('fetch', '--tags', '--quiet', 'origin')
    tags = [t.strip()[1:] for t in _git('tag', '-l', 'v*').stdout.split() if U.VERSION_RE.match(t.strip()[1:])]
    src = re.search(r"^VERSION = '([\d.]+)'", (ROOT / 'core/desktop_diagnostics.py').read_text(encoding='utf-8'), re.M).group(1)
    base = src
    for t in tags:
        if U.cmp_version(t, base) > 0:
            base = t
    parts = [int(x) for x in base.split('.')]
    if base == src and src not in tags:
        return src                                  # source already carries an unreleased version number
    parts[-1] += 1
    return '.'.join(map(str, parts))


KEYS_DIR = ROOT / 'release' / 'keys'


def developer_name():
    name = _git('config', 'user.name').stdout.strip() or getpass.getuser()
    return re.sub(r'[^0-9A-Za-z가-힣._-]', '', name)[:40] or getpass.getuser()


def _push(branch):
    r = _git('push', 'origin', branch)
    if r.returncode != 0 and U._gh():
        # first push from a new collaborator: accept the pending repository invitation and let git use gh's login
        gh = U._gh()
        inv = subprocess.run([gh, 'api', 'user/repository_invitations'], capture_output=True, text=True)
        try:
            for i in json.loads(inv.stdout or '[]'):
                if i.get('repository', {}).get('full_name', '').lower() == U.DEFAULT_REPO.lower():
                    subprocess.run([gh, 'api', '-X', 'PATCH', 'user/repository_invitations/%s' % i['id']],
                                   capture_output=True, text=True)
        except ValueError:
            pass
        subprocess.run([gh, 'auth', 'setup-git'], capture_output=True, text=True)
        r = _git('push', 'origin', branch)
    if r.returncode != 0:
        raise SystemExit('GitHub 에 올리지 못했습니다: ' + (r.stderr or '').strip()[:300] +
                         '\n(gh auth login 이 안 돼 있거나, 저장소 초대를 아직 못 받은 경우)')


def ship(a):
    """One command for any developer: test, commit, push; release too when this Mac holds a trusted key."""
    name = default_name()
    secret = _keychain_get(name)
    trusted = bool(secret) and U.TRUSTED_KEYS.get(name) == base64.b64encode(ed25519.public_key(secret)).decode()
    if not trusted:
        name = developer_name() if not secret else name
        if not _keychain_get(name):
            keygen(name)
        pub = base64.b64encode(ed25519.public_key(_keychain_get(name))).decode()
        KEYS_DIR.mkdir(parents=True, exist_ok=True)
        (KEYS_DIR / (name + '.pub')).write_text(pub + '\n', encoding='utf-8')
    if not a.skip_tests:
        run_tests()
    branch = _git('branch', '--show-current').stdout.strip() or 'main'
    _git('add', '-A')
    if _git('diff', '--cached', '--quiet').returncode != 0:
        _git('commit', '-m', a.notes or '디렉터 고침', check=True)
    pull = _git('pull', '--rebase', 'origin', branch)
    if pull.returncode != 0:
        _git('rebase', '--abort')
        raise SystemExit('GitHub 쪽 변경과 겹칩니다. git pull --rebase origin %s 로 겹친 곳을 정리한 뒤 다시 ship' % branch)
    _push(branch)
    if trusted:
        a.version, a.name, a.repo, a.dry_run, a.skip_tests = None, name, None, False, True
        publish(a)
    else:
        print('올렸습니다. 대표 맥이 한 시간 안에 시험·서명해서 새 판으로 내보내면, 두 맥 모두 앱 설정에 「업데이트」가 뜹니다')


def run_tests():
    py = shutil.which('python3')
    venv = ROOT.parent / '.venv-test' / 'bin' / 'python'
    env = dict(os.environ)
    if venv.exists():                    # some tests run a bare `python`; give them the same interpreter
        env['PATH'] = str(venv.parent) + os.pathsep + env.get('PATH', '')
    r = subprocess.run([str(venv) if venv.exists() else py, '-m', 'pytest', '-q', '-x', 'tests'], cwd=ROOT, env=env)
    if r.returncode != 0:
        raise SystemExit('테스트가 실패해서 올리지 않습니다')


def register_pushed_keys():
    """Public keys pushed by collaborators (release/keys/NAME.pub) become trusted in the next signed release.
    Push rights to the repository are the trust boundary; private keys never leave each developer's keychain."""
    added = []
    if not KEYS_DIR.is_dir():
        return added
    path = ROOT / 'core' / 'updater.py'
    src = path.read_text(encoding='utf-8')
    for f in sorted(KEYS_DIR.glob('*.pub')):
        name, pub = f.stem, f.read_text(encoding='utf-8').strip()
        try:
            ok = len(base64.b64decode(pub, validate=True)) == 32
        except ValueError:
            ok = False
        if not ok or not re.fullmatch(r'[0-9A-Za-z가-힣._-]{1,40}', name) or U.TRUSTED_KEYS.get(name) == pub:
            continue
        if name in U.TRUSTED_KEYS:              # a name may not silently replace an existing signer's key
            print('건너뜀: %s 는 이미 다른 키로 등록돼 있습니다' % name)
            continue
        line = "    '%s': '%s',   # 지문 %s · %s · release/keys 로 등록\n" % (name, pub, U.key_fingerprint(pub),
                                                                       time.strftime('%Y-%m-%d'))
        src = src.replace('TRUSTED_KEYS: Dict[str, str] = {\n', 'TRUSTED_KEYS: Dict[str, str] = {\n' + line, 1)
        U.TRUSTED_KEYS[name] = pub
        added.append(name)
    if added:
        path.write_text(src, encoding='utf-8')
    return added


HUB_STATE = Path.home() / 'Library' / 'Application Support' / 'AI Dev Director' / 'release-hub.json'


def hub(a):
    """Owner's Mac, run hourly by launchd: release whatever collaborators pushed to origin/main."""
    stamp = time.strftime('%F %T')
    state = {}
    try:
        state = json.loads(HUB_STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    if _git('status', '--porcelain').stdout.strip():
        print(stamp, '건너뜀: 이 맥에서 저장소를 고치는 중(커밋 안 된 변경)'); return
    _git('fetch', '--tags', '--quiet', 'origin', check=True)
    remote = _git('rev-parse', 'origin/main').stdout.strip()
    tags = [t for t in _git('tag', '-l', 'v*', '--sort=-v:refname').stdout.split()]
    released = _git('rev-list', '-n1', tags[0]).stdout.strip() if tags else ''
    if not remote or remote == released or _git('merge-base', '--is-ancestor', remote, released).returncode == 0:
        print(stamp, '새 커밋 없음'); return
    if state.get('failed') == remote and not a.force:
        print(stamp, '건너뜀: 이 커밋은 지난번 시험에서 실패했습니다', remote[:9]); return
    if _git('merge', '--ff-only', 'origin/main').returncode != 0:
        print(stamp, '건너뜀: 이 맥의 main 이 GitHub 와 갈라졌습니다'); return
    subjects = [s for s in _git('log', '--format=%s', (released + '..HEAD') if released else 'HEAD').stdout.splitlines()
                if not s.startswith('출시 ')]
    added = register_pushed_keys()
    notes = '\n'.join('- ' + s for s in subjects[:30])
    if added:
        notes += '\n- 출시 서명 등록: ' + ', '.join(added)
    a.version, a.notes, a.name, a.repo, a.dry_run = None, notes, None, None, False
    try:
        publish(a)
        state = {'last': stamp, 'released': remote}
    except SystemExit as exc:
        _git('checkout', '--', '.')
        state = {'last': stamp, 'failed': remote, 'reason': str(exc)}
        print(stamp, '출시 안 함:', exc)
    HUB_STATE.parent.mkdir(parents=True, exist_ok=True)
    HUB_STATE.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description='AI Dev Director 업데이트 출시')
    sub = ap.add_subparsers(dest='cmd', required=True)
    k = sub.add_parser('keygen'); k.add_argument('--name', required=True)
    p = sub.add_parser('pubkey'); p.add_argument('--name')
    b = sub.add_parser('publish')
    b.add_argument('--version'); b.add_argument('--notes', default='')
    b.add_argument('--name'); b.add_argument('--repo'); b.add_argument('--dry-run', action='store_true')
    b.add_argument('--skip-tests', action='store_true')
    sp = sub.add_parser('ship'); sp.add_argument('--notes', default=''); sp.add_argument('--skip-tests', action='store_true')
    h = sub.add_parser('hub'); h.add_argument('--skip-tests', action='store_true'); h.add_argument('--force', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'keygen':
        keygen(a.name)
    elif a.cmd == 'ship':
        ship(a)
    elif a.cmd == 'hub':
        hub(a)
    elif a.cmd == 'pubkey':
        pubkey(a.name or default_name())
    else:
        publish(a)


if __name__ == '__main__':
    main()
