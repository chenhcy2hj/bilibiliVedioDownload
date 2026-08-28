"""无感获取 Cookie：后端弹出真实浏览器窗口 → 用户登录 → 自动捕获保存。

背景：应用页面受同源策略限制，无法读取 bilibili.com 域的 Cookie；
本模块由后端启动持久化浏览器上下文（headful，用户可见用于登录），
登录态就绪后自动抓取 Cookie —— 用户除登录外零操作（无需复制/粘贴/书签）。

体验优化：使用 launch_persistent_context 持久化用户数据目录，
二次触发时若浏览器内登录态仍在，甚至无需重新登录。
"""
import logging
import time
from pathlib import Path
from threading import Event

from app.config import BILI_JUMP_URL

logger = logging.getLogger(__name__)


class BrowserUnavailable(Exception):
    """浏览器组件不可用（未捆绑 playwright/chromium）。"""


COOKIE_ACQUIRE_TIMEOUT_SEC = 300
POLL_INTERVAL_SEC = 2.0

# 在 bilibili.com 页面内探测登录态（同站请求 api.bilibili.com，无跨域问题）
_LOGIN_PROBE_JS = """
(async () => {
  try {
    const resp = await fetch("https://api.bilibili.com/x/web-interface/nav", { credentials: "include" });
    const data = await resp.json();
    if (data && data.code === 0) {
      const uname = data.data && data.data.uname;
      return uname || true;
    }
    return null;
  } catch (e) {
    return null;
  }
})()
"""


class BrowserCookieAcquirer:
    """弹窗等登录 → 返回 bilibili 域 Cookie 字符串（"k=v; k2=v2"）。"""

    def __init__(self, user_data_dir: Path, jump_url: str = BILI_JUMP_URL) -> None:
        self._user_data_dir = user_data_dir
        self._jump_url = jump_url
        self._cancel = Event()

    def cancel(self) -> None:
        self._cancel.set()

    def acquire(self, timeout_sec: int = COOKIE_ACQUIRE_TIMEOUT_SEC) -> str | None:
        """阻塞直到登录成功；超时/取消返回 None。成功返回 cookie 字符串。"""
        self._cancel.clear()
        self._user_data_dir.mkdir(parents=True, exist_ok=True)
        # 惰性导入：打包版若未捆绑 playwright/chromium，给出明确错误而非崩溃
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserUnavailable(
                "当前版本未捆绑浏览器组件，请使用「手动获取」方式粘贴 Cookie"
            ) from exc
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self._user_data_dir),
                headless=False,
                args=["--no-first-run"],
            )
            try:
                page = context.new_page()
                page.goto(self._jump_url, wait_until="domcontentloaded")
                logger.info("Cookie 获取浏览器已弹出: %s", self._jump_url)
                deadline = time.monotonic() + timeout_sec
                while time.monotonic() < deadline:
                    if self._cancel.is_set():
                        return None
                    time.sleep(POLL_INTERVAL_SEC)
                    try:
                        if page.is_closed():
                            return None
                        probe = page.evaluate(_LOGIN_PROBE_JS)
                    except Exception as exc:  # noqa: BLE001 - 页面加载中/跳转中，忽略重试
                        logger.debug("登录态探测未就绪，继续等待: %s", exc)
                        continue
                    if probe:
                        cookie = self._capture(context)
                        if cookie:
                            logger.info("Cookie 捕获成功（登录用户: %s）", probe if isinstance(probe, str) else "?")
                            return cookie
                logger.info("Cookie 获取超时（%ss）", timeout_sec)
                return None
            finally:
                try:
                    context.close()
                except Exception:  # noqa: BLE001
                    logger.debug("浏览器关闭异常（忽略）")

    @staticmethod
    def _capture(context) -> str | None:
        """抓取全部 bilibili 域 Cookie 并组装为原始格式字符串。"""
        try:
            cookies = context.cookies()
        except Exception:  # noqa: BLE001
            return None
        parts = [
            f"{c['name']}={c['value']}"
            for c in cookies
            if "bilibili" in (c.get("domain") or "")
            and c.get("name")
            and c.get("value")
        ]
        return "; ".join(parts) if parts else None