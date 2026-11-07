"""In-app update (0.4.3): check GitHub Releases, verify a signed manifest, swap the app and start it again.

- Feed: the latest release of a GitHub repository (settings 「받는 곳」, default DEFAULT_REPO). A public repository is
  read without login; a private one is read through the `gh` CLI when it is logged in.
- Release assets (fixed names): AI-Dev-Director-mac.dmg and AI-Dev-Director-update.json (the manifest).
- Trust: the manifest's fixed fields (app, platform, version, file, size, sha256) are signed with a developer's
  Ed25519 key. The app only accepts signatures from TRUSTED_KEYS below, so a changed feed cannot install anything
  else. Each developer has their own key (tools/release_mac.py keygen); a new developer's public key is added here
  and shipped once by someone already trusted.
- Install: download to a private folder -> size and SHA-256 must match the signed values -> mount the DMG read-only ->
  bundle id and version must match -> copy the app into the updates folder -> a detached script waits for the app
  to quit, moves the current app to updates/old-apps (never deleted), puts the new app in place and opens it.
  If the swap fails, the old app goes back. Data (missions, deliveries, settings) is never touched.
"""
import base64
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from core import ed25519
from core.db_path import get_db_path

APP = 'AI-Dev-Director'
PLATFORM = 'mac'
BUNDLE_ID = 'kr.hayday.aidevdirector'
APP_NAME = 'AI Dev Director.app'
ASSET = 'AI-Dev-Director-mac.dmg'
MANIFEST = 'AI-Dev-Director-update.json'
SIG_CONTEXT = b'AI-DEV-DIRECTOR-UPDATE-SIG-v1\n'
DEFAULT_REPO = 'andy555-cmyk/ai-dev-director'
CHECK_EVERY = 6 * 3600
MAX_DMG = 400 * 1024 * 1024
MAX_MANIFEST = 64 * 1024
# name -> Ed25519 public key (32 bytes, base64). Add a developer by adding a line and shipping one release signed by
# someone already on this list. Remove an old key only after a release that no longer needs it.
TRUSTED_KEYS: Dict[str, str] = {
    '이승원': 'bOzbZpce7JIvfuMBgoKyyIRH1ely1EkoU9XJatFjf5w=',   # 지문 319ba2c18a33607d · 2026-11-07 · 대표 맥 키체인
}
REPO_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$')
VERSION_RE = re.compile(r'^\d+(\.\d+){1,3}$')


class UpdateError(Exception):
    pass


def data_dir() -> Path:
    return get_db_path().parent


def updates_dir() -> Path:
    p = data_dir() / 'updates'
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p


def current_version() -> str:
    from core.desktop_diagnostics import VERSION
    return VERSION


def cmp_version(a: str, b: str) -> int:
    pa = [int(x) for x in re.findall(r'\d+', str(a))]
    pb = [int(x) for x in re.findall(r'\d+', str(b))]
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    return (pa > pb) - (pa < pb)


# ---------------------------------------------------------------- settings
def _settings_path() -> Path:
    return data_dir() / 'settings.json'


def load_settings() -> Dict[str, Any]:
    out = {'update_repo': DEFAULT_REPO, 'auto_check': True}
    try:
        saved = json.loads(_settings_path().read_text(encoding='utf-8'))
        if isinstance(saved, dict):
            if isinstance(saved.get('update_repo'), str) and REPO_RE.match(saved['update_repo']):
                out['update_repo'] = saved['update_repo']
            if isinstance(saved.get('auto_check'), bool):
                out['auto_check'] = saved['auto_check']
    except (OSError, ValueError):
        pass
    return out


def save_settings(patch: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(patch, dict) or not patch or set(patch) - {'update_repo', 'auto_check'}:
        raise ValueError('바꿀 수 있는 설정은 업데이트 받는 곳과 자동 확인입니다')
    cur = load_settings()
    if 'update_repo' in patch:
        repo = str(patch['update_repo']).strip().removeprefix('https://github.com/').strip('/')
        if not REPO_RE.match(repo):
            raise ValueError('받는 곳은 「주인/저장소」 형식입니다 (예: andy555-cmyk/ai-dev-director)')
        cur['update_repo'] = repo
    if 'auto_check' in patch:
        if not isinstance(patch['auto_check'], bool):
            raise ValueError('자동 확인은 켬/끔만 됩니다')
        cur['auto_check'] = patch['auto_check']
    tmp = _settings_path().with_suffix('.tmp')
    tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(_settings_path())
    return cur


# ---------------------------------------------------------------- signing
def signed_fields(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    f = {k: entry.get(k) for k in ('app', 'platform', 'version', 'file', 'size', 'sha256')}
    if f['app'] != APP or f['platform'] != PLATFORM:
        return None
    if not isinstance(f['version'], str) or not VERSION_RE.match(f['version']):
        return None
    if f['file'] != ASSET:
        return None
    if not isinstance(f['size'], int) or isinstance(f['size'], bool) or not 0 < f['size'] <= MAX_DMG:
        return None
    if not isinstance(f['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', f['sha256']):
        return None
    return f


def signed_payload(f: Dict[str, Any]) -> bytes:
    return SIG_CONTEXT + json.dumps([f['app'], f['platform'], f['version'], f['file'], f['size'], f['sha256']],
                                    ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def key_fingerprint(public_b64: str) -> str:
    return hashlib.sha256(base64.b64decode(public_b64)).hexdigest()[:16]


def sign_entry(entry: Dict[str, Any], secret: bytes, signer: str) -> Dict[str, Any]:
    f = signed_fields(entry)
    if f is None:
        raise UpdateError('서명할 목록 형식이 맞지 않습니다')
    out = dict(entry)
    out['signer'] = signer
    out['key'] = base64.b64encode(ed25519.public_key(secret)).decode()
    out['sig'] = base64.b64encode(ed25519.sign(secret, signed_payload(f))).decode()
    return out


def verify_entry(entry: Any, keys: Optional[Dict[str, str]] = None) -> str:
    """Name of the trusted signer, or raises UpdateError with the reason."""
    keys = TRUSTED_KEYS if keys is None else keys
    f = signed_fields(entry)
    if f is None:
        raise UpdateError('업데이트 목록 형식이 맞지 않습니다 — 설치 안 함')
    try:
        sig = base64.b64decode(str(entry.get('sig') or ''), validate=True)
    except ValueError:
        sig = b''
    if len(sig) != 64:
        raise UpdateError('서명 없는 업데이트 — 설치 안 함')
    payload = signed_payload(f)
    for name, pub in keys.items():
        if ed25519.verify(base64.b64decode(pub), payload, sig):
            return name
    raise UpdateError('믿을 수 있는 개발자 서명이 아닙니다 — 설치 안 함')


# ---------------------------------------------------------------- GitHub
def _gh() -> Optional[str]:
    for c in (shutil.which('gh'), '/opt/homebrew/bin/gh', '/usr/local/bin/gh'):
        if c and Path(c).exists():
            return c
    return None


def _http(url: str, limit: int, dest: Optional[Path] = None, accept: str = 'application/json') -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': 'ai-dev-director-updater', 'Accept': accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        total = 0
        chunks = []
        out = dest.open('wb') if dest else None
        try:
            while True:
                block = r.read(1 << 16)
                if not block:
                    break
                total += len(block)
                if total > limit:
                    raise UpdateError('받는 파일이 서명된 크기보다 큽니다 — 중단')
                if out:
                    out.write(block)
                else:
                    chunks.append(block)
        finally:
            if out:
                out.close()
        return b''.join(chunks)


def latest_release(repo: str, run: Callable = subprocess.run) -> Dict[str, Any]:
    """Find the newest release. Public repos are read through plain github.com download links, which are not
    subject to the 60-per-hour anonymous API limit; private repos fall back to the developer's own gh login."""
    base = 'https://github.com/%s/releases' % repo
    status = None
    try:
        man = json.loads(_http('%s/latest/download/%s' % (base, MANIFEST), MAX_MANIFEST))
        version = str(man.get('version') or '')
        if not VERSION_RE.match(version):
            raise UpdateError('출시본의 판 번호가 이상합니다')
        tag = 'v' + version
        return {'tag_name': tag, '_via': 'web', 'html_url': '%s/tag/%s' % (base, tag),
                'assets': [{'name': MANIFEST, 'browser_download_url': '%s/download/%s/%s' % (base, tag, MANIFEST)},
                           {'name': ASSET, 'browser_download_url': '%s/download/%s/%s' % (base, tag, ASSET)}]}
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError('인터넷에 연결하지 못했습니다 (%s)' % str(getattr(exc, 'reason', exc))[:120])
    gh = _gh()
    if gh:                                   # private repository: read it with the developer's own gh login
        r = run([gh, 'api', 'repos/%s/releases/latest' % repo], capture_output=True, text=True, timeout=60,
                stdin=subprocess.DEVNULL)
        if r.returncode == 0:
            rel = json.loads(r.stdout)
            rel['_via'] = 'gh'
            return rel
    if status == 404:
        raise UpdateError('업데이트 저장소에 출시된 판이 없습니다 (%s). 저장소가 아직 없거나, 비공개인데 gh 로그인이 안 돼 있습니다' % repo)
    raise UpdateError('GitHub가 응답하지 않습니다 (HTTP %s). 잠시 뒤 다시 확인하세요' % status)


def fetch_asset(rel: Dict[str, Any], name: str, dest: Path, limit: int, repo: str,
                run: Callable = subprocess.run) -> Path:
    asset = next((a for a in rel.get('assets') or [] if a.get('name') == name), None)
    if not asset:
        raise UpdateError('출시본에 %s 파일이 없습니다' % name)
    if int(asset.get('size') or 0) > limit:  # web-path assets carry no size; _http enforces the limit while reading
        raise UpdateError('%s 파일이 너무 큽니다' % name)
    target = dest / name
    if rel.get('_via') == 'gh' and _gh():
        r = run([_gh(), 'release', 'download', rel.get('tag_name', ''), '-R', repo, '-p', name, '-D', str(dest),
                 '--clobber'], capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise UpdateError('출시 파일을 받지 못했습니다: ' + (r.stderr or '').strip()[:200])
        if target.stat().st_size > limit:
            raise UpdateError('받는 파일이 서명된 크기보다 큽니다 — 중단')
        return target
    _http(asset['browser_download_url'], limit, dest=target, accept='application/octet-stream')
    return target


# ---------------------------------------------------------------- state machine
class Updater:
    def __init__(self, run: Callable = subprocess.run, keys: Optional[Dict[str, str]] = None,
                 spawn: Callable = subprocess.Popen, bundle: Optional[str] = None):
        self.run, self.keys, self.spawn = run, keys, spawn
        self.bundle = bundle if bundle is not None else os.environ.get('AI_DEV_DIRECTOR_BUNDLE', '')
        self.lock = threading.Lock()
        self.state: Dict[str, Any] = {'state': 'idle'}
        self._load()

    # persisted so a restarted engine still shows the last check and the result of an install
    def _status_file(self) -> Path:
        return updates_dir() / 'status.json'

    def _load(self):
        try:
            s = json.loads(self._status_file().read_text(encoding='utf-8'))
            if isinstance(s, dict):
                if s.get('state') in ('checking', 'downloading', 'installing'):
                    s['state'] = 'idle'
                if (s.get('latest') or {}).get('version') and cmp_version(s['latest']['version'], current_version()) <= 0:
                    s = {'state': 'up_to_date', 'checked_at': s.get('checked_at')}
                self.state = s
        except (OSError, ValueError):
            pass
        try:
            last = json.loads((updates_dir() / 'last_install.json').read_text(encoding='utf-8'))
            self.state['last_install'] = last
        except (OSError, ValueError):
            pass

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)
            snap = dict(self.state)
        try:
            self._status_file().write_text(json.dumps(snap, ensure_ascii=False), encoding='utf-8')
        except OSError:
            pass

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            s = dict(self.state)
        s.update(current=current_version(), settings=load_settings(), install_supported=self.can_install(),
                 signers=[{'name': n, 'fingerprint': key_fingerprint(k)} for n, k in (self.keys or TRUSTED_KEYS).items()])
        return s

    def can_install(self) -> bool:
        return bool(self.bundle) and self.bundle.endswith('.app') and Path(self.bundle).is_dir()

    def busy(self) -> bool:
        return self.state.get('state') in ('checking', 'downloading', 'installing')

    # -- check
    def check(self) -> Dict[str, Any]:
        if self.busy():
            return self.snapshot()
        self._set(state='checking', error='')
        repo = load_settings()['update_repo']
        try:
            rel = latest_release(repo, self.run)
            with tempfile.TemporaryDirectory() as tmp:
                path = fetch_asset(rel, MANIFEST, Path(tmp), MAX_MANIFEST, repo, self.run)
                entry = json.loads(path.read_text(encoding='utf-8'))
            signer = verify_entry(entry, self.keys)
            latest = {'version': entry['version'], 'signer': signer, 'notes': str(entry.get('notes') or '')[:4000],
                      'published_at': str(entry.get('published_at') or rel.get('published_at') or ''),
                      'size': entry['size'], 'sha256': entry['sha256'], 'tag': rel.get('tag_name', ''),
                      'url': rel.get('html_url', '')}
            newer = cmp_version(entry['version'], current_version()) > 0
            self._set(state='available' if newer else 'up_to_date', latest=latest if newer else None,
                      checked_at=_now(), repo=repo, entry=entry if newer else None, error='')
        except (UpdateError, ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
            self._set(state='error', error=str(exc)[:400], checked_at=_now(), repo=repo)
        return self.snapshot()

    # -- download + stage (verifies everything the signature covers)
    def stage(self) -> Path:
        entry = self.state.get('entry')
        if self.state.get('state') not in ('available', 'error', 'downloading') or not entry:
            raise UpdateError('먼저 업데이트를 확인하세요')
        signer = verify_entry(entry, self.keys)
        version = entry['version']
        if cmp_version(version, current_version()) <= 0:
            raise UpdateError('지금 판보다 새 판이 아닙니다')
        self._set(state='downloading', error='')
        repo = load_settings()['update_repo']
        target = updates_dir() / version
        if target.exists():
            shutil.move(str(target), str(updates_dir() / ('%s-old-%d' % (version, int(time.time())))))
        target.mkdir(mode=0o700)
        rel = latest_release(repo, self.run)
        if rel.get('tag_name') != self.state.get('latest', {}).get('tag'):
            raise UpdateError('확인한 뒤 새 출시가 또 올라왔습니다. 다시 확인하세요')
        dmg = fetch_asset(rel, ASSET, target, entry['size'], repo, self.run)
        if dmg.stat().st_size != entry['size'] or _sha256(dmg) != entry['sha256']:
            raise UpdateError('받은 파일이 서명된 파일과 다릅니다 — 설치 안 함')
        mount = target / 'mnt'
        mount.mkdir()
        r = self.run(['/usr/bin/hdiutil', 'attach', '-nobrowse', '-readonly', '-noautoopen', '-mountpoint', str(mount),
                      str(dmg)], capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        if r.returncode != 0:
            raise UpdateError('설치 파일을 열지 못했습니다: ' + (r.stderr or '').strip()[:200])
        try:
            src = mount / APP_NAME
            info = plistlib.loads((src / 'Contents' / 'Info.plist').read_bytes())
            if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleShortVersionString') != version:
                raise UpdateError('설치 파일 안의 앱이 서명된 판과 다릅니다 — 설치 안 함')
            staged = target / APP_NAME
            r = self.run(['/usr/bin/ditto', str(src), str(staged)], capture_output=True, text=True, timeout=300,
                         stdin=subprocess.DEVNULL)
            if r.returncode != 0:
                raise UpdateError('새 앱을 준비하지 못했습니다: ' + (r.stderr or '').strip()[:200])
        finally:
            self.run(['/usr/bin/hdiutil', 'detach', str(mount), '-quiet'], capture_output=True, timeout=120,
                     stdin=subprocess.DEVNULL)
        shutil.move(str(dmg), str(target / ('downloaded-' + ASSET)))
        self._set(state='ready', staged=str(staged), staged_version=version, staged_signer=signer)
        return staged

    # -- swap and restart (detached script; this process is stopped by it)
    def install(self) -> Dict[str, Any]:
        if not self.can_install():
            raise UpdateError('개발용으로 실행 중이라 앱을 바꿀 수 없습니다 (설치된 앱에서만 됨)')
        staged = Path(self.state.get('staged') or '')
        if self.state.get('state') != 'ready' or not (staged / 'Contents' / 'Info.plist').is_file():
            raise UpdateError('준비된 업데이트가 없습니다')
        info = plistlib.loads((staged / 'Contents' / 'Info.plist').read_bytes())
        if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleShortVersionString') != self.state.get('staged_version'):
            raise UpdateError('준비된 앱이 확인한 판과 다릅니다 — 설치 안 함')
        script = updates_dir() / 'swap.sh'
        script.write_text(SWAP_SCRIPT, encoding='utf-8')
        os.chmod(script, 0o700)
        old_dir = updates_dir() / 'old-apps'
        old_dir.mkdir(exist_ok=True)
        backup = old_dir / ('AI Dev Director %s %s.app' % (current_version(), time.strftime('%y%m%d_%H%M%S')))
        log = (updates_dir() / 'install.log').open('a')
        self._set(state='installing')
        self.spawn(['/bin/bash', str(script), self.bundle, str(staged), str(backup),
                    str(updates_dir() / 'last_install.json'), self.state.get('staged_version', ''), current_version()],
                   stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, close_fds=True)
        return self.snapshot()

    def apply(self):
        """One click: download, verify, stage, then swap. Runs in a thread; the UI polls snapshot()."""
        try:
            if self.state.get('state') != 'ready':
                self.stage()
            self.install()
        except (UpdateError, ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
            self._set(state='error', error=str(exc)[:400])


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _now() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S')


SWAP_SCRIPT = r'''#!/bin/bash
# AI Dev Director update swap: stop the app, put the new bundle in place, open it. Never deletes anything.
set -u
APP="$1"; NEW="$2"; BACKUP="$3"; RESULT="$4"; NEWV="$5"; OLDV="$6"
say() { printf '%s %s\n' "$(date '+%F %T')" "$1"; }
result() { printf '{"ok": %s, "version": "%s", "from": "%s", "at": "%s", "message": "%s"}\n' "$1" "$NEWV" "$OLDV" "$(date '+%Y-%m-%dT%H:%M:%S')" "$2" > "$RESULT"; }
say "update $OLDV -> $NEWV"
sleep 1
pkill -INT -f "Contents/Resources/mac_bootstrap.py"
for i in $(seq 1 40); do curl -s -m 1 http://127.0.0.1:8081/health >/dev/null 2>&1 || break; sleep 0.5; done
pkill -INT -f "companion_server.py"
sleep 1
pkill -x "AI Dev Director"
for i in $(seq 1 40); do pgrep -x "AI Dev Director" >/dev/null || break; sleep 0.5; done
PARENT="$(dirname "$APP")"
STAGE="$PARENT/.AI Dev Director.update.app"
if [ -e "$STAGE" ]; then mv "$STAGE" "$BACKUP.partial"; fi
if ! ditto "$NEW" "$STAGE"; then
  say "copy failed"; result false "새 앱을 복사하지 못했습니다"; open "$APP"; exit 1
fi
if ! mv "$APP" "$BACKUP"; then
  say "move old failed"; mv "$STAGE" "$BACKUP.unused"; result false "기존 앱을 옮기지 못했습니다"; open "$APP"; exit 1
fi
if ! mv "$STAGE" "$APP"; then
  say "move new failed, restoring"; mv "$BACKUP" "$APP"; result false "새 앱을 넣지 못해 원래 앱으로 되돌렸습니다"; open "$APP"; exit 1
fi
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null
result true "업데이트했습니다"
say "done"
open "$APP"
'''


_UPDATER: Optional[Updater] = None
_GUARD = threading.Lock()


def updater() -> Updater:
    global _UPDATER
    with _GUARD:
        if _UPDATER is None:
            _UPDATER = Updater()
        return _UPDATER


def start_auto_check(first_delay: float = 10.0):
    def loop():
        time.sleep(first_delay)
        while True:
            try:
                if load_settings()['auto_check']:
                    updater().check()
            except Exception:
                pass
            time.sleep(CHECK_EVERY)
    threading.Thread(target=loop, name='update-auto-check', daemon=True).start()
