"""0.4.3 in-app updater: Ed25519 signing, trusted keys, settings, check / stage / install guards (no network)."""
import base64
import hashlib
import json
import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import ed25519, updater as up


# RFC 8032 section 7.1, tests 1 and 2
RFC = [
    ('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60',
     'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
     'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
    ('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb',
     '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
     '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'),
]


@pytest.mark.parametrize('sk,pk,msg,sig', RFC)
def test_ed25519_matches_rfc8032(sk, pk, msg, sig):
    sk, pk, msg, sig = (bytes.fromhex(x) for x in (sk, pk, msg, sig))
    assert ed25519.public_key(sk) == pk
    assert ed25519.sign(sk, msg) == sig
    assert ed25519.verify(pk, msg, sig)
    assert not ed25519.verify(pk, msg + b'x', sig)


SECRET = bytes(range(32))
PUB = base64.b64encode(ed25519.public_key(SECRET)).decode()
KEYS = {'시험': PUB}


def entry(version='9.9.9', size=10, sha='ab' * 32, **extra):
    e = {'app': up.APP, 'platform': up.PLATFORM, 'version': version, 'file': up.ASSET, 'size': size, 'sha256': sha,
         'notes': '시험 판'}
    e.update(extra)
    return up.sign_entry(e, SECRET, '시험')


def test_signed_entry_verifies_and_names_signer():
    assert up.verify_entry(entry(), KEYS) == '시험'


def test_untrusted_tampered_or_wrong_file_is_rejected():
    with pytest.raises(up.UpdateError):
        up.verify_entry(entry(), {'남': base64.b64encode(ed25519.public_key(bytes(32))).decode()})
    bad = entry()
    bad['sha256'] = 'cd' * 32
    with pytest.raises(up.UpdateError):
        up.verify_entry(bad, KEYS)
    bad = entry()
    bad['version'] = '10.0.0'
    with pytest.raises(up.UpdateError):
        up.verify_entry(bad, KEYS)
    with pytest.raises(up.UpdateError):
        up.verify_entry(entry(file='other.dmg'), KEYS)


def test_shipped_trusted_key_is_well_formed():
    assert up.TRUSTED_KEYS
    for name, key in up.TRUSTED_KEYS.items():
        assert name and len(base64.b64decode(key)) == 32


def test_settings_validate_repo_and_bool():
    assert up.load_settings()['update_repo'] == up.DEFAULT_REPO
    s = up.save_settings({'update_repo': 'https://github.com/someone/thing', 'auto_check': False})
    assert s['update_repo'] == 'someone/thing' and s['auto_check'] is False
    with pytest.raises(ValueError):
        up.save_settings({'update_repo': '../../etc'})
    with pytest.raises(ValueError):
        up.save_settings({'auto_check': 'yes'})
    assert up.load_settings()['update_repo'] == 'someone/thing'


def test_version_compare():
    assert up.cmp_version('0.4.10', '0.4.9') > 0
    assert up.cmp_version('0.4.3', '0.4.3') == 0
    assert up.cmp_version('0.4.2', '0.4.3') < 0


def fake_release(monkeypatch, man, dmg_bytes=b''):
    rel = {'tag_name': 'v' + man['version'], 'assets': [{'name': up.MANIFEST}, {'name': up.ASSET}], 'html_url': 'u'}
    monkeypatch.setattr(up, 'latest_release', lambda repo, run=None: rel)

    def fetch(rel, name, dest, limit, repo, run=None):
        p = Path(dest) / name
        p.write_bytes(json.dumps(man).encode() if name == up.MANIFEST else dmg_bytes)
        return p
    monkeypatch.setattr(up, 'fetch_asset', fetch)


def test_check_finds_newer_signed_release(monkeypatch):
    fake_release(monkeypatch, entry('9.9.9'))
    u = up.Updater(keys=KEYS, bundle='')
    s = u.check()
    assert s['state'] == 'available' and s['latest']['version'] == '9.9.9' and s['latest']['signer'] == '시험'
    assert s['install_supported'] is False


def test_check_same_version_is_up_to_date(monkeypatch):
    fake_release(monkeypatch, entry(up.current_version()))
    assert up.Updater(keys=KEYS, bundle='').check()['state'] == 'up_to_date'


def test_check_rejects_unsigned_manifest(monkeypatch):
    man = entry('9.9.9')
    man['sig'] = base64.b64encode(bytes(64)).decode()
    fake_release(monkeypatch, man)
    s = up.Updater(keys=KEYS, bundle='').check()
    assert s['state'] == 'error' and not s.get('entry')


def test_stage_rejects_download_that_differs_from_signature(monkeypatch):
    body = b'real dmg bytes'
    man = entry('9.9.9', size=len(body), sha=hashlib.sha256(b'something else').hexdigest())
    fake_release(monkeypatch, man, body)
    calls = []
    u = up.Updater(keys=KEYS, bundle='', run=lambda *a, **k: calls.append(a) or SimpleNamespace(returncode=0, stderr=''))
    u.check()
    with pytest.raises(up.UpdateError):
        u.stage()
    assert not any('hdiutil' in str(c) for c in calls), 'must not mount an unverified file'


def test_stage_checks_bundle_id_inside_dmg(monkeypatch, tmp_path):
    body = b'dmg'
    man = entry('9.9.9', size=len(body), sha=hashlib.sha256(body).hexdigest())
    fake_release(monkeypatch, man, body)

    def run(cmd, **k):
        if 'attach' in cmd:
            mnt = Path(cmd[cmd.index('-mountpoint') + 1])
            info = mnt / up.APP_NAME / 'Contents'
            info.mkdir(parents=True)
            (info / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'evil.app',
                                                              'CFBundleShortVersionString': '9.9.9'}))
        return SimpleNamespace(returncode=0, stderr='')
    u = up.Updater(keys=KEYS, bundle='', run=run)
    u.check()
    with pytest.raises(up.UpdateError):
        u.stage()


def test_install_refused_without_installed_bundle():
    u = up.Updater(keys=KEYS, bundle='')
    with pytest.raises(up.UpdateError):
        u.install()


def test_apply_end_to_end_spawns_swap_script(monkeypatch, tmp_path):
    body = b'dmg'
    man = entry('9.9.9', size=len(body), sha=hashlib.sha256(body).hexdigest())
    fake_release(monkeypatch, man, body)
    bundle = tmp_path / 'Applications' / up.APP_NAME
    bundle.mkdir(parents=True)

    def run(cmd, **k):
        if 'attach' in cmd:
            info = Path(cmd[cmd.index('-mountpoint') + 1]) / up.APP_NAME / 'Contents'
            info.mkdir(parents=True)
            (info / 'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': up.BUNDLE_ID,
                                                              'CFBundleShortVersionString': '9.9.9'}))
        if cmd[0] == '/usr/bin/ditto':
            import shutil
            shutil.copytree(cmd[1], cmd[2])
        return SimpleNamespace(returncode=0, stderr='')
    spawned = []
    u = up.Updater(keys=KEYS, bundle=str(bundle), run=run, spawn=lambda cmd, **k: spawned.append(cmd))
    u.check()
    u.apply()
    assert u.state['state'] == 'installing', u.state.get('error')
    cmd = spawned[0]
    assert cmd[2] == str(bundle) and cmd[6] == '9.9.9' and Path(cmd[1]).read_text().startswith('#!/bin/bash')
    assert 'rm -rf' not in up.SWAP_SCRIPT


def test_routes_exist_in_server():
    src = (Path(__file__).resolve().parents[1] / 'companion_server.py').read_text(encoding='utf-8')
    for route in ("'/ops/update'", "'/ops/update/check'", "'/ops/update/apply'", "'/ops/settings'", "'/settings.js'"):
        assert route in src


def test_latest_release_uses_download_links_not_rate_limited_api(monkeypatch):
    seen = []

    def http(url, limit, dest=None, accept=''):
        seen.append(url)
        return json.dumps({'version': '9.9.9'}).encode()
    monkeypatch.setattr(up, '_http', http)
    rel = up.latest_release('owner/repo')
    assert rel['tag_name'] == 'v9.9.9' and rel['_via'] == 'web'
    assert seen == ['https://github.com/owner/repo/releases/latest/download/' + up.MANIFEST]
    assert all('api.github.com' not in a['browser_download_url'] for a in rel['assets'])
    assert any(a['browser_download_url'].endswith('/download/v9.9.9/' + up.ASSET) for a in rel['assets'])


def test_missing_repo_gives_korean_reason(monkeypatch):
    import urllib.error

    def http(url, limit, dest=None, accept=''):
        raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
    monkeypatch.setattr(up, '_http', http)
    monkeypatch.setattr(up, '_gh', lambda: None)
    with pytest.raises(up.UpdateError, match='출시된 판이 없습니다'):
        up.latest_release('owner/none')


def _release_tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location('release_mac', Path(__file__).resolve().parents[1] / 'tools' / 'release_mac.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pushed_public_key_is_registered_but_cannot_replace_a_signer(monkeypatch, tmp_path):
    rm = _release_tool()
    (tmp_path / 'core').mkdir()
    src = (Path(__file__).resolve().parents[1] / 'core' / 'updater.py').read_text(encoding='utf-8')
    (tmp_path / 'core' / 'updater.py').write_text(src, encoding='utf-8')
    keys = tmp_path / 'release' / 'keys'
    keys.mkdir(parents=True)
    other = base64.b64encode(ed25519.public_key(bytes([7] * 32))).decode()
    (keys / '호진.pub').write_text(other + '\n')
    (keys / '이승원.pub').write_text(other + '\n')          # must not override the owner's key
    (keys / 'bad.pub').write_text('not-a-key\n')
    monkeypatch.setattr(rm, 'ROOT', tmp_path)
    monkeypatch.setattr(rm, 'KEYS_DIR', keys)
    monkeypatch.setattr(rm.U, 'TRUSTED_KEYS', dict(up.TRUSTED_KEYS))
    assert rm.register_pushed_keys() == ['호진']
    out = (tmp_path / 'core' / 'updater.py').read_text(encoding='utf-8')
    assert "'호진': '%s'" % other in out and out.count("'이승원':") == 1
    assert rm.register_pushed_keys() == []                     # idempotent


def test_next_version_bumps_patch_over_newest_tag(monkeypatch):
    rm = _release_tool()
    monkeypatch.setattr(rm, '_git', lambda *a, **k: SimpleNamespace(returncode=0, stdout='v0.4.3\nv0.4.10\n', stderr=''))
    assert rm.next_version() == '0.4.11'


def test_swap_script_escalates_and_frees_the_port():
    s = up.SWAP_SCRIPT
    assert 'for sig in INT TERM KILL' in s and 'lsof -ti tcp:8081' in s
    assert s.index('start.command') < s.index('for sig in INT TERM KILL')   # launcher first: no failure dialog
    assert 'rm -rf' not in s
