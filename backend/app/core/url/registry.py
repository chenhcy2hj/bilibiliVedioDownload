"""UrlParser 注册中心：按 match 分发，未匹配抛 UnsupportedUrlError。"""
from app.core.url.base import ParsedRequest, UnsupportedUrlError, UrlParser


class UrlParserRegistry:
    def __init__(self) -> None:
        self._parsers: list[UrlParser] = []

    def register(self, parser: UrlParser) -> None:
        """插拔注册：新平台/新链接形态只需注册新实现。"""
        self._parsers.append(parser)

    @property
    def parsers(self) -> list[UrlParser]:
        return list(self._parsers)

    def capabilities(self) -> list[dict]:
        return [
            {"source": p.source, "capability": p.capability}
            for p in self._parsers
        ]

    def dispatch(self, url: str) -> ParsedRequest:
        for parser in self._parsers:
            if parser.match(url):
                return parser.parse(url)
        raise UnsupportedUrlError(f"不支持的链接格式: {url}")