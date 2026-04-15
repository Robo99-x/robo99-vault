---
name: market-monitor
description: 주식/환율/뉴스 모니터링 알림 등록, 조회, 삭제
user-invocable: true
---

# 시장 모니터링 알림

사용자가 "~하면 알려줘" 류의 요청을 하면 이 스킬 사용.
**절대 openclaw cron을 직접 만들지 마.** 모든 모니터링은 alert_manager.py를 통해.

## 데몬 상태 확인
tmux로 monitor-daemon 세션이 활성화 되었는지 파악하고, 세션이 없거나 세션 내 데몬 스크립트가 돌아가고 있지 않을 경우에는 tmux 세션으로 직접 데몬 실행.
```bash
cd scripts && uv run monitor_daemon.py
```

## 종목 가격 알림
```bash
cd scripts && uv run python alert_manager.py add-stock \
  --ticker <종목코드> --threshold <퍼센트> --market <kr|jp|cn|us>
```

## 환율 알림
```bash
cd scripts && uv run python alert_manager.py add-fx --pair USDJPY --threshold 3
```

## 뉴스 키워드
```bash
cd scripts && uv run python alert_manager.py add-news --term "부양책" --market cn
```

## 조회/삭제
```bash
cd scripts
uv run python alert_manager.py list
uv run python alert_manager.py remove --id <alert_id>
```

## 기본 내장 조건 (데몬)

- 중국: 시총 ~1조원↑, ±8%
- 일본: 대형주 ±8%
- USD/JPY: ±3%
