import pytest
"""v4 RUN&SEE: verdict parsing and the fail-closed screen gate (no CLI, no browser)."""
from core import vision_qa as v


def _report(*kinds):
    return {'ok': True, 'pages': [{'path': '/', 'size': '1440x900', 'screenshot': '/x.png',
                                   'defects': [{'kind': k, 'count': 1, 'items': []} for k in kinds]}]}


def test_parse_verdict_takes_last_valid_json_block():
    text = 'noise ```json\n{"verdict":"maybe"}\n``` more ```json\n{"verdict":"pass","score":90,"problems":[],"summary":"ok"}\n```'
    assert v.parse_verdict(text)['verdict'] == 'pass'
    assert v.parse_verdict('no json here') is None
    assert v.parse_verdict('```json\n{"verdict":"pass"}\n```') is None      # missing keys -> not a verdict


def test_gate_is_fail_closed():
    good = {'verdict': 'pass', 'score': 90, 'problems': [], 'summary': 'ok'}
    assert v.screen_gate(_report(), good)['passed'] is True
    assert v.screen_gate(_report(), None)['passed'] is False
    assert v.screen_gate({'ok': False, 'error': 'x'}, good)['passed'] is False
    assert v.screen_gate(_report('overlap'), good)['passed'] is False
    assert v.screen_gate(_report('small_text'), good)['passed'] is False
    assert v.screen_gate(_report(), dict(good, verdict='fail'))['passed'] is False
    assert v.screen_gate(_report(), dict(good, verdict='pass_with_notes'))['passed'] is True


def test_judge_without_screens_or_cli_fails(tmp_path, monkeypatch):
    assert v.judge('goal', {'ok': True, 'pages': []}, str(tmp_path))['verdict'] == 'fail'
    shot = tmp_path / 'a.png'; shot.write_bytes(b'png')
    monkeypatch.setattr(v, 'resolve_cli', lambda name: None)
    rep = {'ok': True, 'pages': [{'screenshot': str(shot), 'defects': []}]}
    assert v.judge('goal', rep, str(tmp_path))['verdict'] == 'fail'


def test_judge_prompt_carries_taste_and_measurements():
    prompt = v.judge_prompt('축구 회비 앱', _report('overlap'), ['/x/home_1440x900.png'])
    assert 'overlap' in prompt and 'home_1440x900.png' in prompt and '"verdict"' in prompt
    assert '마침표' in prompt      # taste/design_rules.md is injected


def test_measure_rejects_missing_node(monkeypatch, tmp_path):
    monkeypatch.setattr(v.shutil, 'which', lambda name: None)
    assert v.measure('http://127.0.0.1:1/', str(tmp_path))['ok'] is False


def _chrome():
    import os
    return any(os.path.exists(p) for p in ('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome'))


@pytest.mark.skipif(not _chrome(), reason='needs Chrome')
def test_fixed_bar_overlap_only_when_content_stays_hidden(tmp_path):
    from pathlib import Path
    from core.static_serve import serve
    from core import vision_qa
    folder = Path(__file__).parent / 'fixtures' / 'see'
    with serve(folder) as url:
        r = vision_qa.measure(url, str(tmp_path), paths=['/bad.html', '/ok.html'], sizes='390x500', wait_ms=400)
    kinds = {p['path']: [d for d in p['defects'] if d['kind'] == 'overlap'] for p in r['pages']}
    texts = ' '.join(i['bt'] for d in kinds['/bad.html'] for i in d['items'])
    assert '겹친 버튼' in texts and '끝까지 내려도 가려짐' in texts
    assert kinds['/ok.html'] == []
