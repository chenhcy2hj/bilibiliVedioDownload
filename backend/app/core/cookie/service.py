"""CookieService：组合 校验 + 存储 + 转换 + 无感获取（浏览器捕获），面向 API 层统一入口。"""
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.api.errors import ApiError
from app.core.cookie.base import CookieCheckError, CookieStatus, CookieValidator
from app.core.cookie.browser import BrowserCookieAcquirer
from app.core.cookie.store import CookieStore

logger = logging.getLogger(__name__)


class CookieService:
    def __init__(
        self,
        validator: CookieValidator,
        store: CookieStore,
        acquirer: BrowserCookieAcquirer | None = None,
    ) -> None:
        self._validator = validator
        self._store = store
        self._acquirer = acquirer
        self._acquiring = False
        self._acquire_error: str | None = None
        self._acquire_lock = threading.Lock()

    def get_cookie_file(self) -> Path | None:
        """供下载器使用的 Netscape cookie 文件路径；无则 None。"""
        return self._store.read_netscape()

    def is_valid(self, cookie: str | None = None) -> CookieStatus:
        """校验当前已存 Cookie（或指定 Cookie）的有效性。"""
        if cookie is None:
            cookie = self._store.read_raw()
        if not cookie:
            return CookieStatus(valid=False, message="尚未配置 Cookie，请先获取")
        if not cookie.strip():
            return CookieStatus(valid=False, message="Cookie 为空，请重新获取")
        try:
            return self._validator.validate(cookie)
        except CookieCheckError as e:
            # 网络异常不算"已失效"，返回不可校验状态
            return CookieStatus(valid=False, message=f"无法校验 Cookie（网络异常）: {e}")

    def submit(self, cookie: str) -> dict:
        """校验 → 有效则保存并自动转换 Netscape → 返回状态。"""
        cookie = cookie.strip()
        if not cookie:
            raise ApiError("COOKIE_INVALID", "Cookie 不能为空", status_code=422)
        try:
            status = self._validator.validate(cookie)
        except CookieCheckError as e:
            raise ApiError("COOKIE_CHECK_FAILED", f"校验失败（网络异常）: {e}", status_code=502)
        if not status.valid:
            raise ApiError("COOKIE_INVALID", status.message, status_code=422)

        self._store.save_raw(cookie)  # 内部会写入原始 + 转换 Netscape
        return self._to_response(status)

    # ---- 无感获取（Playwright 弹窗捕获） ----

    def begin_acquire(self) -> bool:
        """启动无感获取（后台线程，立即返回）；已有获取进行中返回 False。"""
        if self._acquirer is None:
            raise ApiError("ACQUIRE_UNAVAILABLE", "当前环境不支持浏览器获取（打包版请使用手动方式）", status_code=501)
        with self._acquire_lock:
            if self._acquiring:
                return False
            self._acquiring = True
            self._acquire_error = None
        threading.Thread(target=self._acquire_worker, daemon=True, name="cookie-acquire").start()
        return True

    def _acquire_worker(self) -> None:
        try:
            cookie = self._acquirer.acquire()
            if cookie:
                self._store.save_raw(cookie)  # 捕获成功 → 自动保存 + 转 Netscape
                logger.info("无感获取 Cookie 成功")
            else:
                self._acquire_error = "获取未完成（超时或窗口已关闭），请重试"
        except Exception as e:
            logger.exception("无感获取 Cookie 异常")
            self._acquire_error = f"浏览器获取失败: {e}"
        finally:
            self._acquiring = False

    def status(self) -> dict:
        status = self.is_valid()
        resp = self._to_response(status)
        resp["acquiring"] = self._acquiring
        resp["acquire_message"] = (
            "正在等待登录：请在弹出的浏览器窗口中完成登录，Cookie 将自动保存"
            if self._acquiring
            else self._acquire_error
        )
        return resp

    def _to_response(self, status: CookieStatus) -> dict:
        return {
            "valid": status.valid,
            "uname": status.uname,
            "message": status.message,
            "has_cookie_file": self._store.has_cookie(),
            "updated_at": datetime.now(timezone.utc) if status.valid else None,
        }