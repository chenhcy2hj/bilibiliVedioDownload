"""URL 解析模块测试：三种输入形态、?p 分P、非法输入、registry 分发、短链。"""
import pytest

from app.core.url.base import ParseError, UnsupportedUrlError
from app.core.url.bilibili import BilibiliParser
from app.core.url.registry import UrlParserRegistry

parser = BilibiliParser()
registry = UrlParserRegistry()
registry.register(parser)

VALID_BV = "BV1JRuA6vEvd"


class TestMatch:
    def test_standard_url_with_trailing_slash(self):
        assert parser.match("https://www.bilibili.com/video/BV1hk4y1W76R/")
        assert parser.match("https://www.bilibili.com/video/BV1Z8h36gEnp")
        assert parser.match("https://www.bilibili.com/video/BV1hk4y1W76R/?p=2")

    def test_bare_bvid(self):
        assert parser.match(VALID_BV)

    def test_short_link(self):
        assert parser.match("https://b23.tv/abcd123")

    def test_unsupported(self):
        assert not parser.match("https://www.youtube.com/watch?v=abc")
        assert not parser.match("https://www.bilibili.com/audio/au123")
        assert not parser.match("随便什么文本")
        assert not parser.match("BV12345")  # BV 号长度不足


class TestParse:
    def test_standard_url_single(self):
        r = parser.parse("https://www.bilibili.com/video/BV1hk4y1W76R/")
        assert r.source == "bilibili"
        assert r.kind == "single"
        assert len(r.entries) == 1
        assert r.entries[0].url == "https://www.bilibili.com/video/BV1hk4y1W76R"
        assert r.options["audio_format"] == "mp3"

    def test_no_trailing_slash(self):
        r = parser.parse("https://www.bilibili.com/video/BV1Z8h36gEnp")
        assert r.kind == "single"
        assert r.entries[0].url.endswith("BV1Z8h36gEnp")

    def test_bare_bvid(self):
        r = parser.parse(VALID_BV)
        assert r.kind == "single"
        assert r.entries[0].url == f"https://www.bilibili.com/video/{VALID_BV}"

    def test_multi_page_param(self):
        r = parser.parse("https://www.bilibili.com/video/BV1hk4y1W76R/?p=3")
        assert r.kind == "multi"
        assert r.entries[0].url.endswith("?p=3")

    def test_illegal_page_param(self):
        with pytest.raises(ParseError):
            parser.parse("https://www.bilibili.com/video/BV1hk4y1W76R/?p=abc")

    def test_parse_unsupported_raises(self):
        with pytest.raises(ParseError):
            parser.parse("https://www.youtube.com/watch?v=abc")


class TestRegistry:
    def test_dispatch(self):
        r = registry.dispatch(VALID_BV)
        assert r.source == "bilibili"

    def test_dispatch_unsupported(self):
        with pytest.raises(UnsupportedUrlError):
            registry.dispatch("https://example.com/x")

    def test_capabilities(self):
        caps = registry.capabilities()
        assert any(c["source"] == "bilibili" for c in caps)


class TestShortLink:
    def test_resolve_uses_redirect(self, monkeypatch):
        class FakeResponse:
            def __init__(self):
                self.url = "https://www.bilibili.com/video/BV1CQFjeGEaZ"

        class FakeClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url):
                return FakeResponse()

        import httpx

        monkeypatch.setattr(httpx, "Client", FakeClient)
        r = parser.parse("https://b23.tv/xyz123")
        assert r.source == "bilibili"
        assert "BV1CQFjeGEaZ" in r.entries[0].url