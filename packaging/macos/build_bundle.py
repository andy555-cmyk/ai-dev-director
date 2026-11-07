"""Build the script-based Mac app. Native UDZO on macOS; preview hybrid elsewhere."""
from pathlib import Path
import hashlib
import json
import plistlib
import shutil
import subprocess
import sys
import zipfile

VERSION = '0.4.1'
root = Path(__file__).resolve().parents[2]
out = root.parent / 'macos-release'
volume = out / 'volume'
if volume.exists():
    shutil.rmtree(volume)
app = volume / 'AI Dev Director.app'
contents = app / 'Contents'
resources = contents / 'Resources'
(contents / 'MacOS').mkdir(parents=True)
resources.mkdir()
# 0.4.1: the app is a native window (AppKit + WKWebView), not a script that opens a browser tab. Universal binary.
EXE = 'AI Dev Director'
_tmp = out / '_shell'
_tmp.mkdir(parents=True, exist_ok=True)
_slices = []
for arch in ('arm64', 'x86_64'):
    target = _tmp / arch
    subprocess.run(['swiftc', '-O', '-target', arch + '-apple-macos12', str(root / 'packaging/macos/AppShell.swift'),
                    '-o', str(target)], check=True)
    _slices.append(str(target))
subprocess.run(['lipo', '-create', *_slices, '-output', str(contents / 'MacOS' / EXE)], check=True)
shutil.rmtree(_tmp)
shutil.copy2(root / 'packaging/macos/AppIcon.icns', resources / 'AppIcon.icns')
for name in ('start.command', 'mac_bootstrap.py', 'install_support.py'):
    shutil.copy2(root / 'packaging/macos' / name, resources / name)
(resources / 'start.command').chmod(0o755)
engine = resources / 'engine'
engine.mkdir()
for name in ('agents', 'console', 'core', 'schemas', 'scripts', 'templates', 'taste'):
    shutil.copytree(root / name, engine / name,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for name in ('director.py','companion_server.py','dashboard_server.py','dashboard_i18n.py',
             'config.yaml','companion.json','requirements.txt','LICENSE','README.md'):
    shutil.copy2(root / name, engine / name)
(engine / 'data').mkdir()
# Same-version rebuilds must still replace the installed engine: the installer compares this id too.
import uuid as _uuid
(engine / '.source-build-id').write_text(_uuid.uuid4().hex)
with (contents / 'Info.plist').open('wb') as f:
    plistlib.dump({'CFBundleName':'AI Dev Director', 'CFBundleDisplayName':'AI Dev Director',
        'CFBundleIdentifier':'local.aidevdirector.macpreview','CFBundleVersion':VERSION,
        'CFBundleShortVersionString':VERSION,'CFBundlePackageType':'APPL',
        'CFBundleExecutable':EXE,'LSMinimumSystemVersion':'12.0','CFBundleIconFile':'AppIcon',
        'NSPrincipalClass':'NSApplication','LSApplicationCategoryType':'public.app-category.developer-tools',
        'NSHighResolutionCapable':True}, f)
(contents / 'PkgInfo').write_bytes(b'APPL????')
# Ad-hoc signature over the whole bundle (Apple Silicon refuses unsigned or half-signed bundles).
subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True)
readme = '''AI DEV DIRECTOR · macOS Preview 0.4.1

설치 / 업데이트
1. AI Dev Director.app을 응용 프로그램(Applications) 폴더로 복사합니다.
2. 이전 버전을 실행 중이면 시스템 중지 후 새 앱으로 교체합니다.
3. 앱을 실행하면 앱 자체 창이 뜨고, 엔진이 준비되면 그 창에 HUD 화면이 나옵니다(첫 실행은 1~2분). 브라우저는 열리지 않습니다.
4. 연결 진단에서 Python, Git, AI CLI 설치 및 구독 로그인을 확인합니다.
5. 작업 화면으로 돌아가 프로젝트 폴더와 역할을 선택합니다.
6. 종료는 ⌘Q(AI Dev Director 끝내기)입니다. 진행 중이던 작업은 다음에 켤 때 이어서 합니다. 창만 닫으면 작업은 계속되고, Dock 아이콘을 누르면 다시 열립니다.

0.4.1 변경 사항 (진짜 맥 프로그램)
- 앱을 누르면 크롬 탭이 아니라 앱 자체 창이 뜸. Dock 아이콘·메뉴(복사·붙여넣기·확대·새로 고침)·⌘Q 종료
- Finder에서 눌렀을 때 아무것도 안 뜨던 문제 수정(실행 스크립트가 앱과 함께 꺼지던 것)
- 엔진이 켜지는 동안 창에 진행 화면, 실패하면 이유와 기록 위치 표시
- 바깥 링크는 기본 브라우저로, 내려받기는 저장 창으로
- macOS 12 이상

0.4.0 변경 사항 (한 줄로 앱 만들기)
- 상단 「앱 만들기」: 만들 앱 한 줄과 폴더만 적으면 기획 → 구현 → 실제 화면 확인 → 수정 → 출시 묶음까지 진행
- 대표 확인은 세 번: 기획(와이어프레임 그림·기획 문서 4종), 중간 화면, 출시
- 작업마다 실제로 켜 보고 PC·휴대전화 크기로 캡처, 겹침·잘림·작은 글자·콘솔 오류를 재고 Codex가 그림을 보고 판정. 불합격이면 스스로 두 번까지 고침
- 남긴 의견은 쌓여서 다음 기획·구현·판정에 반영(업데이트해도 남음)
- 명령줄: director.py deliver start / status / approve / feedback
- 콘솔 서버 동시 접속 한도를 늘려 아이콘이 끊기던 문제 수정, HUD 작은 글자 11~12px로

0.3.7 변경 사항 (헤이데이 맥 보완)
- 터미널 창 없이 실행. 로그인 셸의 PATH를 읽어 npm·Homebrew로 깐 CLI도 Finder 실행에서 찾음
- 실행 실패는 알림 창과 launcher.log로 안내
- Claude 장기 토큰(claude setup-token) 로그인을 구독 로그인으로 인정
- Grok 로그인을 자동 판정(grok models, 생성 호출 없음)
- 설치 안 된 AI 자리는 실제 대신 맡는 AI로 HUD·진단에 표시(예: Antigravity 없음 → 구현 Codex, 검수 Claude)
- Grok 호출 때 Claude·Cursor 설정(MCP 서버, 훅, CLAUDE.md, 규칙, 스킬)을 끄고 실행. 예전에는 사용자의 MCP 서버가 전부 같이 켜졌음
- 왼쪽 패널: 작업 폴더 칸이 짜부라져 보이지 않던 문제, 진행 문구가 작업 시작 버튼을 덮던 문제 수정
- 9~11px 글자를 11~12px로 키움

0.3.6 변경 사항
- Grok을 계획·구현·테스트 검수·최종 판단과 자동 보완의 전체 흐름에 연동
- 단계별 분석·보완 제안·미확인 증거를 Builder/Reviewer/HEAD와 다음 미션 계획에 전달
- 단계 기록·중복 실행 방지·중단/재시작·취소·CLI 호출 기록과 provenance 지원
- HUD Grok 패널에 단계별 실제 완료/실패와 보완 차수 표시, 다시보기 연계
- 구독 CLI만 사용, 단계 분석은 제공된 요구사항·검증 요약만 사용하고 도구/파일 쓰기 금지
- macOS 공백 Python 경로·빠른 보완 시 이전 바이트코드 재사용·터미널 종료 후 서버 응답 문제 수정

0.3.5 변경 사항
- 네 AI에 7갈래 발광 회로 라인, 이동 광점과 접점 렌즈 플레어 추가
- 중앙 코어에 시안·보라색 광륜, 구면 회로 패턴과 TRINITY 표식
- 다층 파동과 하단 투영 링, 패널 라인의 조명 효과
- 실제 작업 시 속도·밝기 강화, 모션 끄기/동작 줄이기와 WebGL/2D 지원
- 입자 12.5만 개 미만·렌더 버퍼 약 3.4MP 상한으로 효과 비용 제한

0.3.4 변경 사항
- HUD AI 연결에 연결됨·연결 안됨·확인 필요 배지, 상세 사유와 확인 시각 표시
- HUD 연결 상태 다시 점검 버튼, 자동 초기 점검 및 30초 상태 갱신
- CLI 실행/구독 로그인 또는 최근 10분의 실제 응답 기록을 근거로 상태 판정
- 미설치·미로그인·CLI 실행 실패·API 인증을 구분하고 점검 실패 시 이전 정상 표시 해제
- 재점검은 설치·로그인 명령만 사용하며 AI 생성 호출이나 계정 변경을 하지 않음

0.3.3 변경 사항
- Grok HUD 입자 구체와 중앙 코어 연결선, 분석 상태에 따른 색·흐름 동기화
- Grok 카드를 구체 위치에 고정, WebGL2 및 2D 대체 화면과 모션 끄기 지원
- HUD 우측 상단에 Grok 보조 분석·리서치 전용 카드와 결과 창
- 공식 Grok CLI 로그인, 웹 자료 분석 요청·취소·결과 저장
- 질문만 전송하며 웹 도구만 허용, 프로젝트 파일 읽기·쓰기와 MCP·하위 에이전트 제외

0.3.1에서 이어지는 로그인 기능
- Claude Code·Codex·Antigravity 계정 로그인 버튼과 로그인 후 연결 재확인
- 공식 CLI 로그인 창 사용. 앱에서 아이디·비밀번호·인증 코드를 받거나 저장하지 않음
- 계정을 자동 로그아웃하거나 다른 계정으로 바꾸지 않음

0.3.0에서 이어지는 화면 구성
- 자비스 스타일의 입체형 HUD 메인 화면: 중앙 코어, 세 AI 궤도, 투명 패널
- WebGL2 gyroscope 렌더링 + WebGL 미지원 시 입체 코어/궤도 대체 렌더링
- 왼쪽 작업 입력, 오른쪽 실시간 검증 및 연결 상태, 하단 5단계 파이프라인
- 역할 카드 클릭/키보드 Enter로 역할 변경, 모션 켜기/끄기
- 전송 거절·오류 시 작성한 지시 보존, 상태 갱신 중에도 오류 안내 유지
- 진단 화면 색상 통일, 좁은 화면에서 세로 배치 지원

이전 버전에서 유지한 기능
- 설치·연결 진단 화면 /setup, 공식 설치·로그인 안내, JSON 진단 보고서 저장
- Claude·Codex의 구독 로그인과 API 인증을 구분. Antigravity 로그인은 직접 확인
- 진단에 API 키·계정 이메일·프로젝트 코드·경로·CLI 원문 출력을 포함하지 않음
- 불완전한 최종 검증 증거를 통과로 표시하지 않도록 수정
- 업데이트 전에 이전 코드와 설정을 backups에 보관, 데이터는 공용 폴더로 보존
- 의존성 목록이 바뀔 때 재설치, 실제 서버 상태 확인 후 진단 화면 열기
- macOS에서는 Windows taskkill을 호출하지 않고 프로세스 트리를 정리

필수 조건
- Python 3.9 이상: https://www.python.org/downloads/macos/
- Git (필요하면 터미널에서 xcode-select --install)
- claude, codex, agy 중 최소 두 CLI 설치 및 해당 서비스의 로그인
- 첫 실행 때 의존성 다운로드를 위한 인터넷 연결
Python과 AI CLI는 포함돼 있지 않습니다. 구독료는 별도입니다.
CLI 경로가 인식되지 않으면 engine/config.yaml의 executable에 절대 경로를 지정하세요.
진단 화면의 정상 표시는 설치·구독 로그인 확인이며 실제 AI 생성 성공이나 요금 검증이 아닙니다.

데이터와 설정
~/Library/Application Support/AI Dev Director/
설정: engine/config.yaml
실행 기록: data/, runs/, research/ (engine 내부에서는 이 위치로 연결)
이전 코드와 설정: backups/engine-날짜/
backups는 데이터베이스 시점 복원본이 아닙니다. 실행 기록은 업데이트 전후 공유됩니다.
감독관 Python 환경: venv/
기본 화면: http://127.0.0.1:8081
진단 화면: http://127.0.0.1:8081/setup

프리뷰 상태
Windows 원본을 바탕으로 만든 비공식 macOS 포트입니다.
Apple Silicon과 Intel을 위한 스크립트 실행기이며, 설치된 Python과 CLI가 해당 Mac과 호환돼야 합니다.
macOS에서 앱 서버·HUD·연결 진단을 확인하고, 격리 예제에서 네 구독 CLI와 Grok 네 단계 및 테스트 4개 통과를 확인했습니다.
실제 사용자 프로젝트별 결과와 신규 계정 로그인 완료는 별도로 확인해야 합니다.
Apple 개발자 서명과 공증이 없습니다.
macOS가 차단하면 시스템 설정 > 개인정보 보호 및 보안에서 메시지를 확인하세요.
이 버전은 macOS hdiutil로 생성한 표준 UDZO 디스크 이미지입니다.
macOS에서 동봉 Source_Code.zip을 풀고 Python으로 packaging/macos/build_bundle.py를 실행하면
hdiutil을 사용해 표준 UDZO DMG를 다시 생성합니다.

검사 내역: RELEASE_NOTES.txt 참고
원본: https://github.com/digilogd-cmd/ai-dev-director
원본 커밋: a463e7886666794101f6a6c7542abdcf9c9b6c0b
MIT 라이선스: 앱 Contents/Resources/engine/LICENSE
'''
(volume / 'READ_ME_KO.txt').write_text(readme, encoding='utf-8')
(volume / 'LICENSE.txt').write_text((root / 'LICENSE').read_text())
notes = root / 'packaging/macos/RELEASE_NOTES.txt'
if notes.exists():
    shutil.copy2(notes, volume / 'RELEASE_NOTES.txt')
# Include auditable source and tests, without repository metadata or runtime state.
if (root / '.git').exists():
    files = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'], cwd=root).decode().split('\0')
else:
    files = [str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()
             and not any(part in ('__pycache__','.git','data','runs','research','.pytest_cache') for part in p.relative_to(root).parts)]
with zipfile.ZipFile(volume / 'Source_Code.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for rel in sorted(set(files)):
        if rel and (root / rel).is_file() and rel not in ("docs/design/hud-comparison.jpg", "docs/design/hud-core-comparison.jpg"):
            archive.write(root / rel, 'ai-dev-director/' + rel)
build_info = {'upstream_commit':'a463e7886666794101f6a6c7542abdcf9c9b6c0b','hayday_mac_patch':VERSION,
              'version':VERSION,'macos_runtime_tested':True,'login_credential_flow_tested':False,'related_tests_passed':688,'known_failing_upstream':['test_v014_qualification::test_a2_permission_guard_hook_blocks_escapes'],'connection_badges_tested':True,'circuit_hud_tested':True,'grok_full_pipeline_tested':True,'real_four_cli_pipeline_passed':True,'grok_hud_regression_tested':True,'grok_cli_response_tested':True,'grok_web_research_tested':True,'signed':False,'python_bundled':False}
(volume / 'BUILD_INFO.json').write_text(json.dumps(build_info, indent=2))
dmg = out / 'AI_Dev_Director_macOS_Preview.dmg'
if sys.platform == 'darwin':
    subprocess.run(['hdiutil','create','-volname','AI Dev Director','-srcfolder',str(volume),
                    '-ov','-format','UDZO',str(dmg)], check=True)
else:
    tool = shutil.which('genisoimage')
    fallback = Path('/tmp/director-build-tools/root/usr/bin/genisoimage')
    if not tool and fallback.exists():
        tool = str(fallback)
    if not tool:
        raise SystemExit('App bundle created. DMG creation requires macOS hdiutil or Linux genisoimage.')
    subprocess.run([tool,'-quiet','-R','-J','-hfs','-V','AI_DEV_DIRECTOR','-hfs-volid',
                    'AI Dev Director','-o',str(dmg),str(volume)], check=True)
(out / 'SHA256SUMS.txt').write_text(hashlib.sha256(dmg.read_bytes()).hexdigest()+'  '+dmg.name+'\n')
print(dmg)
