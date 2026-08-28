"""无感获取 Cookie（浏览器捕获）测试：使用 fake acquirer 验证线程/状态/保存。"""
import threading
import time
from pathlib import Path

import pytest

from app.api.errors import ApiError
from app.core.cookie.base import CookieStatus
from app.core.cookie.service import CookieService
from app.core.cookie.store import CookieStore
from app.schemas.cookie import CookieStatusResponse


class FakeAcquirer:
    """测试替身：可控延迟/结果的浏览器捕获器。"""

    def __init__(self, result: str | None, delay: float = 0.1, raise_error: bool = False):
        self._result = result
        self._delay = delay
        self._raise = raise_error
        self.calls = 0

    def acquire(self, timeout_sec: int = 300) -> str | None:
        self.calls += 1
        time.sleep(self._delay)
        if self._raise:
            raise RuntimeError("浏览器崩溃")
        return self._result


class OkValidator:
    def validate(self, cookie: str) -> CookieStatus:
        return CookieStatus(valid=True, uname="测试用户", message="ok")


def make_service(tmp_path: Path, acquirer) -> CookieService:
    store = CookieStore(
        raw_file=tmp_path / "bilibiliCookie.txt",
        netscape_file=tmp_path / "bilibiliCookie_netscape.txt",
        legacy_raw=None,
    )
    return CookieService(validator=OkValidator(), store=store, acquirer=acquirer)


def wait_acquire_done(svc: CookieService, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    status = svc.status()
    while status["acquiring"] and time.time() < deadline:
        time.sleep(0.05)
        status = svc.status()
    return status


class TestAcquireService:
    def test_success_saves_cookie(self, tmp_path):
        svc = make_service(tmp_path, FakeAcquirer("SESSDATA=abc; bili_jct=xyz"))
        assert svc.begin_acquire() is True
        status = wait_acquire_done(svc)
        assert status["acquiring"] is False
        assert status["valid"] is True
        assert status["uname"] == "测试用户"
        assert (tmp_path / "bilibiliCookie.txt").read_text("utf-8") == "SESSDATA=abc; bili_jct=xyz"
        assert (tmp_path / "bilibiliCookie_netscape.txt").exists()

    def test_timeout_no_cookie(self, tmp_path):
        svc = make_service(tmp_path, FakeAcquirer(None))
        svc.begin_acquire()
        status = wait_acquire_done(svc)
        assert status["acquiring"] is False
        assert status["valid"] is False
        assert "超时" in (status["acquire_message"] or "")

    def test_exception_reports_error(self, tmp_path):
        svc = make_service(tmp_path, FakeAcquirer("x", raise_error=True))
        svc.begin_acquire()
        status = wait_acquire_done(svc)
        assert status["acquiring"] is False
        assert "失败" in (status["acquire_message"] or "")

    def test_concurrent_acquire_rejected(self, tmp_path):
        gate = threading.Event()

        class BlockingAcquirer(FakeAcquirer):
            def acquire(self, timeout_sec=300):
                gate.wait(5)
                return "SESSDATA=ok"

        svc = make_service(tmp_path, BlockingAcquirer("SESSDATA=ok"))
        assert svc.begin_acquire() is True
        assert svc.begin_acquire() is False  # 进行中拒绝
        gate.set()
        wait_acquire_done(svc)
        assert svc.begin_acquire() is True  # 完成后可再次发起

    def test_without_acquirer_raises(self, tmp_path):
        store = CookieStore(
            raw_file=tmp_path / "a.txt",
            netscape_file=tmp_path / "b.txt",
            legacy_raw=None,
        )
        svc = CookieService(validator=OkValidator(), store=store)  # 无 acquirer
        with pytest.raises(ApiError) as e:
            svc.begin_acquire()
        assert e.value.code == "ACQUIRE_UNAVAILABLE"


class TestAcquireAPI:
    """API 层：替换 app.state.cookie 为 fake，避免真实弹窗。"""

    def test_acquire_endpoint_flow(self, tmp_path):
        from fastapi.testclient import TestClient

        from app.main import app

        fake = make_service(tmp_path, FakeAcquirer("SESSDATA=api-test"))
        original = app.state.cookie
        app.state.cookie = fake
        client = TestClient(app)
        try:
            r = client.post("/api/cookie/acquire")
            assert r.status_code == 200
            body = CookieStatusResponse.model_validate(r.json())
            assert body.acquiring is True or body.valid is True
            # 等待后台完成
            deadline = time.time() + 5
            while body.acquiring and time.time() < deadline:
                time.sleep(0.05)
                body = CookieStatusResponse.model_validate(client.get("/api/cookie/status").json())
            assert body.valid is True
            assert body.uname == "测试用户"

            # 进行中重复请求 → 409
            gate = threading.Event()

            class Slow(FakeAcquirer):
                def acquire(self, timeout_sec=300):
                    gate.wait(5)
                    return "SESSDATA=x"

            fake2 = make_service(tmp_path, Slow("SESSDATA=x"))
            app.state.cookie = fake2
            assert client.post("/api/cookie/acquire").status_code == 200
            r2 = client.post("/api/cookie/acquire")
            assert r2.status_code == 409
            gate.set()
        finally:
            app.state.cookie = original