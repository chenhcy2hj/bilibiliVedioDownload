"""URL 解析接口（扩展性设计的关键点）。

新增平台/新链接形态 = 新增 UrlParser 实现并注册到 Registry，
不改动任何业务代码（开闭原则）。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MediaItem:
    """一个可下载条目（条目级 URL，yt-dlp 可直接消费）。"""

    url: str
    title_hint: str | None = None


@dataclass
class ParsedRequest:
    """URL 解析后的统一结构，是所有注册解析器的输出契约。"""

    source: str                     # 来源平台标识，如 "bilibili"
    kind: str                       # single / multi（多P选集上下文）
    entries: list[MediaItem] = field(default_factory=list)
    options: dict = field(default_factory=dict)   # 默认输出选项（格式、清晰度）


class ParseError(Exception):
    """链接能被识别但解析失败（如短链重定向异常）。"""


class UnsupportedUrlError(Exception):
    """没有任何注册解析器认识该链接。"""


class UrlParser(ABC):
    """URL 解析器抽象接口。"""

    source: str = ""
    capability: str = ""            # 能力描述，供 /api/capabilities 上报

    @abstractmethod
    def match(self, url: str) -> bool:
        """识别是否本解析器负责该链接（纯规则判断，不做网络请求）。"""

    @abstractmethod
    def parse(self, url: str) -> ParsedRequest:
        """解析成统一结构；可发起必要的网络解析（如短链重定向）。"""