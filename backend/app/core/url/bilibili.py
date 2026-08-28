"""BilibiliParser：识别 3 种输入形态（标准链接/裸BV/短链）与 ?p= 分P 参数。"""
import re
from urllib.parse import parse_qs, urlparse

import httpx

from app.config import BILI_HOST, REFERER, UA
from app.core.url.base import MediaItem, ParsedRequest, ParseError, UrlParser

BV_RE = r"BV[0-9A-Za-z]{10}"

# 标准链接：带/不带尾斜杠、可带 query（?p=2）与 hash 路由
STANDARD_URL_RE = re.compile(
    rf"^https?://(?:www\.|m\.)?bilibili\.com/video/({BV_RE})(?:[/?#].*)?$"
)
BARE_BV_RE = re.compile(rf"^({BV_RE})$")
SHORT_LINK_RE = re.compile(r"^https?://b23\.tv/[0-9A-Za-z]+$")


class BilibiliParser(UrlParser):
    source = "bilibili"
    capability = "bilibili: 标准链接(带/不带尾斜杠) / 裸BV号 / b23.tv短链 / ?p=分P"

    def match(self, url: str) -> bool:
        url = url.strip()
        return bool(
            STANDARD_URL_RE.match(url)
            or BARE_BV_RE.match(url)
            or SHORT_LINK_RE.match(url)
        )

    def parse(self, url: str) -> ParsedRequest:
        url = url.strip()
        if BARE_BV_RE.match(url):
            return self._from_bvid(url, page=None)
        if SHORT_LINK_RE.match(url):
            real = self._resolve_short_link(url)
            return self.parse(real)  # 短链解析出真实地址后走标准流程
        m = STANDARD_URL_RE.match(url)
        if not m:
            raise ParseError(f"无法解析的链接: {url}")
        return self._from_bvid(m.group(1), page=self._extract_page(url))

    # ---- 内部实现 ----

    def _from_bvid(self, bvid: str, page: int | None) -> ParsedRequest:
        base = f"{BILI_HOST}/video/{bvid}"
        if page is None:
            return ParsedRequest(
                source=self.source,
                kind="single",
                entries=[MediaItem(url=base)],
                options=self._default_options(),
            )
        # 多P 选集：entry 携带 ?p=N（kind=multi 表示来自多P选集上下文）
        return ParsedRequest(
            source=self.source,
            kind="multi",
            entries=[MediaItem(url=f"{base}?p={page}")],
            options=self._default_options(),
        )

    @staticmethod
    def _extract_page(url: str) -> int | None:
        qs = parse_qs(urlparse(url).query)
        raw = qs.get("p", [None])[0]
        if raw is None:
            return None
        try:
            page = int(raw)
        except ValueError:
            raise ParseError(f"非法的分P参数: p={raw}")
        return page if page >= 1 else None

    @staticmethod
    def _resolve_short_link(url: str) -> str:
        try:
            with httpx.Client(
                timeout=10,
                follow_redirects=True,
                headers={"User-Agent": UA, "Referer": REFERER},
            ) as client:
                resp = client.get(url)
                real = str(resp.url)
        except httpx.HTTPError as e:
            raise ParseError(f"短链解析失败: {e}")
        if not real.startswith("http"):
            raise ParseError("短链解析结果非法")
        return real

    @staticmethod
    def _default_options() -> dict:
        return {"audio_format": "mp3", "audio_quality": "192"}