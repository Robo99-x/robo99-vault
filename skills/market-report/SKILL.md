---
name: market-report
description: 미장 마감 리포트 생성. KST 07:00 cron 또는 수동 요청 시 사용.
user-invocable: true
---

# 미장 마감 리포트

## 데이터 수집

```bash
cd scripts && uv run python scripts/collect_market_data.py
# → alerts/market_snapshot_YYYYMMDD.json
```

## 리포트 포맷

```
📊 미장 마감 리포트 (MM/DD)

■ 주요 지수
S&P 500: 5,xxx.xx (+x.x%) | 나스닥: xx,xxx (+x.x%) | 다우: xx,xxx (+x.x%)
VIX: xx.xx

■ 매크로
10Y: x.xx% | DXY: xxx.xx | WTI: $xx.xx
USD/KRW: x,xxx | USD/JPY: xxx.xx

■ 섹터
기술 +x.x% | 금융 +x.x% | 에너지 +x.x% | 헬스케어 +x.x%

■ 특이사항
- (주요 이벤트 1~3줄)

■ 주의 포인트
- (한국 시장 영향 1줄)
```

## 실적 해석

실적 발표 시: FMP 데이터 → 컨센서스 대비 → 시간외 반응 → 2~3문장 해석

## 발송

텔레그램으로 발송. 원본은 `alerts/report_YYYYMMDD.md`에 저장.
