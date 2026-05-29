---
source: telegram
channel: cahier_de_market
message_id: 9639
date: 2026-05-29
datetime: 2026-05-29T08:57:52 KST
sender: cahier_de_market
processed: false
---

*** Datacurve가 발표한 새로운 코딩 벤치마크 표준 'DeepSWE'**

- 이 벤치마크 기준으로 모델들을 평가한 결과 위 그림과 같은 다소 충격적 결과가 나옴

- **GPT 5.5가 70%의 압도적인 포인트를 달성**했고
- Claude Opus 4.7은 54%에 불과, 나머지 다른 모델들은 한참 뒤떨어진 점수를 보임(최근 런칭한 딥시크 V4 Pro는 경쟁의 축에도 끼기 불가능한 점수)

- Datacurve가 밝히는 DeepSWE 표준이 기존 SWE-Bench류 기준들과 다른 점 :

**1) 학습 데이터 오염 가능성이 낮음.** 기존 GitHub PR이나 커밋을 그대로 가져온 문제가 아니라, 과제를 새로 만들고 reference solution도 새로 작성. 그래서 모델이 사전학습 중 정답 패치를 미리 학습했을 가능성을 줄임

**2) 과제 다양성이 크다.** DeepSWE는 91개 오픈소스 레포지토리, 113개 과제, 5개 언어(TypeScript, Go, Python, JavaScript, Rust)를 포함. 반면 SWE-Bench Pro Public은 11개, SWE-Bench Verified는 12개 레포 중심

**3) 실제 개발 업무에 더 가까운 장기 과제 중심의 평가.** 프롬프트는 SWE-Bench Pro보다 짧지만, 실제 해결에는 훨씬 많은 코드 수정이 필요. 

**4) 검증 방식이 더 '행동 중심'.** 특정 내부 함수명이나 구현 방식을 맞혔는지가 아니라, public API와 관찰 가능한 동작이 맞는지를 테스트.


**
* 이 벤치마크 결과의 함의**

**1)** **AI 코딩 에이전트 시장은 아직 'benchmark saturation' 상태가 아니다**. 즉, 기존 SWE-Bench류에서 모델들이 비슷해 보였더라도, 더 **현실적인 장기 과제에서는 성능 격차가 크게 벌어진다는 점을 확인.** 

**2) 이는 상위 모델 사업자에게 성능 차별화, 가격결정력의 여지가 존재**하고, 모델들의 **성능 개선 룸 또한 더욱 많이 남아있다는 의미**

**3) KV 캐시의 과한 압축과 비용 효율화에 중점을 둔 DeepSeek와 같은 모델들은 장기과제 수행능력에서 열위를 보일 수 밖에 없다**


https://deepswe.datacurve.ai/blog