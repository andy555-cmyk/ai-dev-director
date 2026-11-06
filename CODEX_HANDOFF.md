# AI Dev Director macOS Preview 0.3.6

기존 TRINITY HUD에 Grok 보조 분석·리서치 전용 기능을 추가했습니다.
사용자 선택: Grok은 지휘·구현·검수 대체가 아닌 보조 분석·리서치 전용입니다.

- core/grok_research.py: 단일 분석 실행, 취소, 중복 방지, 결과 저장과 재시작 후 중단 처리.
- Grok CLI --prompt-file / JSON(text) / read-only / web_search,web_fetch 허용 / 셸·파일·MCP·하위 에이전트 제외.
- GET /ops/grok, POST /ops/grok/research 및 /cancel: 로컬 Host/Origin과 기존 X-Solomon-Bridge 인증.
- console/grok.js/css와 HUD 우측 상단 카드, 분석·로그인·취소·결과 패널.
- core/usage.py: GROK 제공자와 RESEARCH 역할을 호출 기록에 포함. 기존 3역할의 주 흐름은 유지.
- 설치·연결 진단에 Grok 카드와 grok login --oauth 버튼.
- 아이디·비밀번호·인증 코드는 사용자가 공식 화면에 직접 입력. 인증 파일을 읽거나 배포하지 마세요.

테스트는 가짜 CLI와 분리된 DB를 사용합니다. 실제 OAuth/계정 변경은 자동 수행하지 마세요.
관련 검사 64개. node --check console/grok.js 및 기존 stage.js/setup.js.
python -m pytest tests/test_grok_research.py tests/test_desktop_login.py tests/test_desktop_upgrade.py tests/test_macos_port.py tests/test_v301_companion_http.py tests/test_desktop_restart.py -q
빌드: python packaging/macos/build_bundle.py (macOS hdiutil).
설정·기록: ~/Library/Application Support/AI Dev Director/ (배포본에 포함하지 않음).
기존 앱·엔진은 업데이트 전 backups/에 보관합니다.
공식 자료: https://docs.x.ai/build/cli/headless-scripting , https://docs.x.ai/build/features/sandbox

0.3.2 설치본에서 실제 Grok 웹 문서 조사 완료·출처 URL 포함 결과와 CLI 연결 확인 버튼을 확인했습니다.

0.3.3: Grok 전용 4번 HUD 노드·코어 스트림을 추가했습니다. 메인 3역할의 set()과 독립적인 auxiliary()로 /ops/grok 상태를 반영합니다. 카드도 4번 노드의 투영 좌표를 따라갑니다. WebGL2·2D 및 모션 끄기에서 상태 반영을 검사하세요.

0.3.3 검증: 관련 pytest 64개 통과. hud_renderer.cjs (네 번째 노드·스트림, 3역할 독립 상태, WebGL/2D, 모션 끄기), grok_hud.cjs (실행/완료/오류/오프라인 복구) 통과.

0.3.4: core/desktop_connections.py가 CLI 진단 + 최근 10분 실제 응답 메타데이터로 3상태를 판정합니다. /ops/diagnostics GET/POST에 connections를 추가했고, HUD는 상세 사유·확인 시각·다시 점검과 오프라인 시 정상 배지 해제를 지원합니다. 인증 파일은 읽지 않습니다. Antigravity/Grok의 로그인 미확인을 임의의 연결 안됨으로 바꾸지 마세요.

0.3.5: console/trinity.js의 9~15 입자 그룹은 회로 버스/코어 광륜/구면 회로/파동/플레어/접점/투영 링입니다. 4개 AI 모두 회로가 있고 총 입자는 12.5만 미만입니다. WebGL/2D 경로와 모션 끄기를 검사합니다. core-insignia는 투영된 코어 좌표를 따라가며 상호작용을 가리지 않습니다. 기존 연결 상태/로그인 동작은 변경하지 않습니다.

0.3.6: core/grok_pipeline.py를 계획/구현/테스트검수/판단 및 보완에 연동했습니다. grok_pipeline.enabled(기본 true), required(기본 false), timeout_sec(기본 60, 최대120) 설정. 테스트에서는 기본 비활성, 주입된 보조 분석기는 활성. 단일 단계 실패는 report에 표시하며 required=true이면 실행을 중단합니다. Grok 보고서는 판단·승인·실제 테스트를 대체하지 않습니다. 요구사항·검증 요약만 전달하고 원본 파일/로그는 전달하지 않습니다. 자체 분석이 외부 참조 문서를 추가하지 못하도록 문서 로더에서 분리합니다. 단계별 fingerprint 캐시와 실제 CLI provenance, cross-process 취소를 지원합니다. 실제 4 CLI 예제 검증은 work/grok-process-check-20261106T174351/result.json에서 PASS·테스트4개·4단계 완료를 확인했습니다.
