"""Versioned engine installation. Keep runtime data and user settings across upgrades."""
import json
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime, timezone

RUNTIME_DIRS = ('data', 'runs', 'research')
SETTINGS = ('config.yaml', 'companion.json', 'companion.local.json')


def install_engine(source, state, version):
    source, state = Path(source), Path(state)
    state.mkdir(parents=True, exist_ok=True)
    engine = state / 'engine'
    # Recover a previous code tree if a process died between the two atomic renames.
    if not engine.exists():
        backups = sorted((state / 'backups').glob('engine-*'))
        if backups:
            backups[-1].rename(engine)
    manifest = engine / '.desktop-build.json'
    build_id = (source / '.source-build-id').read_text().strip() if (source / '.source-build-id').is_file() else ''
    if manifest.exists():
        installed = json.loads(manifest.read_text())
        if installed.get('version') == version and installed.get('build', '') == build_id:
            return engine
    stage = Path(tempfile.mkdtemp(prefix='.engine-staging-', dir=state))
    backup = None
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True)
        # Stage the complete new code first; a copy failure leaves the old engine untouched.
        for name in SETTINGS:
            current = engine / name
            if current.exists():
                shutil.copy2(current, stage / name)
        for name in RUNTIME_DIRS:
            permanent, old = state / name, engine / name
            if not permanent.exists():
                if old.is_dir() and not old.is_symlink():
                    old.rename(permanent)
                    old.symlink_to(permanent, target_is_directory=True)
                else:
                    permanent.mkdir()
            elif old.exists() and not old.is_symlink():
                # Do not merge two different databases or run histories silently.
                if any(old.iterdir()):
                    raise RuntimeError('기존 실행 기록이 두 위치에 있습니다. 자동 업데이트를 중단합니다: ' + name)
            staged_dir = stage / name
            if staged_dir.exists():
                if staged_dir.is_dir() and not staged_dir.is_symlink():
                    shutil.rmtree(staged_dir)
                else:
                    staged_dir.unlink()
            staged_dir.symlink_to(permanent, target_is_directory=True)
        (stage / '.desktop-build.json').write_text(json.dumps({'version': version, 'build': build_id}))
        if engine.exists():
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backup = state / 'backups' / ('engine-' + stamp)
            backup.parent.mkdir(exist_ok=True)
            engine.rename(backup)
        try:
            stage.rename(engine)
        except BaseException:
            if backup is not None:
                backup.rename(engine)
            raise
        return engine
    finally:
        if stage.exists():
            shutil.rmtree(stage)
