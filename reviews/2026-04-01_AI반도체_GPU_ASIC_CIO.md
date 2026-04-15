---
date: 2026-04-01
tickers: SK하이닉스(000660), 삼성전기(009150), 한미반도체(042700), 삼성전자(005930)
agents: optimus, geek
conclusion: CIO Score 7.6 / 10 — JPMorgan GPU/ASIC 리포트. SK하이닉스·삼성전기·한미반도체 집중. AI 반도체 수혜 구조 선명.
---

# CIO 브리핑 — JPMorgan GPU/ASIC Foodchain
출처: JPMorgan Asia Semis 260401 | 2026-04-01

---

## 원문 핵심 요약

1. **Rubin Ultra 4-Die → 2x2 구조 변경 가능성**
   - HBM 1TB 용량 유지, 컴퓨트 성능 무변화
   - 더 큰 ABF Substrate 필요 → 삼성전기 수혜
   - CoWoS 복잡도 감소, 수율 개선 가능

2. **LPX(Groq) 출하 전망**
   - 2026년 500K, Rack 2,000개 수준
   - LP30/35: 삼성파운드리 4nm / LP40: TSMC N3 + CoWoS-R
   - CPX 수요 저조 — 고객이 Rubin GPU 대비 차별성 부족 인식

3. **Trainium 3/4**
   - Trainium 3: 2Q26 램프업 순항. Alchip $1.5B 매출. 출하량 3mn
   - Anthropic: Claude Code + Opus 4.5 출시 후 토큰 급증 → Trainium 수요 강세
   - Trainium 4: 2nm Compute + 3nm I/O Die + HBM 12hi. Alchip 백엔드. 27년 테이프아웃, 28년 양산

4. **Zebrafish (MediaTek × Google TPU v8)**
   - 2Q26 말 TSMC 램프업, 4Q26 매출 인식 시작
   - 2026년 $1B → 2027년 $4~7B (CoWoS 60~100K)
   - 경미한 ECO 이슈 해결 완료

5. **TPU v9**
   - Humufish: MediaTek + Intel EMIB-T + 3D SoIC (리스크 높음)
   - Pumafish: Broadcom + TSMC CoWoS-L (우위)
   - MediaTek: 300G SerDes vs Broadcom: 400G SerDes → 성능 열위

---

## 🗣️ 옵티머스 (드러켄밀러 시각)

**거시 레짐 판단:**
AI 인프라 투자 사이클이 칩 설계 → 패키징 → 소재까지 전방위 확산. Rubin Ultra, Trainium 3/4, Zebrafish, TPU v9가 동시에 램프업하는 "슈퍼사이클 동시다발" 구간. 12~18개월 후 시장은 CoWoS 공급 병목과 HBM 12hi 전환을 메인 테마로 인식할 것.

**베팅 가설:**
① Rubin Ultra 2x2 → ABF Substrate 대형화 수혜
② Trainium 3 2Q26 + Claude Code 토큰 급증 → HBM 수요 직결
③ TPU v9 Broadcom 우세 → TSMC CoWoS-L 수혜

**모멘텀 방향:**
삼성파운드리 LP30/35 수혜이나 LP40 TSMC N3 이동은 중기 점유율 위협. SK하이닉스 HBM 모멘텀 가장 명확.

**Conviction: 8 / 10**

---

## 🔬 Geek (퀀트/리스크)

**국내 종목별 임팩트:**

| 종목 | 임팩트 | 근거 |
|------|--------|------|
| SK하이닉스(000660) | ★★★ 직접수혜 | HBM 1TB 유지 + HBM 12hi(T4) + Trainium 수요 강세 |
| 삼성전기(009150) | ★★★ 직접수혜 | ABF Substrate 대형화 수혜 |
| 한미반도체(042700) | ★★ 수혜 | Zebrafish CoWoS 60~100K TC본더 수요 |
| 삼성전자(005930) | ★ 양면 | 파운드리 LP30/35 수혜 vs LP40 TSMC 이동 위협 |

**리스크 팩터:**
1. Zebrafish ECO 추가 지연 시 CoWoS 타이밍 밀림
2. MediaTek EMIB 실패 시 TPU v9 구도 조기 결정
3. AI 투자 버블 논쟁 (CAPEX 과잉 우려)

**무효화 조건:** 빅테크 CAPEX 컷 발표 or NVIDIA Blackwell 공급 정상화로 ASIC 수요 급감

**RiskScore: 3 / 10** (낮음)

---

## 📊 CIO 통합 판단

CIO Score = (8 × 0.6) + ((10-3) × 0.4) = 4.8 + 2.8 = **7.6 / 10**
권장 비중 = 7.6 × 2% = **최대 15%**

**결론:**
AI 반도체 수혜 구조 선명. SK하이닉스·삼성전기·한미반도체 3종 집중. 삼성전자는 파운드리 점유율 위협 감안해 비중 축소 방향.

**후속 모니터링:**
- Trainium 3 2Q26 실제 램프업 확인
- Zebrafish 4Q26 매출 인식 시작 여부
- Rubin Ultra 2x2 구조 변경 공식 확인
