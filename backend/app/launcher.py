"""桌面应用启动入口（M6 打包版）：

1. uvicorn 绑定 127.0.0.1:0（动态端口，避免冲突）；
2. 生成随机 token 注入前端（URL query），后端按 HTTP Header / WS query 校验，
   防止本机其他进程调用（token 不落日志）；
3. pywebview 窗口加载前端页面；启动失败直接报错退出（不做浏览器降级）；
4. 暴露 js_api（choose_dir 原生目录选择），供设置面板使用。

开发模式：不要通过本文件启动（直接 uvicorn app.main:app），此时无 token 校验。
"""
import io
import logging
import os
import secrets
import sys
import threading
import time
from pathlib import Path

import uvicorn

from app.config import DATA_DIR, is_packaged


def _ensure_stdio() -> None:
    """windowed 模式（PyInstaller console=False）下 sys.stdout/stderr 为 None：
    uvicorn 日志配置访问 isatty() 直接崩溃（Windows 真机实测 ValueError）。
    替换为哑对象（isatty=False），打印/日志静默丢弃。
    """
    if sys.stdout is not None and sys.stderr is not None:
        return

    class _NullWriter(io.TextIOBase):
        def isatty(self) -> bool:
            return False

        def write(self, s: str) -> int:
            return len(s)

        def flush(self) -> None:
            pass

    if sys.stdout is None:
        sys.stdout = _NullWriter()
    if sys.stderr is None:
        sys.stderr = _NullWriter()
    logging.getLogger(__name__).debug("stdio 已替换为哑对象（windowed 模式）")


def _fatal(message: str) -> None:
    """GUI 模式（console=False）下 print 不可见，用系统弹窗告知用户。"""
    import subprocess

    if sys.platform == "darwin":
        subprocess.run(
            ["osascript", "-e", f'display dialog "{message}" buttons {{"OK"}}'],
            check=False,
        )
    elif sys.platform.startswith("win"):
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "BiliDownloader", 0x10)
    print(f"[FATAL] {message}", file=sys.stderr)
    raise SystemExit(1) from None


def main() -> None:
    # windowed 模式 stdio 为 None：必须在任何日志/uvicorn 初始化之前替换（Windows 实测崩溃点）
    _ensure_stdio()

    # P5：打包版浏览器指向包内捆绑目录（sys._MEIPASS/_browsers），恢复无感获取；
    # 必须在 import app.main（browser 惰性 import）之前设置；开发模式走系统缓存不设置。
    if is_packaged():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.argv[0]).resolve().parent))
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(base / "_browsers"))

    # 调试/验证可用环境变量指定 token（正式运行随机生成）
    token = os.environ.get("BILIDL_LAUNCHER_TOKEN") or secrets.token_hex(16)

    from app.main import app

    app.state.auth_token = token  # 全局中间件据此校验

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, log_level="info")
    )
    threading.Thread(target=server.run, daemon=True, name="uvicorn").start()
    while not server.started:
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]

    try:
        import webview

        from app.pywebview_api import DesktopApi
    except Exception as exc:  # noqa: BLE001 - GUI 组件缺失属致命错误
        _fatal(f"窗口组件初始化失败: {exc}")

    webview.create_window(
        "BiliDownloader",
        url=f"http://127.0.0.1:{port}/?token={token}",
        js_api=DesktopApi(),
        width=1200,
        height=820,
        min_size=(900, 600),
        background_color="#f8fafc",
    )
    # 数据目录仅做初始化（打包版首次启动）
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        webview.start()
    except Exception as exc:  # noqa: BLE001 - 窗口启动失败必须让用户明确知道
        _fatal(f"窗口启动失败: {exc}")


if __name__ == "__main__":
    main()