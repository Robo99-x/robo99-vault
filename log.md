# robo99 Operation Log

append-only. 절대 편집/삭제 금지.
포맷: ## [YYYY-MM-DDTHH:MM KST] {ACTION} {설명}

ACTION 목록:
- INGEST: raw 파일 저장
- DRAFT: event card draft 생성
- PREFLIGHT_FAIL: preflight check 실패
- CONFIRM: Gate 1 통과 (draft → confirmed)
- INTEGRATE: Gate 2 통과 (confirmed → integrated)
- SKIP: Gate 2에서 thesis 무관 (confirmed → skipped)
- RETRO: retrospective 실행
- CIO_SESSION: CIO context pack 생성

---
