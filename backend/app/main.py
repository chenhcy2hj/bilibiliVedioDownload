"""FastAPI 应用入口：组装各模块单例、路由、CORS、token 鉴权与错误处理。

- 前端构建产物存在时托管静态文件（同一端口访问，M4）；
- token 鉴权（M6 打包版）：launcher 设置 app.state.auth_token 后，
  HTTP 请求须携带 X-Auth-Token、WS 连接须携带 ?token=，否则拒绝；
  开发模式（不经 launcher）auth_token 为 None → 不校验。
"""
import sys
from pathlib import Path

import yt_dlp
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import capabilities, cookie, settings_route, tasks, ws
from app.api.errors import register_error_handlers
from app.config import (
    APP_NAME,
    APP_VERSION,
    COOKIE_NETSCAPE_FILE,
    COOKIE_RAW_FILE,
    DATA_DIR,
    DEFAULT_OUTPUT_DIR,
    LEGACY_COOKIE_RAW,
    SETTINGS_FILE,
    is_packaged,
)
from app.core.cookie.bilibili_validator import BilibiliCookieValidator
from app.core.cookie.browser import BrowserCookieAcquirer
from app.core.cookie.service import CookieService
from app.core.cookie.store import CookieStore
from app.core.dirs import ensure_data_dirs, migrate_legacy_data
from app.core.settings.service import SettingsService
from app.core.task.manager import TaskManager
from app.core.url.bilibili import BilibiliParser
from app.core.url.registry import UrlParserRegistry

# 数据目录初始化与旧数据迁移（打包模式首次启动执行一次）
ensure_data_dirs()
migrate_legacy_data(frozen=is_packaged())

app = FastAPI(title=APP_NAME, version=APP_VERSION)

# 打包版 token 校验开关（None = 开发模式不校验）
app.state.auth_token = None


def _resolve_frontend_dist() -> Path:
    """前端构建产物：打包版随包内（sys._MEIPASS）；开发模式项目内。"""
    if is_packaged():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.argv[0]).resolve().parent))
        return base / "frontend" / "dist"
    return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


FRONTEND_DIST = _resolve_frontend_dist()

# ---- 共享单例（app.state，路由经 Depends 获取） ----

settings_service = SettingsService(
    settings_file=SETTINGS_FILE,
    default_output_dir=DEFAULT_OUTPUT_DIR,
)
cookie_store = CookieStore(
    raw_file=COOKIE_RAW_FILE,
    netscape_file=COOKIE_NETSCAPE_FILE,
    legacy_raw=LEGACY_COOKIE_RAW,
)
cookie_service = CookieService(
    validator=BilibiliCookieValidator(),
    store=cookie_store,
    acquirer=BrowserCookieAcquirer(user_data_dir=DATA_DIR / "browser_profile"),
)

parser_registry = UrlParserRegistry()
parser_registry.register(BilibiliParser())

task_manager = TaskManager(settings=settings_service, cookie=cookie_service)
# 启动恢复任务历史：终态进历史分组；上次未完成任务标记"中断"（P3）
task_manager.load_history()

# WebSocket 进度推送：TaskManager 事件 → EventPusher（节流）→ ConnectionManager 广播
ws_manager = ws.ConnectionManager()
event_pusher = ws.EventPusher(ws_manager, task_manager)
task_manager.on_event = event_pusher.push

app.state.settings = settings_service
app.state.cookie = cookie_service
app.state.registry = parser_registry
app.state.tasks = task_manager
app.state.ws_manager = ws_manager

# ---- 中间件 ----

# 本机 token 鉴权：仅 launcher 设置 auth_token 后生效（打包版防本地越权调用）
# 只保护 /api/*（数据接口）；页面/静态资源放行（浏览器入口加载无法携带 header）
@app.middleware("http")
async def token_auth(request, call_next):
    expected = getattr(request.app.state, "auth_token", None)
    if expected and request.url.path.startswith("/api/"):
        got = request.headers.get("X-Auth-Token")
        if got != expected:
            return JSONResponse(
                status_code=401,
                content={"code": "AUTH_REQUIRED", "message": "非法访问", "data": None},
            )
    return await call_next(request)


# 本地开发 CORS（打包版同源不需要；书签回传来源放开）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://www.bilibili.com",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 路由与错误处理 ----

register_error_handlers(app)
app.include_router(tasks.router)
app.include_router(cookie.router)
app.include_router(settings_route.router)
app.include_router(capabilities.router)
app.include_router(ws.router)


@app.get("/")
def root():
    if FRONTEND_DIST.exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return {"app": APP_NAME, "status": "ok"}


@app.get("/api/health")
def health():
    """健康检查：版本 + yt-dlp 版本（前端"关于"展示，便于排查升级）。"""
    return {
        "app": APP_NAME,
        "status": "ok",
        "version": APP_VERSION,
        "ytdlp_version": yt_dlp.version.__version__,
    }


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")