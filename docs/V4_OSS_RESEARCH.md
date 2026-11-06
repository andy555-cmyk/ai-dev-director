# v4 오픈소스 조사 요약 (2026-11-06, GitHub API 확인)

## 가져다 쓸 것(허용 라이선스)
- 기획: github/spec-kit (MIT) — constitution → specify → plan → tasks 템플릿. BMAD-METHOD (MIT) 역할·PRD 템플릿 참고. MetaGPT (MIT) SOP 발상
- 긴 작업: snarktank/ralph, frankbria/ralph-claude-code (MIT) — prd.json 항목 하나씩, 반복마다 새 CLI 세션, progress 파일. OpenHands(MIT) 이벤트 로그·응축 발상. Aider(Apache) repo-map·편집마다 커밋 체크포인트
- 화면 검수: playwright-python (Apache, channel="chrome"이면 브라우저 내려받기 없음), anthropics/skills webapp-testing의 with_server.py (Apache), axe-core (MPL, 수정 없이 주입만), pixelmatch (ISC), Lighthouse (Apache). 대안 chrome-devtools-mcp / playwright-mcp (Apache)
- 뼈대: Vite + React + Tailwind + shadcn/ui (MIT), Tauri (Apache), full-stack-fastapi-template (MIT)
- 디자인 규칙: anthropics/skills frontend-design (Apache), ui-ux-pro-max-skill (MIT, 신뢰도 미확인)
- 취향 기억: AGENTS.md 관례 + 파일 기반 taste/design_rules.md, taste/rejections.jsonl (mem0·Letta는 API 필요해 발상만)
- 현황판: vibe-kanban (Apache) 이정표 칸반·작업마다 worktree, humanlayer (Apache) 승인 상태 기계

## 피할 것
- API 키 기본: browser-use, Stagehand, mem0, Letta
- GPL·AGPL(코드 금지): claude-squad, opcode, claudecodeui, Superdesign, basic-memory, spec-workflow-mcp
- 상업 제한: Task Master(Commons Clause), GPT-Pilot(FSL)
- 통째로 끼우기: OpenHands, MetaGPT

## 이 맥 환경
- Chrome 설치됨, Node 26(전역 WebSocket 있음 → 의존성 없이 CDP 가능), Python 3.9.6, 디스크 여유 약 19GB
- CLI: claude 2.1.304(구독), codex 0.163.0(구독), grok 1.0.70(구독), agy 없음
