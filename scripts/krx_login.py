"""krx_login.py — KRX 로그인 세션을 pykrx webio에 주입

pykrx PR#282의 auth.py를 활용해 실제 로그인 세션을 생성하고,
webio.Post/Get의 requests 호출을 세션 기반으로 교체.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger("krx_login")

SECRETS_PATH = Path.home() / "robo99_hq" / "secrets" / "krx_login.json"


def _load_credentials() -> tuple[str, str]:
    if not SECRETS_PATH.exists():
        raise FileNotFoundError(f"KRX 크리덴셜 없음: {SECRETS_PATH}")
    data = json.loads(SECRETS_PATH.read_text())
    return data["id"], data["pw"]


def login_krx() -> bool:
    """KRX 로그인 세션 생성 후 pykrx webio에 주입. 성공 시 True."""
    try:
        login_id, login_pw = _load_credentials()
    except Exception as e:
        log.error(f"크리덴셜 로드 실패: {e}")
        return False

    try:
        from pykrx.website.comm.auth import build_krx_session
        from pykrx.website.comm import webio

        session = build_krx_session(login_id, login_pw)
        if session is None:
            log.warning("KRX 세션 생성 실패 (ID/PW 없음)")
            return False

        # webio.Post.read / Get.read를 session 기반으로 monkey-patch
        original_post = webio.Post.read
        original_get = webio.Get.read

        def patched_post(self, **params):
            resp = session.post(self.url, headers=self.headers, data=params, timeout=30)
            return resp

        def patched_get(self, **params):
            resp = session.get(self.url, headers=self.headers, params=params, timeout=30)
            return resp

        webio.Post.read = patched_post
        webio.Get.read = patched_get

        log.info("KRX 세션 주입 완료")
        return True

    except Exception as e:
        log.error(f"KRX 로그인/주입 실패: {e}")
        return False
