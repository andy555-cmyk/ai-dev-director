# AI DEV DIRECTOR v4 기획서

기준: `docs/V4_GOAL.md`  
작성 범위: 기획만 수행, 코드·설정 변경 없음

**설계 결론:** 기존 구현·시험·검수 흐름은 유지하고, 바깥에 **기획 승인 → 이정표 관리 → 실제 화면 검수 → 출시 준비**를 담당하는 실행 관리자를 추가한다. 첫 구현은 이미 작성 중인 화면 검사 코드를 보강하는 데 집중한다.

본문의 새 파일·함수 이름은 구현 제안이다. 현재 존재하는 파일과 구분해 표기한다.

---

## 1. 목표 재정의

### 1.1 측정 가능한 완료 조건

| 목표 | 완료 조건 | 남겨야 할 증거 |
|---|---|---|
| 한 줄로 기획 시작 | 입력 후 10분 이내 기획 문서 4종, 작업 목록, 주요 화면 뼈대 생성 | `plan_manifest.json`, 생성 시간, 문서·캡처 |
| 승인한 내용만 구현 | 승인한 기획의 파일 지문과 현재 기획의 파일 지문 일치 | `approvals.jsonl`, `spec_hash` |
| 수십 단계 진행 | 30개 작업을 가진 시험에서 12단계를 넘어 계속 진행 | 작업별 상태·실행 기록 |
| 중단 후 이어하기 | 중단 지점부터 재개하며 완료 작업 중복 실행 없음 | `checkpoint.json`, 재개 시험 기록 |
| 단계마다 화면 확인 | 첫 단계부터 실행 가능한 화면 유지, 각 단계의 영향 화면 검사 | 화면별 PNG·측정 결과·모델 판정 |
| 자동 수정 | 화면 결함을 수정 작업으로 만들고 재검사 | 수정 전후 캡처, 결함 식별자 |
| 대표 개입 최소화 | 정상 시험에서 기획·중간 화면·출시 승인, 최대 3회 | 승인 기록 |
| 문서와 출시 묶음 | 실행 설명, 기능 설명, 시험 결과, 정적 웹 배포본 생성 | `release/manifest.json`, 압축 파일 |
| 첫 종단 시험 | 조기축구 관리 앱이 4시간 이내 완성 | 전체 시간표·실행·검수 증거 |
| 기존 기능 보존 | 기존 시험 항목 삭제·완화 없이 새 실패 0건 | 변경 전후 시험 항목·결과 비교 |

완료는 다음 조건을 프로그램이 모두 확인할 때만 인정한다.

```text
완료 =
  승인한 필수 작업 전부 통과
  AND 기능 시험 통과
  AND 작성자와 다른 공급자의 독립 검수 통과
  AND 필수 화면·크기·상태 전부 검사
  AND 미해결 화면 결함 0
  AND 문서·출시 묶음 검증 통과
```

지휘 담당의 `DONE` 응답만으로 완료 처리하지 않는다.

### 1.2 목표 문서의 빈틈과 정리안

| 빈틈·모순 | 적용할 해석 |
|---|---|
| 개입 3회 제한과 위험 행동 승인 요구가 충돌 | 정상 경로의 목표를 3회로 제한. 위험 행동 발견 시 안전 정지가 우선이며, 추가 개입이 생기면 시험의 개입 목표는 미달로 기록 |
| 10분·4시간 보장과 구독 사용 한도가 충돌 | 전체 경과 시간과 실제 작업 시간을 따로 기록. 사용 한도로 멈춘 경우도 전체 시간에서 숨기지 않음 |
| “다시 실행해도 같은 결과”가 불명확 | 같은 출시 묶음·시험 자료로 같은 기능 결과를 얻는다는 뜻. 새 생성 실행에서 코드·이미지가 바이트 단위로 같다는 뜻은 아님 |
| 웹은 정적 배포본인데 데이터 저장 방식이 없음 | 첫 시험은 한 기기의 브라우저 저장소 사용. JSON 내보내기·가져오기 제공. 공동 접속·서버 동기화 제외 |
| 모든 단계의 화면 검사가 초기 데이터 작업과 충돌 | 첫 이정표에서 실행 가능한 화면 뼈대 생성. 이후 데이터 작업도 최소 대표 화면과 관련 상태 검사 |
| 웹·데스크탑을 동시에 완성하면 첫 구현이 커짐 | 1·2차는 정적 웹 완성. 데스크탑 앱 묶음은 3차, 별도 합격 기준 적용 |
| 오픈소스 조사에 MPL·ISC가 포함 | `V4_GOAL.md`의 MIT·Apache·BSD 허용 목록을 우선. `axe-core`, `pixelmatch`는 이번 이식 대상에서 제외 |

추가로 “표준 라이브러리 서버”는 HTTP 서버 구성에 해당한다. 저장소 전체는 이미 `pydantic`, `pyyaml`, `click`, `psutil` 등을 사용한다. **새 실행 의존성을 추가하지 않는 방향**으로 해석한다.

---

## 2. 현재 구조 진단

### 2.1 목표를 막는 지점

| 파일·함수 | 현재 동작 | v4에서 필요한 변화 |
|---|---|---|
| `dashboard_server.py::start_goal_mission()`·`handle_chat_message()` | 대화 결과를 ORDER로 바꾸어 구현 시작 | 기획 문서 생성과 대표 승인 단계를 먼저 통과 |
| `agents/head.py::BaseHead.plan_next()` | 다음 ORDER 또는 `DONE` 생성 | 승인한 전체 작업 목록과 완료 증거를 기준으로 작업 선택 |
| `core/mission.py::MissionRunner.create()`·`_advance()` | 기본 6단계, 깊게 실행해도 12단계 | 작업 수와 재시도 횟수를 분리한 장기 실행 관리 |
| `config.yaml::autonomy.profiles` | 2·6·12단계 상한 | v4 전용 시간·작업·호출 예산 추가 |
| `schemas/order.py::OrderSchema` | 기본 15파일·800줄 | 작업을 작게 분할해 유지 |
| `Orchestrator.apply_safety_caps()` | 설정 상한 15파일·1,500줄 적용 | 상한을 늘리지 않고 작업 분할 |
| `autopilot.split_post_build()`·`Orchestrator.validate_post_build()` | 일부 파일 수·변경량 초과를 자동 면제 | v4에서는 면제 없이 재분할하는 엄격 모드 추가 |
| `agents/proposal_builder.py::ProposalBuilder.run()` | 전체 파일 또는 부분 교체 제안, 읽을 자료에 크기 제한 | 작업에 필요한 승인 기획·취향·관련 코드만 정확히 공급 |
| `MissionRunner._plan()`·`_advance()` | 지휘 담당의 `DONE`을 받아 미션 종료 | 작업·기능·화면·문서 증거를 프로그램이 다시 확인 |
| `Orchestrator.final_evidence()` | 작업본·경로·기준 시험·회귀 검사 확인 | 화면 검사 결과를 포함한 상위 완료 관문 필요 |
| `Orchestrator.apply_final_pass_gate()` | 경미한 검수 문제나 독립성 저하를 허용하는 경로 존재 | v4 완료는 작성자와 검수자 분리, 검수 원문 `pass` 필수 |
| `MissionRunner._auto_apply()` | 기본 `on_pass`, 부분 결과도 원본에 반영 가능 | v4는 `auto_apply=off`, 출시 준비와 원본 반영 분리 |
| `core/env_utils.py::get_sanitized_env()` | 정해진 7개 API 키 변수만 제거 | 모든 `*_API_KEY`와 별도 과금 경로 점검 |
| `agents/claude_head.py::_invoke_cli()` | 출력 형식만 지정, 도구 제한은 명령에 없음 | 새 단계의 기획·판정 호출은 도구 없는 제한 실행 |
| `dashboard_server.py::mission_view()` | 실행 단계·시험 수·반영 상태 중심 | 승인·작업별 완료·캡처·화면 판정 추가 |
| `console/stage.js::liveModel()`·`paintMission()` | 단계 예산만큼 숫자 칸 표시 | 실제 작업의 대기·진행·수정·완료 상태 표시 |

파일 수 상한 자체가 문제는 아니다. **큰 목표를 작은 작업으로 나누는 장치가 부족한 것이 문제**다.

또한 구현 방식은 README 설명보다 발전해 있다. `ProposalBuilder.resolve_changes()`는 전체 파일뿐 아니라 `old/new` 방식의 부분 교체도 지원한다. 이를 버리고 새로운 편집 체계를 만들 필요가 없다.

### 2.2 작성 중인 화면 검사 코드

현재 작업 폴더에는 아직 Git에 등록되지 않은 다음 파일이 있다.

- `core/vision_qa.py`
- `scripts/qa/see.mjs`

화면 검수가 완전히 없는 상태는 아니다. 다만 `Orchestrator`·`MissionRunner`의 완료 판단에는 연결되지 않았다.

| 지점 | 확인된 문제 |
|---|---|
| `vision_qa.measure()` | 일반 `subprocess.run()` 사용. 기존 전체 프로세스 정지 관리와 분리 |
| `vision_qa.judge()` | 처음 6장만 판정하여 나머지 화면 누락 가능 |
| `vision_qa.judge()` | 종료 코드가 실패여도 출력에서 판정을 찾을 수 있음 |
| `vision_qa.parse_verdict()` | 필수 키 존재 위주 검사. 문제 항목·점수·화면 범위의 엄격한 검증 부족 |
| `vision_qa.screen_gate()` | `clipped_text`가 차단 목록에 없어 잘림을 놓칠 수 있음 |
| `vision_qa.screen_gate()` | 필수 화면 수·파일 지문·판정 범위 확인 없음 |
| `see.mjs` 주소 처리 | 시작 주소만 검사. `--paths`의 절대 주소와 이후 이동을 별도 제한하지 않음 |
| `see.mjs::audit()` | 고정 위치 요소를 겹침 검사에서 제외, 입력란 글자·부모에 의한 잘림 누락 가능 |
| `see.mjs::audit()` | 항목 수를 먼저 잘라 실제 결함 총수가 축소될 수 있음 |
| `see.mjs::audit()` | `canvas` 등이 존재하면 빈 화면 판정에서 빠질 수 있음 |
| `see.mjs` 준비 대기 | 고정 시간 대기. 글꼴·이미지·화면 안정 여부 미확인 |
| `see.mjs` 검사 범위 | 대비 검사와 클릭 후 상태 검사 없음 |

현재 CSS와 `dashboard_server.py`에도 기존 수정이 있다. 구현자는 이를 자신의 변경으로 간주하거나 덮어쓰지 않아야 한다.

### 2.3 환경·시험 사실

- 현재 터미널: Node **24.18.0**, 전역 `WebSocket` 사용 가능
- Chrome: **157.0.8103.38**
- Claude: **2.1.304**, Codex: **0.163.0**
- Python 3.9는 요구 호환 버전으로 유지. 이번 읽기 작업에서 실행 버전 재확인은 권한 문제로 완료하지 못함
- **675개 전부 통과는 이번 세션에서 확인하지 않음**. README의 596개 표기는 오래된 기록이므로 구현 시작 시 실제 시험 목록을 기준으로 고정

---

## 3. 새 파이프라인 설계

### 3.1 기존 실행기 바깥에 v4 관리자 추가

`core/delivery.py::DeliveryRunner`를 신설한다. 기존 `core/state_machine.py`의 실행 상태에 기획·화면·출시 상태를 섞지 않는다.

```text
PLAN
  ↓
WAIT_PLAN_APPROVAL
  ↓
BUILD → RUN_SEE → FIX ─┐
  ↑                    │
  └────────────────────┘
  ↓
REPORT → 다음 작업
  ↓
WAIT_SCREEN_APPROVAL   ← 대표 중간 확인 1회
  ↓
남은 BUILD·RUN_SEE·FIX
  ↓
DOCS_PACKAGE
  ↓
WAIT_RELEASE_APPROVAL
  ↓
READY
```

`READY`는 출시 가능한 묶음이 준비됐다는 뜻이다. 공개 배포 성공은 별도 `PUBLISHED` 기록으로 구분한다.

### 3.2 파일 배치와 소유권

감독관 기록은 제품 작업본 밖에 둔다.

```text
data/deliveries/<delivery_id>/
  delivery.json
  approvals.jsonl
  events.jsonl
  plan/v001/
    spec/prd.md
    spec/screens.md
    spec/data.md
    spec/design.md
    spec/tasks.json
    wireframes/*.html
    plan_manifest.json
  checkpoint.json
  progress.md
  evidence/<task_id>/<attempt>/
    source.json
    launch.json
    measurements.json
    screenshots/*.png
    judge-input.json
    judge-raw.jsonl
    judge.json
    gate.json
  reports/*.json
  release/
    manifest.json
    checksums.sha256
    app.zip
```

제품 코드는 기존 `.director_worktrees/` 안에서만 수정한다.

- 기획 문서는 승인 후 해당 버전을 고정한다.
- 구현 담당에게는 선택한 문서 내용을 입력으로 제공한다.
- 구현 담당은 승인 기록·작업 상태·검수 결과를 직접 쓰지 못한다.
- 모델이 작성한 설명과 프로그램이 측정한 사실을 별도 파일에 저장한다.

### 3.3 단계별 계약

| 단계 | 입력 | 출력 | 담당 | 실패 시 동작·통과 금지 조건 |
|---|---|---|---|---|
| PLAN | 한 줄 목표, 프로젝트 현황, 취향 | 문서 4종·`tasks.json`·HTML 뼈대·캡처 | Claude CLI 기본, Codex 대체 | 형식 수정 1회. 필수 문서·화면·완료 기준 누락 시 승인 화면으로 보내지 않음 |
| 기획 승인 | 문서·캡처·가정·파일 지문 | 승인 기록 | 대표, 감독관 저장 | 승인 없음·과거 버전 승인·중복 요청 불일치 시 BUILD 금지 |
| BUILD | 승인 작업 1개, 직전 통과 작업본, 관련 문서 | 기존 `runs/<run_id>/` 증거와 변경 작업본 | 기존 `Orchestrator`, 구독 CLI | 범위·시험·독립 검수 실패 시 완료 금지. 구현 수정 기본 2회 |
| RUN&SEE | 작업본 지문, 실행 설정, 화면 검사 목록 | 실행 기록·PNG·측정·모델 판정 | Python·Node·Chrome, 판정 CLI | 실행 실패·누락·측정 불가·판정 실패 모두 통과 금지 |
| FIX | 결함 식별자·좌표·관련 코드·전 캡처 | 제한된 수정 ORDER, 후 캡처 | 지휘 CLI·구현 CLI | 화면 수정 최대 2회. 같은 결함 지속 시 `BLOCKED_QUALITY` |
| REPORT | 작업 결과와 검수 증거 | 캡처 포함 보고 JSON | 감독관, 필요 시 지휘 CLI 요약 | 보고 문구 오류는 재생성. 증거 없는 “완료” 문구 금지 |
| 중간 승인 | 대표 화면과 반려 기록 | 승인 또는 수정 방향 | 대표 | 첫 사용 흐름 완성 후 1회 대기. 반려 시 해당 작업 재개방 |
| DOCS·묶음 | 통과한 전체 작업·실행 결과 | 실행 설명·기능 설명·시험 보고·배포본 | 문서 CLI, 감독관 묶음 생성 | 새 폴더에서 실행·필수 파일·지문 검사 실패 시 출시 승인 금지 |
| 출시 승인 | 완성 묶음, 검수 결과, 공개 범위 | 해당 묶음의 승인 기록 | 대표 | 묶음 변경 시 기존 승인 무효. 승인 없는 배포·결제·계정 작업 금지 |

### 3.4 `tasks.json` 구조

```json
{
  "schema_version": 1,
  "plan_version": 1,
  "tasks": [
    {
      "id": "T003",
      "title": "경기별 출석 입력과 저장",
      "depends_on": ["T001", "T002"],
      "allowed_paths": ["app/attendance.js", "tests/attendance.test.mjs"],
      "required_outputs": ["app/attendance.js", "tests/attendance.test.mjs"],
      "acceptance_ids": ["AC-ATT-01", "AC-ATT-02"],
      "screen_case_ids": ["SC-ATT-LIST", "SC-ATT-SAVED"],
      "estimated_minutes": 15,
      "max_build_repairs": 2,
      "max_visual_repairs": 2
    }
  ]
}
```

작업의 실제 상태는 승인 문서와 분리해 `delivery.json`에 저장한다.

검사 규칙:

- 작업 식별자 중복·의존 관계의 순환 금지
- 모든 완료 기준이 작업과 시험에 연결되어야 함
- 모든 주요 화면이 검사 사례와 연결되어야 함
- 작업 1개는 기본 3~5파일, 기존 상한 이내
- 작업을 쪼갤 때 부모 작업·자식 작업 관계 보존
- 필수 기능 추가·삭제는 기획 변경으로 처리하고 기존 승인 무효화
- 단순 구현 순서 변경·동일 완료 기준의 작업 분할은 승인 범위 안에서 처리

### 3.5 긴 작업과 이어하기

Ralph식 반복에서 가져올 것은 **작업 하나씩 처리, 매번 새 CLI 호출, 진행 기록, 통과 증거에 따른 완료 처리**다. 무한 반복이나 완료 문구만 믿는 방식은 가져오지 않는다.

`checkpoint.json` 필수 필드:

```text
delivery_id, revision, phase, task_id, attempt, run_id
plan_hash, taste_hash, source_snapshot_ref
candidate_worktree, last_accepted_worktree
evidence_manifest_hash, completed_task_ids
spent_seconds, cli_calls, stop_requested
```

운영 규칙:

1. CLI 호출 전 실행 식별자를 먼저 저장한다.
2. 단계 종료 시 임시 파일에 기록한 뒤 원자적으로 교체한다.
3. `core/bootstrap.py::snapshot()`의 기존 비공개 스냅샷 방식을 재사용한다.
4. 다시 시작하면 작업본·기획·증거 지문을 대조한다.
5. 구현 통과 후 화면 검사 중 끊겼다면 BUILD를 반복하지 않고 화면 검사부터 재개한다.
6. 파일이 바뀌었으면 이전 캡처·판정을 재사용하지 않는다.
7. `STOPPED`는 자동 재개하지 않는다.
8. 제품별 실행 잠금과 기록 버전 검사를 사용해 중복 실행을 막는다.

제안 기본 예산:

```text
전체 작업 시간: 240분
작업 수: 최대 40개
전체 CLI 호출: 최대 160회
작업별 구현 수정: 2회
작업별 화면 수정: 2회
같은 원인 연속 실패: 3회
```

상한 도달 시 `INCOMPLETE_BUDGET`으로 저장한다. 완료로 바꾸거나 예산을 자동 증가시키지 않는다.

---

## 4. 화면 검수 설계

### 4.1 선택: 기존 Chrome + Node의 직접 화면 제어

기존 `scripts/qa/see.mjs`를 발전시킨다.

- Python 3.9: 실행 관리·결과 검증·파일 기록
- Node: Chrome 제어 연결과 화면 내부 측정
- Chrome: 실제 화면 실행·캡처
- 구독 CLI: 이미지 기반 시각 판단

추가 패키지와 브라우저 다운로드가 없고, 현재 코드도 이 방식으로 시작돼 있다.

Chrome의 `Page.captureScreenshot`과 `Emulation.setDeviceMetricsOverride`로 캡처와 화면 크기를 지정한다. 다만 직접 연결 방식은 Chrome 변경을 따라가야 하므로 실행 전 기능 확인과 버전 기록이 필요하다. [Chrome 제어 규약](https://chromedevtools.github.io/devtools-protocol/)

Playwright는 복잡한 입력·브라우저 종류가 늘어나는 3차에서 재검토한다.

### 4.2 실행·준비·정리 절차

1. 승인한 실행 설정의 작업본·명령·포트를 확인한다.
2. 첫 정적 웹은 감독관이 관리하는 정적 파일 서버로 실행한다.
3. `127.0.0.1`의 지정 포트에서 준비 응답을 확인한다.
4. 별도 Chrome 프로필로 숨김 실행한다.
5. 이동 전 오류 수집과 외부 주소 차단을 활성화한다.
6. 문서 준비, `document.fonts.ready`, 이미지 로딩, 배치 안정 여부를 확인한다.
7. 최대 15초 안에 안정되지 않으면 실패한다.
8. 화면 측정·캡처·입력 동작 검사를 수행한다.
9. 성공·실패·중단 모두 자신이 띄운 서버와 Chrome 자식 프로세스를 종료한다.
10. 로그·캡처는 보존한다.

Chrome은 일반 사용 프로필을 사용하지 않는다. 별도 `--user-data-dir`은 디버깅 분리에도 필요하다. [Chrome 공식 안내](https://developer.chrome.com/blog/remote-debugging-port)

### 4.3 화면 크기와 상태

| 검사 시점 | 범위 |
|---|---|
| 매 이정표 | 영향 화면을 1440×900, 390×844에서 검사 |
| 공통 글꼴·배치·이동 메뉴 변경 | 구현 완료된 모든 화면 재검사 |
| 중간 승인 | 대표 사용 흐름의 전 화면과 입력 결과 |
| 최종 검사 | 주요 화면 5개 이상 × 1440×900·1280×800·390×844, 최소 15개 조합 |

각 화면은 기본 상태 외에 해당 기능의 빈 목록·입력 오류·저장 완료·긴 이름 상태를 검사한다.

긴 화면은 첫 화면만 찍지 않는다. 전체 높이 캡처를 보관하고, 판정에는 글자가 읽히는 화면 단위의 구간 캡처를 제공한다.

### 4.4 측정 항목

DOM은 브라우저가 관리하는 화면 요소 정보다. 측정값과 모델의 미감 판단을 구분한다.

| 항목 | 측정 방식 | 합격 기준 |
|---|---|---|
| 겹침 | 글자 영역·입력 요소 영역의 교차, 실제 앞뒤 가림 확인 | 설명되지 않은 겹침 0 |
| 넘침·잘림 | 글자 영역과 부모의 자르기 영역 비교, `scrollWidth/clientWidth` 등 확인 | 내용 손실 0 |
| 작은 글자 | 보이는 글자·입력값·안내 글자의 실제 표시 크기 | 12px 미만 0, 기본 본문 16px 이상 |
| 빈 화면 | 필수 제목·주요 조작 요소·콘텐츠 존재 확인 | 필수 요소 누락 0 |
| 콘솔 오류 | 실행 예외, `console.error`, 오류 로그 | 0 |
| 가로 스크롤 | 문서 너비와 화면 너비 비교 | 문서 전체 가로 넘침 0 |
| 대비 | 글자색·실제 배경색의 상대 밝기 계산 | 일반 글자 4.5:1, 큰 글자 3:1 이상 |
| 깨진 이미지 | 로딩 완료 여부·실제 이미지 크기 | 0 |
| 조작 가능 여부 | 버튼 클릭·입력·저장 후 예상 화면과 데이터 확인 | 필수 사용 흐름 전부 통과 |

대비 기준은 W3C 기준을 따른다. 큰 글자는 일반적으로 24px 이상, 굵은 글자는 약 18.67px 이상으로 구분하며 계산 결과를 반올림해 통과시키지 않는다. [W3C 대비 기준](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)

오탐과 누락 처리:

- 부모와 자식이 겹치는 정상 배치는 제외한다.
- 고정 메뉴·팝업도 검사한다.
- 의도한 겹침은 감독관의 검사 설정에 요소·화면·이유를 명시한다.
- 제품 코드의 `data-ignore` 같은 표시만으로 검사를 면제하지 않는다.
- 그림·그라데이션 배경의 대비를 계산하지 못하면 `UNKNOWN`으로 남긴다.
- 모델이 괜찮다고 해도 수치 검사 실패를 통과로 바꾸지 않는다.
- 항목 수 제한에 걸리면 `truncated=true`로 표시하고 통과 금지한다.
- 확인하지 못한 상태는 결함 0건으로 계산하지 않는다.

### 4.5 판정 JSON 스키마

`schemas/visual.py`에 저장할 화면 단위 결과 규격이다. `measurements`는 감독관이 생성하고, 모델은 `model` 부분만 반환한다.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "case_id", "source_hash", "plan_hash",
    "taste_hash", "viewport", "screenshots", "measurements",
    "model", "truncated"
  ],
  "properties": {
    "schema_version": {"const": 1},
    "case_id": {"type": "string", "minLength": 1},
    "source_hash": {"$ref": "#/$defs/hash"},
    "plan_hash": {"$ref": "#/$defs/hash"},
    "taste_hash": {"$ref": "#/$defs/hash"},
    "viewport": {
      "type": "object",
      "additionalProperties": false,
      "required": ["width", "height", "dpr"],
      "properties": {
        "width": {"type": "integer", "minimum": 1},
        "height": {"type": "integer", "minimum": 1},
        "dpr": {"type": "number", "minimum": 1}
      }
    },
    "screenshots": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "path", "sha256"],
        "properties": {
          "id": {"type": "string"},
          "path": {"type": "string"},
          "sha256": {"$ref": "#/$defs/hash"}
        }
      }
    },
    "measurements": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "overlap", "overflow", "small_text", "blank",
        "console_error", "horizontal_scroll", "contrast"
      ],
      "properties": {
        "overlap": {"$ref": "#/$defs/metric"},
        "overflow": {"$ref": "#/$defs/metric"},
        "small_text": {"$ref": "#/$defs/metric"},
        "blank": {"$ref": "#/$defs/metric"},
        "console_error": {"$ref": "#/$defs/metric"},
        "horizontal_scroll": {"$ref": "#/$defs/metric"},
        "contrast": {"$ref": "#/$defs/metric"}
      }
    },
    "model": {
      "type": "object",
      "additionalProperties": false,
      "required": ["verdict", "reviewed_image_ids", "issues", "summary"],
      "properties": {
        "verdict": {"enum": ["PASS", "FAIL", "UNKNOWN"]},
        "reviewed_image_ids": {
          "type": "array",
          "minItems": 1,
          "uniqueItems": true,
          "items": {"type": "string"}
        },
        "issues": {
          "type": "array",
          "items": {"$ref": "#/$defs/issue"}
        },
        "summary": {"type": "string"}
      }
    },
    "truncated": {"type": "boolean"}
  },
  "$defs": {
    "hash": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$"
    },
    "metric": {
      "type": "object",
      "additionalProperties": false,
      "required": ["status", "count", "issues"],
      "properties": {
        "status": {"enum": ["PASS", "FAIL", "UNKNOWN"]},
        "count": {"type": "integer", "minimum": 0},
        "issues": {
          "type": "array",
          "items": {"$ref": "#/$defs/issue"}
        }
      }
    },
    "issue": {
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "rule", "selector", "bbox", "message"],
      "properties": {
        "id": {"type": "string"},
        "rule": {"type": "string"},
        "selector": {"type": "string"},
        "bbox": {
          "type": ["array", "null"],
          "minItems": 4,
          "maxItems": 4,
          "items": {"type": "number"}
        },
        "message": {"type": "string"}
      }
    }
  }
}
```

`screen_gate()`で行う整合性確認:

- 要求した画面・サイズ・状態と結果の集合が完全一致
- PNGの存在・形式・寸法・ファイル指紋が一致
- モデルに渡した画像と`reviewed_image_ids`が一致
- `PASS`なのに問題があるなどの矛盾を拒否
- `UNKNOWN`、途中切れ、CLI異常終了を拒否
- 最後にコードが変わった後の証拠だけを使用

**平均点による合格は廃止する。** 1画面の重大な欠陥を他画面の高得点で相殺しない。

### 4.6 Codexへの画像添付

現在のCLIヘルプで確認した`--image`を使用する。以下はシェル文字列ではなく、`ProcessTreeRunner.run()`へ渡す引数配列の例。

```python
argv = [
    codex_executable,
    "exec",
    "--sandbox", "read-only",
    "--skip-git-repo-check",
    "--ephemeral",
    "--output-schema", judge_schema_path,
    "--image", screenshot_1,
    "--image", screenshot_2,
    "-"
]
```

- プロンプトは`stdin_data`へ渡す
- 作業場所は監督官が用意した検査資料専用フォルダー
- 終了コード0・時間超過なし・JSON検証成功をすべて要求
- 標準エラーから成功判定を拾わない
- 1回3〜5枚、全画像を分割して処理
- 画像ID・指紋・CLI版・実際の供給元・呼び出し結果を保存

### 4.7 Claudeへの画像添付

ローカルPNGは`--file`に渡さない。このオプションは`file_id:relative_path`形式のダウンロード用資料指定である。

画像本体をBase64にして、改行区切りJSONを標準入力へ渡す方式を採用する。

```python
argv = [
    claude_executable,
    "--print",
    "--restricted",
    "--tools", "",
    "--strict-mcp-config",
    "--mcp-config", empty_mcp_config_path,
    "--disable-slash-commands",
    "--no-session-persistence",
    "--input-format", "stream-json",
    "--output-format", "stream-json",
    "--verbose",
    "--json-schema", judge_schema_json
]
```

入力1行の構造:

```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "text",
        "text": "SC-ATT-SAVEDの画面を検査。続く画像と測定結果から指定形式で判定"
      },
      {
        "type": "image",
        "source": {
          "type": "base64",
          "media_type": "image/png",
          "data": "<PNGをBase64化した文字列>"
        }
      }
    ]
  }
}
```

`empty_mcp_config_path`の内容は`{"mcpServers":{}}`。出力は最終`result`イベントの正常終了と`structured_output`を確認する。

`--restricted`などの対応は現在のローカルヘルプで確認済み。画像入力の実呼び出し試験は今回未実施のため、1次実装で確認が必要。公式リポジトリには同形式の画像入力事例があるが、CLI版・環境差の失敗も報告されている。 [Claude CLI仕様](https://code.claude.com/docs/en/cli-reference)、[画像入力の報告](https://github.com/anthropics/claude-code/issues/79273)

`--bare`は使用しない。現在の公式説明では通常の購読ログインを利用しないため、本件の条件に合わない。 [Claude自動実行の説明](https://code.claude.com/docs/en/headless)

---

## 5. 代表の好みの記憶

### 5.1 ファイル構造

```text
taste/
  design_rules.md
  rules.json
  rejections.jsonl
  projects/<project_id>.json
  examples/
    approved/
    rejected/
```

| ファイル | 責任 |
|---|---|
| `design_rules.md` | 人が読める基準と理由 |
| `rules.json` | 機械で測る値、適用範囲、版 |
| `rejections.jsonl` | 代表の発言原文と対象画面、対応履歴 |
| プロジェクト別JSON | 今回だけの色・雰囲気・例外 |
| `examples/` | 承認・反対の判断に使った画像 |

`rules.json`の初期案:

```json
{
  "version": 1,
  "defaults": {
    "background": "white",
    "body_font_px": 16,
    "minimum_font_px": 12,
    "ui_sentence_final_period": false
  },
  "qualitative": [
    "根拠のない実績や数字を入れない",
    "見出しを小さくしすぎない",
    "文字の不自然な1字残りを避ける",
    "説明のない飾りや定型句を増やさない"
  ],
  "exceptions": [
    {
      "scope": "director_hud",
      "rule": "background",
      "value": "preserve_existing"
    }
  ]
}
```

白い背景の既定値は生成する製品へ適用する。既存HUDの暗い舞台を勝手に白くしない。

### 5.2 反対意見の反映

```text
代表の「これは好みではない」
  → 原文・画面・画像指紋を保存
  → 問題箇所と修正案を整理
  → 今回の修正条件に追加
  → 該当作業を再開
  → 修正前後を比較
  → 解消したか記録
```

記録には以下を含める。

```text
id, delivery_id, case_id, image_hash
original_comment, interpreted_rule
scope, source_event_id, status, resolved_by_evidence
```

- 代表の発言を自動的に全案件共通ルールへ広げない
- 「今後すべて」で明示された内容は共通化
- 意味が曖昧なら今回限りの仮条件として扱う
- 反対履歴は削除せず、対応済み状態を追記
- 好みは安全規則・承認範囲・数値基準を上書きできない

### 5.3 指示への挿入位置

`core/taste.py::build_taste_context(stage, project_id)`を共通入口とする。

| 挿入先 | 内容 |
|---|---|
| `PlanAgent.create_plan()` | 共通規則、今回の条件、参考画像 |
| `TaskPlanner.make_order()` | 作業に関係する規則だけ |
| `ProposalBuilder.run()`へ渡す`order.context` | 実装に必要な数値・文言規則 |
| `vision_qa.judge_prompt()` | 規則ID、反対履歴、承認した方向 |
| 文書生成 | 表現・数字の根拠に関する規則 |

各判定へ`taste_hash`を記録し、どの版の好みで検査したか追えるようにする。

---

## 6. HUD変更

中央の舞台、左右の情報欄、下部の進行表示は維持する。

### 6.1 承認画面

中央に重ねる詳細パネルを追加する。

- 目的・作る機能・作らない機能
- 画面一覧と画面骨格の小画像
- 保存方法・仮定・完成条件
- 「この内容で進める」「修正点を送る」
- 対象の計画版と承認状態

承認待ちは実行状態として保存する。画面を閉じても、再起動しても承認済みにはならない。

### 6.2 イ정표の進行欄

既存`mission-steps`を実際の作業一覧に変更する。

```text
待機 → 実装中 → 画面確認中 → 修正中 → 完了
                     └→ 保留
```

表示項目:

- 作業名
- 機能試験結果
- 画面検査結果
- 最新キャプチャ
- 修正回数

「17/40段階使用」は補助情報に下げる。主表示は「承認した12作業のうち7作業完了」とする。

### 6.3 キャプチャ付き報告

3作業完了ごと、または15分ごとに更新する。

```text
できたこと: 出欠登録と月別会費集計
画面: 出欠一覧 / 会費一覧
検査: 4画面・8条件、未解消0件
次: データの保存と復元
```

中間承認時以外の報告で毎回代表の返事を待たない。

変更候補:

| ファイル | 変更箇所 |
|---|---|
| `console/stage.js` | `liveModel()`にv4情報追加、`paintMission()`更新 |
| 新規`console/delivery.js` | `paintApproval()`、`paintTaskBoard()`、`paintScreenReport()` |
| 新規`console/delivery.css` | 詳細パネル・小画像・作業状態の表示 |
| `console/index.html` | 詳細パネルと読込追加 |
| `companion_server.py` | 新しい静的ファイルとv4用接続口追加 |
| `dashboard_server.py` | `build_activity_payload()`へv4参照追加 |

接続口案:

```text
GET  /ops/deliveries/<id>
POST /ops/deliveries/<id>/approve
POST /ops/deliveries/<id>/feedback
GET  /ops/deliveries/<id>/artifacts/<artifact_id>
```

承認要求には`request_id`・対象版・対象指紋を必須とする。画像は登録済みの`artifact_id`だけを配信し、任意の絶対パスを受け取らない。

生成HTMLをHUDと同じ権限で埋め込まない。承認画面はPNGを基本とする。

---

## 7. 安全・料金

### 7.1 購読CLIだけを使う

環境変数の削除だけでは購読利用を証明できない。CLI設定に別料金の認証・接続先が入っている場合も考慮する。

新規`core/subscription_policy.py`の責任:

```text
sanitize_env()             課金用キー・接続先切替変数を除去
probe_auth_mode()          秘密値を表示せず認証方式だけ確認
validate_provider_config() 独自接続先・APIキー補助設定を拒否
assert_subscription()     購読利用を確認できなければ停止
```

- `*_API_KEY`を一括除去し、既存の禁止一覧も維持
- AWS・Google等の別課金経路への切替を禁止
- 自動API切替・追加利用購入・自動課金を禁止
- 購読状態不明は`BLOCKED_AUTH`
- 使用上限は`PAUSED_QUOTA`として記録
- 別CLIへ切り替える場合も購読確認と独立検査を再実施
- 実際の追加料金設定を確認できなければ、無料と断定しない

### 7.2 危険な操作は実行前に止める

既存`autopilot.entry_gate()`・`money_code_findings()`・`SafetyPolicy`を維持する。

新しい段階も対象に含める。

| 場面 | 制限 |
|---|---|
| PLAN | 文書と画像を返すだけ。外部送信・インストールなし |
| 画面実行 | 承認済み実行設定だけ。実アカウント情報なし |
| クリック試験 | 試験用データのみ。外部送信・決済・実データ削除なし |
| DOCS | 実測結果から記述。勝手に公開しない |
| 発売用ファイル生成 | ローカルファイル作成のみ |
| 公開配布 | 承認したファイル・公開先・操作に限定 |

「会費を記録する」と「会費を実際に決済する」は区別する。第一試験は前者だけを行う。

### 7.3 隔離作業本はOSの隔離ではない

Git作業本だけでは、動かしたコードの外部通信やホームフォルダー読み取りを防げない。

`core/execution_policy.py`とmacOS用の実行制限を追加する。

- 作業本・専用一時領域以外への書込みを禁止
- 個人文書・認証情報へのアクセスを禁止
- 製品試験用プロセスは外部通信禁止
- 必要な自機内通信だけ許可
- 子プロセスにも制限を継承
- 起動前に書込み・通信禁止の自動確認を実施

このMacには`/usr/bin/sandbox-exec`がある。ただし存在だけでは有効性の証拠にならない。制限確認に失敗した場合、生成コードの実行を止める。

第一実装の画面確認は監督官所有の静的サーバーに絞り、任意のサーバー起動機能を後回しにする。

### 7.4 原本と制御記録の保護

- v4は`auto_apply=off`
- 原本へ反映する際は既存`ResultManager.apply_tree()`の競合検査を使用
- 人が変更したファイルがあれば反映停止
- 検査設定・承認・証拠ファイルは製品作業本の外に置く
- 新しい計画作成で安全上限・検査閾値を弱められない
- 容量不足では停止。古い作業本・証拠を勝手に削除しない

GPL・AGPLコードの移植は禁止する。外部コードを取り込む場合は、URL・版・ファイル・ライセンス・著作権表示を`docs/THIRD_PARTY_NOTICES.md`へ記録する。第一実装は外部コードの移植を必要としない。

---

## 8. 実装計画

### 8.1 第1次: 画面検査を信用できる状態へ

**Claudeが数時間で実装・試験する範囲は、静的WebのRUN&SEE単体までとする。** 自動計画・長期反復・HUD全面変更は含めない。

既存の画面検査原型があるため、ここを固めるのが最も効果が大きい。

想定作業量は4〜6時間。既存試験の実行時間は別途実測する。

#### 修正ファイル

| ファイル | 責任 |
|---|---|
| `core/vision_qa.py` | `measure()`を管理対象プロセスへ変更。`judge()`の全画像分割、終了コード確認、厳格解析。`screen_gate()`で証拠・範囲・指紋確認 |
| `scripts/qa/see.mjs` | `main()`化、入力検査、同一接続先制限、準備待ち、確実な終了、重複しない画像名 |
| `core/env_utils.py` | 禁止一覧に加えて`*_API_KEY`除去。既存認証情報の扱いは維持 |

#### 新規ファイル

| ファイル | 関数・責任 |
|---|---|
| `schemas/visual.py` | `Measurement`・`VisualJudgment`・`CaptureManifest`、厳格な型と整合性確認 |
| `scripts/qa/dom_audit.mjs` | `collectElements()`、`measureOverlap()`、`measureOverflow()`、`measureFonts()`、`measureContrast()` |
| `scripts/run_screen_qa.py` | `main()`。既存の静的成果物を指定して検査、結果保存、合否に応じた終了コード |
| `tests/test_v4_visual_gate.py` | 証拠不足・未知状態・画像欠落・終了失敗の拒否 |
| `tests/test_v4_vision_cli.py` | 実CLIを使わない引数・添付・応答解析・分割試験 |
| `tests/test_v4_capture_policy.py` | URL・出力先・停止・異常終了の試験 |
| `tests/fixtures/v4_visual/` | 正常、重なり、切れ、11px文字、空画面、エラー、低コントラストの固定画面 |

#### 第1次の合格条件

- 意図的に入れた各画面欠陥を検出
- `clipped_text`を確実に不合格にする
- 画像7枚以上でも全件判定
- CLI異常終了・不正JSON・不足画像で不合格
- 外部URL・外部への画面移動を拒否
- 中断後に自分のChromeを残さない
- 実画像をCodexへ添付した判定1件を実証
- Claude添付方式も小さい画像で動作確認
- 新規試験と既存試験に新しい失敗なし

この時点では「自動制作完成」と表示しない。成果は**実画面を根拠に通過・停止できる検査器**である。

### 8.2 第2次: 計画承認と長期反復の接続

| 新規・修正 | ファイル | 主な責任 |
|---|---|---|
| 新規 | `core/delivery.py` | `DeliveryRunner.start()`・`advance()`・`resume()`・`stop()` |
| 新規 | `core/delivery_store.py` | 原子的保存、実行ロック、版確認、追記イベント |
| 新規 | `core/planning.py` | 計画生成・必須成果物検証・画面骨格出力 |
| 新規 | `agents/plan_agent.py` | 購読CLIへの計画生成指示 |
| 新規 | `core/task_planner.py` | 次作業選択、ORDER変換、修正作業分割 |
| 新規 | `core/taste.py` | 好み読込み・適用範囲・指示生成 |
| 新規 | `core/subscription_policy.py` | 購読利用確認 |
| 新規 | `core/execution_policy.py` | 実行可能な処理とOS制限の確認 |
| 新規 | `schemas/delivery.py` | 計画・作業・承認・チェックポイント型 |
| 修正 | `core/orchestrator.py` | v4厳格モードで自動免除と独立性緩和を禁止。通常モードの既定動作を維持 |
| 修正 | `director.py` | `plan`・`delivery`・`delivery-resume`入口 |
| 修正 | `config.yaml` | `v4.enabled: false`を既定に専用設定追加 |
| 修正 | `companion_server.py` | 計画承認・進行・証拠取得 |
| 修正 | `dashboard_server.py` | v4明示時だけ新管理者へ振分け |
| 新規・修正 | `console/delivery.*`・`console/stage.js`・`console/index.html` | 承認画面、作業表示、キャプチャ報告 |

`core/mission.py`の旧ミッションを無理に変換しない。旧ミッションは旧実行器、v4は新管理者で継続する。

### 8.3 第3次: 文書・発売用ファイル・対象拡張

| ファイル | 責任 |
|---|---|
| 新規`core/release_package.py` | 文書生成、配布物検査、指紋一覧、圧縮 |
| 新規`core/release_gate.py` | 全作業・画面・文書・承認の最終確認 |
| 新規`templates/web_static/` | 依存追加なしの静的Web骨格 |
| 新規`templates/desktop/` | デスクトップ向け構成。依存・署名要件を別途固定 |
| 新規`tests/test_v4_football_e2e.py` | 一行入力から完成までの試験 |
| 修正`README.md`・新規`docs/V4_RUNBOOK.md` | 実行・停止・再開・障害時の手順 |

デスクトップは起動・終了・保存先・インストール用ファイルを別試験する。署名・公証・公開配布の承認をWeb完成に混ぜない。

---

## 9. 試験計画

### 9.1 一行の宗端試験

入力:

> 동네 조기축구 출석·회비 관리 웹앱 만들어줘

最初の計画では以下を明示する。

- 管理者1名、1台のブラウザーで使用
- 実決済なし、入金事実の手入力
- 会費額は変更可能な試験設定
- 会員・試合・出欠・請求額・入金記録を保存
- バックアップ用JSONの出力・復元
- 実際の会員情報を使わない

主要画面:

1. ホーム: 次の試合、出欠、未納概要
2. 会員管理
3. 試合日程
4. 試合別出欠
5. 月別会費

#### 実行手順

| 順序 | 手順 | 合格条件 |
|---|---|---|
| 1 | 空の試験用プロジェクトに一行入力 | 原本への製品コード書込みなし |
| 2 | 計画生成 | 10分以内、文書4種・作業一覧・5画面の骨格 |
| 3 | 代表が計画承認 | 承認前のBUILD呼出し0回 |
| 4 | 小さい作業単位で実装 | 各作業に機能試験・独立検査・画面証拠 |
| 5 | 中途で監督官プロセスを強制終了し再起動 | 完了作業の重複なし、途中段階から再開 |
| 6 | 3〜5作業程度のまとまりで中間画面確認 | 代表の第2回目の承認 |
| 7 | 画面と機能を完成 | 主要5画面×3サイズ、必須状態の検査完了 |
| 8 | 文書・配布物を生成 | 新しい展開先で起動・機能試験成功 |
| 9 | 代表が発売用ファイルを承認 | 第3回目の承認、対象指紋が固定 |
| 10 | 同じ成果物を再実行 | 保存データ・集計結果・機能試験結果が一致 |

#### 機能の合格例

- 会員追加・名前修正後に再読込みしても内容保持
- 同一試合・同一会員の出欠が二重登録されない
- 参加人数と一覧の人数が一致
- 会員3名、各10,000ウォン請求で請求総額30,000ウォン
- 入金10,000・5,000・0ウォンで未納総額15,000ウォン
- 別月の入金が今月の集計へ混ざらない
- JSON出力後、新しいブラウザー領域へ復元して同じ集計
- 不正ファイルの復元で既存データを壊さない
- 空一覧・長い名前・入力ミスの状態でも画面破綻なし

#### 最終合格

```text
全体4時間以内
代表介入3回以下
主要画面5以上、最終画面・サイズ組合せ15以上
重なり・切れ・12px未満・コンソールエラー0
未測定・未知・判定漏れ0
機能試験・独立検査通過
文書・発売用ファイルの再実行成功
```

外部待ちで時間を超えた場合は、機能完成と時間目標未達を分けて報告する。

### 9.2 CLIなしで回す単体試験

| 試験対象 | 主なケース |
|---|---|
| 計画 | 必須文書欠落、空の完成条件、作業重複、循環依存 |
| 承認 | 古い版、指紋不一致、二重要求、未承認BUILD拒否 |
| 作業選択 | 前提未完了の作業を選ばない、完了済みを再実行しない |
| 再開 | 保存直前・直後・CLI終了直後の中断、壊れた記録 |
| 停止 | 停止が遅い保存で取り消されない、再起動で自動再開しない |
| 予算 | 作業・時間・呼出し・修正回数の上限 |
| 安全 | 範囲外・保護パス・リンク経由の脱出・原本競合 |
| 認証 | APIキー・未知の認証方式・別課金接続先の拒否 |
| 画像添付 | Codex引数、Claude画像ブロック、7枚以上の分割 |
| 応答解析 | 空、途中切れ、無効JSON、異常終了中の偽PASS |
| 画面完了 | 必須画面欠落、古い画像、画像指紋不一致 |
| 数値判定 | 11.99px、12px、4.49:1、4.5:1の境界 |
| 好み | プロジェクト限定、原文保持、共通化条件、安全規則優先 |
| HTTP | ローカル出所・トークン・不正画像ID・パス脱出 |
| 発売用ファイル | 必須ファイル不足、秘密情報混入、指紋不一致 |
| 互換性 | v4無効時に既存呼出し・応答・停止動作を維持 |

CLI呼出しは`ProcessTreeRunner`の偽物へ置き換える。Chrome内の実際の表示測定は別のローカル統合試験に分ける。これも購読CLIは不要である。

既存675項目については、実装開始時に収集した試験ID一覧を基準にする。項目削除・無効化・成功条件の緩和で件数を合わせない。

---

## 10. リスクと決めること

### 10.1 主なリスク

| リスク | 対応 |
|---|---|
| 購読使用上限で4時間を超える | 残り時間と呼出し回数を記録。小さい作業と3〜5枚の画像判定にまとめる |
| 画面測定の見落とし・誤検出 | 固定画面の試験、意図した例外の限定、未知状態を通過させない |
| コード変更後に古い判定を再利用 | コード・計画・好み・画像の指紋を照合 |
| Chrome・CLI更新で動作が変わる | 版記録、実行前の機能試験、未対応時停止 |
| 生成コードが外部へアクセス | OS制限とブラウザー移動制限を併用。制限未確認なら実行しない |
| 現在進行中の変更と衝突 | 作業開始時の差分を保持。画面検査原型とCSS変更を上書きしない |
| 第1次を詰め込みすぎる | 単体RUN&SEEまでで区切り、全自動完成と表示しない |

### 10.2 代表が決めること

通常経路で必要な判断は次の3件だけとする。

1. **計画承認**: 作る機能・画面・保存方法・完成条件の確定
2. **中間画面承認**: 見た目と使い方の方向の確定
3. **発売承認**: 完成したファイルと公開先・公開操作の確定

今回の計画書を実装へ渡すために、先に追加で決める事項はない。第1次は**既存の画面検査原型を補強し、証拠不足を確実に止めるところまで**を実装範囲とする。