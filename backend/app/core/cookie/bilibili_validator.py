"""Bilibili Cookie 校验：请求 /x/web-interface/nav 判断登录态。"""
import httpx

from app.config import BILI_NAV_URL, REFERER, UA
from app.core.cookie.base import CookieCheckError, CookieStatus, CookieValidator


class BilibiliCookieValidator(CookieValidator):
    def validate(self, cookie: str) -> CookieStatus:
        headers = {
            "User-Agent": UA,
            "Referer": REFERER,
            "Cookie": cookie,
        }
        try:
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                resp = client.get(BILI_NAV_URL, headers=headers)
                data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise CookieCheckError(f"校验请求失败: {e}")

        code = data.get("code")
        if code == 0:
            uname = (data.get("data") or {}).get("uname") or "未知用户"
            return CookieStatus(valid=True, uname=uname, message="Cookie 有效")
        if code == -101:
            return CookieStatus(valid=False, message="未登录或 Cookie 已失效，请重新获取")
        return CookieStatus(valid=False, message=f"B站接口返回异常(code={code})")