"""Cookie 校验接口：判断 Cookie 是否有效 + 登录用户名。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CookieStatus:
    valid: bool
    uname: str | None = None
    message: str = ""


class CookieCheckError(Exception):
    """网络异常等无法完成校验的情况（区别于"校验结果为无效"）。"""


class CookieValidator(ABC):
    @abstractmethod
    def validate(self, cookie: str) -> CookieStatus:
        """校验 Cookie 有效性；校验过程本身失败抛 CookieCheckError。"""