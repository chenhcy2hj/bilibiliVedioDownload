"""Cookie 相关数据模型。"""
from datetime import datetime

from pydantic import BaseModel, Field


class CookieSubmitRequest(BaseModel):
    cookie: str = Field(min_length=1, description="浏览器 Cookie 字符串（key=value; ...）")


class CookieStatusResponse(BaseModel):
    valid: bool
    uname: str | None = None
    message: str
    has_cookie_file: bool = False
    updated_at: datetime | None = None
    acquiring: bool = False
    """无感获取（浏览器弹窗）进行中。"""
    acquire_message: str | None = None
    """获取中提示 / 获取失败原因。"""


class CookieGuideResponse(BaseModel):
    jump_url: str
    bookmarklet: str | None = None
    """javascript: 协议书签脚本（可直接存为书签地址）；打包版为 None（动态端口不适用）。"""
    steps: list[str]