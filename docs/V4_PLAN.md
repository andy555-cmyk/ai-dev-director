# AI DEV DIRECTOR v4 확정 기획

## 목표
- 대표가 「○○ 앱 만들자」 한 줄만 쓰면 기획 → 구현 → 실제 화면 확인 → 수정 → 문서·출시 묶음까지 끝냄
- 대표 확인은 세 번만: 기획 승인, 중간 화면 승인, 출시 승인
- 성공 기준: 조기축구 출석·회비 웹앱을 한 줄로 시작해 4시간 안에 화면 5개 이상, 테스트 통과, 화면 검수 통과, README 포함 묶음

## 흐름(상태)
| 단계 | 하는 일 | 멈춤 |
|---|---|---|
| PLANNING | 도구 없는 Claude가 기획서 4종(요구사항·화면·데이터·디자인), 화면 목록, 작업 6~14개, 화면별 와이어프레임 HTML 작성 · 구조 검증 실패 시 1회 재작성 | |
| WAIT_PLAN_APPROVAL | 와이어프레임 캡처와 문서를 보여 줌 · 승인은 기획 해시가 같을 때만 | 대표 1 |
| BUILDING | 작업 순서대로 기존 Orchestrator가 격리 작업본에서 구현·테스트·독립 검수 → 실제 실행 화면 캡처(PC·휴대전화) → 측정 + 코덱스 이미지 판정 → 불합격이면 최대 2번 자동 수정 | |
| WAIT_SCREEN_APPROVAL | 작업 절반 끝난 뒤 실제 화면 보여 줌 · 의견은 다음 작업에 반드시 반영 | 대표 2 |
| PACKAGING | 최종 화면 검수(1440·1280·390) → README 확인 → app.zip·체크섬 | |
| WAIT_RELEASE_APPROVAL | 묶음 해시가 그대로일 때만 승인 | 대표 3 |
| READY | 대표가 직접 고친 파일이 없으면 프로젝트 폴더에 복사 | |

## 판정 원칙(fail-closed)
- 캡처 없음, 판정 응답 깨짐, 시간 초과는 모두 불합격
- 측정 결함 막힘 항목: 빈 화면, 이동 오류, 콘솔 오류, 겹침, 가로 스크롤, 깨진 이미지, 화면 밖 요소
- 13px 미만 글자는 한 곳이라도 불합격
- 승인 뒤 기획 파일이 바뀌면 멈춤
- 예산: 240분, 빌드 재시도 2회, 화면 수정 2회

## 취향 학습
- `taste/design_rules.md`: 웹제작 플레이북 §1·§1-1 요약(13px 하한, 화면 문구 끝 마침표 금지 등)
- 대표가 남긴 의견은 `data/taste_rejections.jsonl`에 쌓이고, 최근 10건이 기획·구현·판정 지시에 함께 들어감
- `data/` 아래라 앱을 업데이트해도 남음

## 쓰는 도구(구독 CLI만, 종량제 API 없음)
- 기획: Claude CLI(도구·MCP·사용자 설정 끈 상태)
- 구현·검수: 기존 HEAD / BUILDER / REVIEWER 배정
- 화면 판정: Codex CLI 읽기 전용 + 캡처 이미지 첨부
- 눈: `scripts/qa/see.mjs`(Node 내장 WebSocket으로 크롬 CDP, 추가 설치 없음, localhost만)

## 첫 범위
- 정적 웹앱(빌드 도구 없음, localStorage, node:test)
- 서버·로그인·결제·외부 API가 필요한 앱은 다음 단계

## 쓰는 법
- HUD 상단 「앱 만들기」 → 한 줄과 폴더 → 기획 시작
- 명령줄: `director.py deliver start -p 폴더 -g "한 줄"` · `deliver status` · `deliver approve <id> plan|screen|release` · `deliver feedback <id> "고칠 점"`
- 기록: `data/deliveries/<id>/`(기획 판, 화면 증거, 출시 묶음, 진행 기록)

## 참고한 오픈소스(코드 이식 없음, 방식만)
- spec-kit: 기획 문서 → 작업 분해
- Ralph 반복 루프: 작은 작업 하나씩 끝까지
- AGENTS.md 관례, vibe-kanban 작업판
- 피함: AGPL 프로젝트, Task Master
