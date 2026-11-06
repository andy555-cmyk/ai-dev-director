import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_native_picker_unicode_and_cancel(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location('mac_picker', Path(__file__).parents[1] / 'scripts/pick_folder.py')
    picker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(picker)
    monkeypatch.setattr(sys, 'platform', 'darwin')
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout='/Users/test/프로젝트\n'))
    monkeypatch.setattr('subprocess.run', runner)
    assert picker.main() == 0
    assert json.loads(capsys.readouterr().out)['path'] == '/Users/test/프로젝트'
    assert runner.call_args.args[0][0] == '/usr/bin/osascript'
    runner.return_value.stdout = '\n'
    assert picker.main() == 0
    assert json.loads(capsys.readouterr().out)['path'] == ''


def test_finder_open_uses_argv(monkeypatch):
    from core.result_manager import ResultManager
    monkeypatch.setattr(sys, 'platform', 'darwin')
    runner = Mock()
    monkeypatch.setattr('core.result_manager.subprocess.Popen', runner)
    path = '/Users/test/프로젝트 $(echo unsafe)'
    assert ResultManager._open(path)['status'] == 'ok'
    runner.assert_called_once_with(['/usr/bin/open', path])
