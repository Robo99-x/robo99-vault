---
source: telegram
channel: cahier_de_market
message_id: 10163
date: 2026-07-20
datetime: 2026-07-20T19:54:25 KST
sender: cahier_de_market
processed: false
---

* **Deep|LLM : Kimi K3의 KV 캐시는 더 작다
 - 그런데 이것이 오히려 DRAM/NAND에 긍정적일 수 있는 이유**


**K3는 여전히 대규모 메모리를 요구하는 모델이다.**
- Kimi K3는 총 2.8조 개의 파라미터를 보유하고 있으며, 토큰당 896개 전문가 중 16개를 활성화한다. Moonshot은 최소 64개의 가속기로 구성된 고대역폭 슈퍼노드에서의 배포를 권장한다. KV 캐시가 작아졌다고 해서 전체 메모리 및 네트워크 수요가 감소한다는 의미는 아니다. K3는 여전히 HBM급 메모리 용량과 스케일업 네트워킹, GPU를 필요로 한다.

**KV 오프로드는 압축이 이뤄져야 비로소 실용적이 된다.**
- 압축되지 않은 대규모 KV 캐시는 PCIe, NIC, SSD의 지연시간 때문에 활성 디코딩 경로에 배치하기 어렵다. 데이터를 외부 메모리에서 불러오는 지연으로 인해, 프리필을 다시 계산하는 것보다 오히려 비효율적일 수 있기 때문이다. KV 압축은 DRAM, NAND, 네트워크를 통해 이동해야 하는 데이터의 양을 줄여준다. 이에 따라 KV 오프로드는 단순히 이론적인 용량 확장 수단에서 실제 배포 가능한 아키텍처로 전환된다.

**DRAM/NAND에 대한 시사점**
- 핵심적인 변화는 KV 캐시가 사라지는 것이 아니라, **KV 캐시가 HBM, DRAM, NAND, 네트워크에 걸쳐 계층적으로 관리되는 데이터 자산으로 바뀌고 있다는 점이다**. 
-** DRAM은 웜 캐시와 데이터 스테이징 계층으로서 중요성이 높아지며, NAND는 과거 세션, 여러 사용자가 공유하는 프리픽스, 비활성 상태의 KV 캐시를 저장하는 대규모 풀로 활용**될 수 있다.



https://open.substack.com/pub/fundaai/p/deepllm-kimi-k3s-kv-cache-is-smaller?utm_source=share&utm_medium=android&r=6hkvpp