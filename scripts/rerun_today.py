#!/usr/bin/env python3
"""
rerun_today.py — 누락/실패 작업 수동 재처리

1. 장전 브리핑: 저장된 stdout → vault_writer 파이프라인 (텔레그램 전송)
   - 이미 처리된 .md 파일이면 스킵 (already done 표시)
2. stage2_scanner 재실행 → geek_filter → stage2_briefing (텔레그램 전송)

사용: uv run --with pyyaml --with requests python rerun_today.py
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib import config as _cfg  # noqa: E402
BASE = _cfg.BASE

TODAY = datetime.now().strftime("%Y-%m-%d")


def rerun_premarket():
    """저장된 premarket stdout → vault_writer 재처리. 이미 처리됐으면 스킵."""
    print(f"\n=== [1/3] 장전 브리핑 재처리 ({TODAY}) ===")

    saved = BASE / "alerts" / f"premarket_briefing_{TODAY}.md"
    if not saved.exists():
        print(f"❌ 파일 없음: {saved}")
        return False

    raw = saved.read_text()
    print(f"📄 파일 크기: {len(raw)} chars")

    # 이미 vault_writer 처리된 파일인지 확인 (YAML frontmatter 존재)
    if raw.startswith("---") and "briefing_type: premarket" in raw:
        print("✅ 이미 처리 완료된 파일 (vault_writer frontmatter 감지) — 스킵")
        return True

    # JSON 추출
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        raw_json = m.group(1).strip()
    elif raw.strip().startswith("{"):
        raw_json = raw.strip()
    else:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            raw_json = raw[start:end + 1]
        else:
            print("❌ JSON 추출 실패")
            return False

    print(f"🔍 추출된 JSON: {len(raw_json)} chars")

    from vault_writer import VaultWriter
    vw = VaultWriter(base_dir=BASE)
    result = vw.process_premarket(raw_json, run_id=f"premarket_{TODAY}_rerun")

    print(f"📋 결과: {json.dumps({k: v for k, v in result.items() if k != 'warnings'}, ensure_ascii=False)}")
    if result.get("warnings"):
        print(f"⚠️ 경고: {result['warnings']}")

    if result.get("success"):
        print("✅ 장전 브리핑 재처리 성공" + (" (텔레그램 전송됨)" if result.get("telegram") else " (텔레그램 실패)"))
    else:
        print(f"❌ 실패: {result.get('error', 'unknown')}")
        if result.get("quarantine"):
            print(f"🔒 quarantine: {result['quarantine']}")

    return result.get("success", False)


def rerun_stage2():
    """stage2_scanner → geek_filter → stage2_briefing (텔레그램) 순서 실행."""
    print("\n=== [2/3] stage2_scanner 재실행 ===")

    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < 4096:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (min(4096, hard), hard))
        except Exception:
            pass

    r = subprocess.run(
        ["uv", "run", "python", "stage2_scanner.py"],
        cwd=str(SCRIPTS), capture_output=True, text=True, timeout=480,
    )
    if r.returncode != 0:
        print(f"❌ stage2_scanner 실패:\n{r.stderr[:500]}")
        return False
    print("✅ stage2_scanner 완료")

    print("\n=== [3/3] geek_filter + stage2_briefing (텔레그램 전송) ===")
    r = subprocess.run(
        ["uv", "run", "python", "geek_filter.py"],
        cwd=str(SCRIPTS), capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        print(f"❌ geek_filter 실패:\n{r.stderr[:300]}")
        return False
    print("✅ geek_filter 완료")

    r = subprocess.run(
        ["uv", "run", "python", "stage2_briefing.py"],
        cwd=str(SCRIPTS), capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        print(f"❌ stage2_briefing 실패:\n{r.stderr[:300]}")
        return False
    print("✅ stage2_briefing 완료 (텔레그램 전송됨)")
    return True


if __name__ == "__main__":
    ok1 = rerun_premarket()
    ok2 = rerun_stage2()

    print("\n=== 결과 요약 ===")
    print(f"  장전 브리핑:    {'✅' if ok1 else '❌'}")
    print(f"  stage2 파이프라인: {'✅' if ok2 else '❌'}")

    if not (ok1 and ok2):
        sys.exit(1)
