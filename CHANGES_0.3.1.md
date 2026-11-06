# 0.3.1 — CLI 계정 로그인

설치·연결 진단 카드에 계정 로그인과 연결 확인 버튼을 추가했습니다.
사용자 클릭 시 새 터미널에 고정된 공식 CLI 로그인 명령을 열고, 로그인은 사용자가 완료합니다.
인증 정보는 각 CLI가 관리하며 이 앱은 로그인 출력이나 인증 정보를 보관하지 않습니다.
기존 인증을 자동 로그아웃하지 않습니다. Antigravity는 CLI에서 상태를 직접 확인합니다.

공식 명령 확인: 설치된 CLI --help 및 아래 공식 문서, 2026-11-06.
- https://code.claude.com/docs/en/cli-reference
- https://learn.chatgpt.com/docs/cli/reference
- https://antigravity.google/docs/install?tab=cli

변경 파일: core/desktop_login.py, companion_server.py, console/setup.js/html/css,
버전 표시, macOS 패키징과 실행 권한, tests/test_desktop_login.py.
