"""Cookie 相关 REST API：引导（书签脚本）/ 提交校验 / 状态查询。"""
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request

from app.api.errors import ApiError
from app.config import is_packaged
from app.core.cookie.service import CookieService
from app.schemas.cookie import (
    CookieGuideResponse,
    CookieStatusResponse,
    CookieSubmitRequest,
)

router = APIRouter(prefix="/api/cookie", tags=["cookie"])

# 书签小工具：在 bilibili.com 页面（登录态）点击，读取 document.cookie 回传本地后端
# 注意：URL 编码后整体放入 javascript: 协议；回传地址固定 127.0.0.1:8000（开发模式）
_BOOKMARKLET_CODE = r"""
(async () => {
  try {
    const resp = await fetch("http://127.0.0.1:8000/api/cookie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cookie: document.cookie }),
    });
    const data = await resp.json();
    if (data.valid) {
      alert("[BiliDownloader] Cookie 已保存，登录用户：" + (data.uname || ""));
    } else {
      alert("[BiliDownloader] " + (data.message || "校验失败"));
    }
  } catch (e) {
    alert("[BiliDownloader] 回传失败：请确认应用正在运行（127.0.0.1:8000）");
  }
})();
"""


def build_bookmarklet() -> str:
    """生成 javascript: 协议书签地址（URL 编码，避免引号/换行冲突）。"""
    return "javascript:" + quote(_BOOKMARKLET_CODE.strip())


def get_cookie(request: Request) -> CookieService:
    return request.app.state.cookie


CookieDep = Annotated[CookieService, Depends(get_cookie)]


@router.get("/guide", response_model=CookieGuideResponse)
def cookie_guide():
    """获取 Cookie 引导信息：书签脚本（开发模式可回传）+ 手动粘贴兜底。"""
    if not is_packaged():
        return CookieGuideResponse(
            jump_url="https://www.bilibili.com/",
            bookmarklet=build_bookmarklet(),
            steps=[
                "点击下方按钮，新窗口打开 bilibili.com 并登录（若已登录则直接使用书签）",
                "在浏览器中新建书签：名称任意，地址粘贴右侧「复制书签脚本」得到的内容",
                "回到 B 站页面点击该书签 → Cookie 自动回传并校验，页面显示登录用户名",
                "书签不可用时可手动粘贴：F12 → Network 任意请求头中的 Cookie → 粘贴到下方输入框",
            ],
        )
    return CookieGuideResponse(
        jump_url="https://www.bilibili.com/",
        bookmarklet=None,
        steps=[
            "打包版使用动态端口，书签回传不适用；请使用手动粘贴方式",
            "点击下方按钮打开 bilibili.com 并登录",
            "F12 → Network 任意请求头中复制 Cookie → 粘贴到下方输入框提交",
        ],
    )


@router.post("/acquire", response_model=CookieStatusResponse)
def acquire_cookie(cookie: CookieDep):
    """无感获取：弹出浏览器窗口，用户登录后自动捕获并保存 Cookie。

    进行中再次调用返回 409；前端轮询 GET /api/cookie/status 获取结果。
    """
    ok = cookie.begin_acquire()
    if not ok:
        raise ApiError("ACQUIRE_IN_PROGRESS", "获取已在进行中，请在弹出的浏览器窗口完成登录", status_code=409)
    return cookie.status()


@router.post("", response_model=CookieStatusResponse)
def submit_cookie(
    body: CookieSubmitRequest,
    cookie: CookieDep,
):
    """提交 Cookie：后端校验（nav 接口）→ 有效则保存并自动转 Netscape。"""
    return cookie.submit(body.cookie)


@router.get("/status", response_model=CookieStatusResponse)
def cookie_status(cookie: CookieDep):
    """查询当前 Cookie 有效状态（有效/过期/未配置 + 登录用户名）。"""
    return cookie.status()