# robo99_hq 운영 가이드

## 비협상 원칙

### 1. Single Writer Rule
- `.state/*.yaml`, `alerts/compiled/`, 자동 생성 briefing 파일은 **Mac mini 스케줄러만** 쓴다.
- Windows (Obsidian) 에서는 사람 markdown (`.md`) 만 편집한다.
- 같은 파일을 두 머신에서 동시에 수정하면 git conflict 가 발생한다.
  사람 영역 vs 기계 영역이 파일 단위로 분리돼 있으므로 규칙만 지키면 충돌은 구조적으로 불가능하다.

### 2. LLM 은 파일을 직접 쓰지 않는다
- `scheduler_daemon.py` 의 `run_claude()` 는 Claude CLI stdout 만 캡쳐한다.
- 파일 저장 · frontmatter 생성 · wikilink 렌더링 · 텔레그램 전송은 `vault_writer.py` 가 담당.
- LLM prompt 에 "이 경로에 저장하라" 같은 문구를 **넣지 말 것**.

### 3. `.state` 는 derived artifact
- `tickers/.state/*.yaml`, `events/.state/*.yaml`, `themes/active/.state/*.yaml` 는
  `entity_syncer.py` 가 raw source (briefing, review, event, screener) 로부터 생성한 파생 상태.
- 사람이 `.state` yaml 을 직접 편집하면 **다음 entity_syncer 실행 시 덮어써진다**.
- 사람이 남기고 싶은 영구 정보는 `tickers/<종목명>.md` frontmatter 에 기록한다.
  (추후 override 레이어 도입 예정)

### 4. Silent Failure 금지
- `healthcheck_entities.py` 가 아래 조건에서 텔레그램 알림을 보낸다:
  - 파싱된 엔티티 0건
  - quarantine 파일 존재 (LLM 출력 검증 실패)
  - wikilink 커버리지 80% 미만
  - 연속 briefing 유사도 90% 초과
  - state_events 마지막 기록 24시간 이상 경과
  - stale 종목 50% 초과

### 5. Idempotency
- `entity_syncer.py` 를 같은 입력으로 2회 실행하면 두 번째 실행에서 파일 diff 가 없어야 한다.
- 모든 `.state` 변경은 `state_events/YYYY-MM.jsonl` 에 append-only 로 기록된다.

---

## 파일 영역 구분

### 사람 영역 (Windows Obsidian 에서 편집)
- `tickers/<종목명>.md` — 투자 thesis, 메모, 주관적 판단
- `events/*.md` — 사건 카드 본문
- `themes/active/*.md` — 테마 노트 본문
- `watchlist.md` — 관심 종목 실수 관리
- `reviews/*.md` — CIO 리뷰 (에이전트 생성 후 사람이 편집 가능)

### 기계 영역 (Mac mini 스케줄러/스크립트만 쓰기)
- `tickers/.state/*.yaml` — 종목 상태 (entity_syncer)
- `events/.state/*.yaml` — 이벤트 상태 (entity_syncer)
- `themes/active/.state/*.yaml` — 테마 상태 (entity_syncer)
- `alerts/*.md`, `alerts/*.json` — 브리핑, 스크리너 결과 (scheduler_daemon + vault_writer)
- `alerts/quarantine/*.json` — LLM 출력 검증 실패 보관 (vault_writer)
- `alerts/healthcheck_metrics.json` — 헬스체크 메트릭 (healthcheck_entities)
- `state_events/*.jsonl` — append-only 변경 이력 (entity_syncer)

---

## 일일 운영 순서

| 시각 | 작업 | 누가 |
|---|---|---|
| 07:02 | 미장 마감 리포트 | scheduler → Claude CLI → vault_writer |
| 08:30 | 장전 브리핑 (delta-only) | scheduler → Claude CLI → vault_writer → Telegram |
| 09:20 | 장초반 스크리닝 | scheduler → Python scripts |
| 14:00 | 장중 스크리닝 | scheduler → Python scripts |
| 15:40 | 장마감 특징주 분류 | scheduler → Claude CLI → vault_writer → Telegram |
| 23:00 | 시스템 자가 점검 | scheduler → Claude CLI |
| 23:30 (예정) | entity_syncer | launchd / cron → entity_syncer.py |
| 23:35 (예정) | healthcheck | launchd / cron → healthcheck_entities.py |

---

## 장애 처리

### 텔레그램 브리핑이 안 올 때
1. `tail -50 ~/robo99_hq/alerts/scheduler.log` — 스케줄러가 job 을 실행했는지 확인
2. `ls ~/robo99_hq/alerts/quarantine/` — vault_writer 가 출력을 격리했는지 확인
3. `cat ~/robo99_hq/alerts/healthcheck_metrics.json` — 마지막 헬스체크 결과
4. 스케줄러 재시작: `pkill -f scheduler_daemon.py && cd ~/robo99_hq && nohup uv run python scripts/scheduler_daemon.py > alerts/scheduler.log 2> alerts/scheduler.err &`

### entity_syncer 가 0건 파싱할 때
1. `ls ~/robo99_hq/alerts/theme_briefing_*.md | tail -5` — 최신 briefing 이 있는지
2. `grep '\[\[' ~/robo99_hq/alerts/theme_briefing_$(date +%Y-%m-%d).md | wc -l` — wikilink 있는지
3. briefing 에 wikilink 가 없으면 → `scheduler_daemon.py` 의 theme_screener prompt 점검

### .state 가 오염됐거나 불일치할 때
1. `.state` 디렉토리를 전부 삭제해도 된다 — `entity_syncer.py` 를 한 번 돌리면 재생성.
2. 재생성 후에도 이상하면 `state_events/*.jsonl` 의 최근 이력을 확인해서 언제 오염됐는지 역추적.
3. (Phase 2 에서 `rebuild_state.py` 도입 예정)

### 스케줄러가 이중 실행될 때
- lockfile (`alerts/.scheduler.lock`) 이 자동으로 두 번째 인스턴스를 차단한다.
- 에러 메시지: "이미 다른 스케줄러가 실행 중입니다"
- 강제 해제: `rm ~/robo99_hq/alerts/.scheduler.lock`

---

## git 운영

### 브랜치 전략
- 단일 `main` 브랜치. Mac/Windows 양쪽 push.
- 사람 영역 / 기계 영역 파일 분리로 conflict 원천 차단.

### .gitattributes
- 모든 텍스트 파일 LF 강제 (`* text=auto eol=lf`).
- Windows 에서 CRLF 로 저장돼도 git 이 commit 시 LF 로 변환.

### .gitignore 권장 추가 항목
```
alerts/.scheduler.lock
alerts/logs/
alerts/quarantine/
state_events/
```
(state_events 는 로컬 디버깅용. git 에 넣으면 히스토리가 빠르게 비대해진다.)

---

## Phase 1 산출물 목록

| 파일 | 역할 |
|---|---|
| `scripts/schema_models.py` | pydantic-free 스키마 정의 + 검증 |
| `scripts/vault_writer.py` | JSON → 검증 → 렌더 → atomic write → Telegram |
| `scripts/healthcheck_entities.py` | 메트릭 수집 + 텔레그램 알림 |
| `scripts/entity_syncer.py` (수정) | state_events append-only 이벤트 로그 추가 |
| `scripts/scheduler_daemon.py` (수정) | stdout 캡쳐 + vault_writer 연동 + lockfile |
| `.gitattributes` | LF 강제 |
| `docs/operations_guide.md` | 이 문서 |
