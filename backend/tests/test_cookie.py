"""Cookie 模块测试：validator（mock 网络）、store 转换格式、service 组合逻辑。"""
from pathlib import Path

import pytest

from app.api.errors import ApiError
from app.core.cookie.base import CookieCheckError, CookieStatus
from app.core.cookie.bilibili_validator import BilibiliCookieValidator
from app.core.cookie.service import CookieService
from app.core.cookie.store import CookieStore


def make_store(tmp_path: Path) -> CookieStore:
    return CookieStore(
        raw_file=tmp_path / "bilibiliCookie.txt",
        netscape_file=tmp_path / "bilibiliCookie_netscape.txt",
        legacy_raw=None,
    )


class FakeValidator:
    """测试替身：按注入结果返回。"""

    def __init__(self, status: CookieStatus):
        self._status = status

    def validate(self, cookie: str) -> CookieStatus:
        return self._status


class TestValidator:
    def test_valid(self, monkeypatch):
        class FakeResp:
            def json(self):
                return {"code": 0, "data": {"uname": "测试用户"}}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, **k):
                return FakeResp()

        import httpx

        monkeypatch.setattr(httpx, "Client", FakeClient)
        status = BilibiliCookieValidator().validate("SESSDATA=abc")
        assert status.valid
        assert status.uname == "测试用户"

    def test_invalid(self, monkeypatch):
        class FakeResp:
            def json(self):
                return {"code": -101, "message": "账号未登录"}

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, **k):
                return FakeResp()

        import httpx

        monkeypatch.setattr(httpx, "Client", FakeClient)
        status = BilibiliCookieValidator().validate("SESSDATA=expired")
        assert not status.valid

    def test_network_error_raises(self, monkeypatch):
        import httpx

        class BoomClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, **k):
                raise httpx.ConnectError("network down")

        monkeypatch.setattr(httpx, "Client", BoomClient)
        with pytest.raises(CookieCheckError):
            BilibiliCookieValidator().validate("SESSDATA=x")


class TestStore:
    def test_save_and_netscape_format(self, tmp_path):
        store = make_store(tmp_path)
        store.save_raw("SESSDATA=abc; bili_jct=xyz; DedeUserID=1")
        raw = (tmp_path / "bilibiliCookie.txt").read_text("utf-8")
        assert raw == "SESSDATA=abc; bili_jct=xyz; DedeUserID=1"

        netscape = (tmp_path / "bilibiliCookie_netscape.txt").read_text("utf-8")
        assert "Netscape HTTP Cookie File" in netscape
        assert ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tabc" in netscape
        assert ".bilibili.com\tTRUE\t/\tFALSE\t0\tDedeUserID\t1" in netscape

    def test_has_cookie_and_read(self, tmp_path):
        store = make_store(tmp_path)
        assert not store.has_cookie()
        store.save_raw("a=b")
        assert store.has_cookie()
        assert store.read_raw() == "a=b"
        assert store.read_netscape() is not None

    def test_legacy_root_fallback(self, tmp_path):
        legacy = tmp_path / "bilibiliCookie.txt"
        legacy.write_text("old=1", encoding="utf-8")
        store = CookieStore(
            raw_file=tmp_path / "data" / "bilibiliCookie.txt",
            netscape_file=tmp_path / "data" / "bilibiliCookie_netscape.txt",
            legacy_raw=legacy,
        )
        assert store.has_cookie()
        assert store.read_raw() == "old=1"


class TestService:
    def test_submit_valid_saves(self, tmp_path):
        svc = CookieService(FakeValidator(CookieStatus(True, "U1", "ok")), make_store(tmp_path))
        resp = svc.submit("SESSDATA=good")
        assert resp["valid"]
        assert resp["uname"] == "U1"
        assert (tmp_path / "bilibiliCookie.txt").exists()
        assert (tmp_path / "bilibiliCookie_netscape.txt").exists()

    def test_submit_invalid_rejected(self, tmp_path):
        svc = CookieService(FakeValidator(CookieStatus(False, message="失效")), make_store(tmp_path))
        with pytest.raises(ApiError) as e:
            svc.submit("SESSDATA=bad")
        assert e.value.code == "COOKIE_INVALID"

    def test_submit_empty_rejected(self, tmp_path):
        svc = CookieService(FakeValidator(CookieStatus(True, "U", "ok")), make_store(tmp_path))
        with pytest.raises(ApiError) as e:
            svc.submit("   ")
        assert e.value.code == "COOKIE_INVALID"

    def test_status_without_cookie(self, tmp_path):
        svc = CookieService(FakeValidator(CookieStatus(True, "U", "ok")), make_store(tmp_path))
        resp = svc.status()
        assert not resp["valid"]
        assert "尚未配置" in resp["message"]

    def test_status_with_stored_cookie(self, tmp_path):
        store = make_store(tmp_path)
        store.save_raw("SESSDATA=x")
        svc = CookieService(FakeValidator(CookieStatus(True, "U1", "ok")), store)
        resp = svc.status()
        assert resp["valid"]
        assert resp["uname"] == "U1"