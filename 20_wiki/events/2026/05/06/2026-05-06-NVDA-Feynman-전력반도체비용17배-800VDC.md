---
schema_version: 1
type: event
status: draft
date: 2026-05-06
source: telegram
source_file: "00_inbox/2026/05/06/2026-05-06-120036-telegram-raw.md"
entities:
  - DB하이텍(000990)
  - 삼성전기(009150)
  - RFHIC(218410)
themes:
  - AI인프라
  - 전력반도체
  - GaN
  - SiC
  - 데이터센터
catalyst_type:
  - 신제품
  - 업황회복
market_reaction:
  direction: unknown
  strength: unknown
confidence: medium
risk_hypothesis:
  - "Feynman은 2028년 출시 예정으로 2년 이상 남은 로드맵이며, 지금 주가에 선반영되는 정도가 과도할 수 있음"
  - "Morgan Stanley 리포트 기반 추정치이며, 실제 양산 시 비용 구성이 달라질 가능성 존재"
  - "국내 SiC·GaN 기업의 엔비디아 공급망 진입 여부가 확인되지 않은 상태에서 테마 편입 위험"
invalidates_if:
  - "엔비디아가 800VDC 아키텍처 채택 일정을 지연·변경하거나 대안 설계(48V 유지)를 발표하는 경우"
  - "DB하이텍·삼성전기 등이 관련 공급망에 진입하지 못하거나 해외 경쟁사(온세미, 인피니언)가 독점하는 경우"
skip_reason:
integration_notes:
---

## 확인된 사실

- Morgan Stanley 분석: 엔비디아 GPU 세대별 랙당 전력 반도체 비용 — Blackwell 11,234달러 → Feynman 191,000달러 (17배 증가)
- Feynman 전력 반도체 구성: PCS 27%, VRM 26%, PSU 19%, 측면VRM 15%, IBC 5%, BBU/UPS 5%
- 800VDC 아키텍처 최초 도입: Kyber 랙 (Rubin Ultra GPU, 2027년 예정)
- Feynman 출시 예정: 2028년
- 기존 48V/54V 방식 한계: 1MW 랙에 구리 부스바 200kg 필요, 공간 잠식
- 출처: Wccftech (2026.05.04) — Morgan Stanley 리포트 인용, 1차 소스 아님

## 사건

엔비디아가 2027년 Kyber(Rubin Ultra)부터 800VDC 아키텍처를 도입하며, 2028년 Feynman까지 랙당 전력 반도체 비용이 Blackwell 대비 17배로 증가한다. PCS·VRM·PSU 중심의 고전압 GaN·SiC 전력 반도체 수요가 폭발적으로 확대될 전망이다.

## 해석

- AI 인프라의 전력 반도체 TAM이 2028년까지 기하급수적으로 확대되는 구조적 트렌드 확인
- GaN·SiC 전력 반도체 업체(온세미, 인피니언, 울프스피드, 로옴)가 1차 수혜
- 한국 관련: DB하이텍은 SiC 파운드리 사업 확대 중으로 간접 수혜 가능성. RFHIC는 GaN 기반이나 RF 중심으로 직접 수혜 제한적
- VRM 핵심 부품인 MLCC·인덕터 수요 급증 → 삼성전기 MLCC 부문 간접 수혜
- 2027~2028 로드맵이므로 2026년 주가 반영은 선행 기대감 영역

## 확인할 것

- DB하이텍의 SiC 웨이퍼·에피텍시 공급망에서 엔비디아향 납품 여부 또는 가능성
- 삼성전기 MLCC의 800VDC 고전압 스펙 대응 제품군 현황
- 국내 VRM 전문 업체 존재 여부 (현재 미파악)
- Morgan Stanley 원본 리포트 세부 내용 (Wccftech 2차 인용이므로 수치 검증 필요)

## 연결

- [[DB하이텍]]
- [[삼성전기]]
- [[RFHIC]]
- [[AI인프라]]
- [[전력반도체]]
- [[GaN]]
- [[SiC]]
