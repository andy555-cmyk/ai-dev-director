"""Publish an AI Dev Director update (0.4.3) — the other developer's app shows 「업데이트」 after this.

  python3 tools/release_mac.py keygen --name 이름          # once per developer: key into the macOS keychain, prints public key
  python3 tools/release_mac.py publish --version 0.4.4 --notes "바뀐 점" [--name 이름] [--repo 주인/저장소] [--dry-run]

publish = version bump in the four version spots -> tests -> build DMG -> sign manifest with your keychain key ->
GitHub release v<version> with AI-Dev-Director-mac.dmg + AI-Dev-Director-update.json (+ SHA256SUMS.txt).
The private key never leaves the keychain item (service ai-dev-director-release-signing) and is never printed.
A new developer: run keygen, send the printed public key, and have it added to TRUSTED_KEYS in core/updater.py by
a release signed with a key that is already trusted.
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


def publish(a):
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
        py = shutil.which('python3')
        venv = ROOT.parent / '.venv-test' / 'bin' / 'python'
        r = subprocess.run([str(venv) if venv.exists() else py, '-m', 'pytest', '-q', '-x', 'tests'], cwd=ROOT)
        if r.returncode != 0:
            raise SystemExit('테스트가 실패해서 출시하지 않습니다')
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
    title = 'AI Dev Director %s' % a.version
    notes = (a.notes or '') + '\n\n출시: %s · 서명 키 %s' % (name, U.key_fingerprint(pub))
    subprocess.run([gh, 'release', 'create', 'v' + a.version, str(dmg), str(manifest), str(dist / 'SHA256SUMS.txt'),
                    '-R', repo, '--title', title, '--notes', notes], check=True)
    print('올렸습니다: https://github.com/%s/releases/tag/v%s' % (repo, a.version))


def main():
    ap = argparse.ArgumentParser(description='AI Dev Director 업데이트 출시')
    sub = ap.add_subparsers(dest='cmd', required=True)
    k = sub.add_parser('keygen'); k.add_argument('--name', required=True)
    p = sub.add_parser('pubkey'); p.add_argument('--name')
    b = sub.add_parser('publish')
    b.add_argument('--version', required=True); b.add_argument('--notes', default='')
    b.add_argument('--name'); b.add_argument('--repo'); b.add_argument('--dry-run', action='store_true')
    b.add_argument('--skip-tests', action='store_true')
    a = ap.parse_args()
    if a.cmd == 'keygen':
        keygen(a.name)
    elif a.cmd == 'pubkey':
        pubkey(a.name or default_name())
    else:
        publish(a)


if __name__ == '__main__':
    main()
