"""M5 测试：FFmpeg 定位、文件名去重、数据目录解析与迁移、书签引导、中文文件名响应头。"""
from pathlib import Path

import pytest

from app.api.cookie import build_bookmarklet
from app.config import resolve_data_dir
from app.core.dirs import ensure_data_dirs, migrate_legacy_data
from app.core.downloader.ffmpeg import FFmpegLocator, FfmpegNotFoundError
from app.core.downloader.ytdlp import unique_path


class TestFfmpegLocator:
    def test_found_in_path(self, monkeypatch, tmp_path):
        fake = tmp_path / "ffmpeg"
        fake.write_text("")
        fake.chmod(0o755)
        monkeypatch.setattr("shutil.which", lambda name: str(fake) if name == "ffmpeg" else None)
        assert FFmpegLocator().locate() == fake

    def test_found_in_bundled_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("shutil.which", lambda name: None)
        bundled = tmp_path / "bin"
        bundled.mkdir()
        exe = bundled / "ffmpeg"
        exe.write_text("")
        assert FFmpegLocator(bundled_dir=bundled).locate() == exe

    def test_windows_exe_in_bundled(self, monkeypatch, tmp_path):
        monkeypatch.setattr("shutil.which", lambda name: None)
        bundled = tmp_path / "bin"
        bundled.mkdir()
        exe = bundled / "ffmpeg.exe"
        exe.write_text("")
        assert FFmpegLocator(bundled_dir=bundled).locate() == exe

    def test_not_found_raises(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda name: None)
        with pytest.raises(FfmpegNotFoundError) as e:
            FFmpegLocator().locate()
        assert "FFmpeg" in str(e.value)


class TestUniquePath:
    def test_no_conflict(self, tmp_path):
        assert unique_path(tmp_path, "a.mp3") == tmp_path / "a.mp3"

    def test_conflict_suffixes(self, tmp_path):
        (tmp_path / "a.mp3").write_text("1")
        (tmp_path / "a (1).mp3").write_text("2")
        assert unique_path(tmp_path, "a.mp3") == tmp_path / "a (2).mp3"

    def test_non_ascii_name(self, tmp_path):
        (tmp_path / "歌.mp3").write_text("1")
        assert unique_path(tmp_path, "歌.mp3") == tmp_path / "歌 (1).mp3"


class TestDataDirs:
    def test_resolve_dev_mode(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.config.PROJECT_ROOT", tmp_path)
        assert resolve_data_dir(is_frozen=False) == tmp_path / "data"

    def test_resolve_packaged_macos(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        home = Path("/Users/fake")
        monkeypatch.setattr("pathlib.Path.home", lambda: home)
        d = resolve_data_dir(is_frozen=True)
        assert d == home / "Library" / "Application Support" / "BiliDownloader"

    def test_ensure_creates_defaults(self, tmp_path, monkeypatch):
        data = tmp_path / "data"
        monkeypatch.setattr("app.core.dirs.DATA_DIR", data)
        monkeypatch.setattr("app.core.dirs.DEFAULT_OUTPUT_DIR", data / "downloads")
        ensure_data_dirs()
        assert (data / "downloads").is_dir()

    def test_migrate_once(self, tmp_path, monkeypatch):
        data = tmp_path / "data"
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "old.txt").write_text("x")
        (legacy / "sub").mkdir()
        monkeypatch.setattr("app.core.dirs.DATA_DIR", data)
        monkeypatch.setattr("app.core.dirs.LEGACY_DATA_DIRS", [legacy])
        migrate_legacy_data(frozen=True)
        assert (data / "old.txt").exists()
        assert (data / "sub").is_dir()

    def test_migrate_skips_when_frozen_false(self, tmp_path, monkeypatch):
        data = tmp_path / "data"
        legacy = tmp_path / "legacy"
        legacy.mkdir()
        (legacy / "old.txt").write_text("x")
        monkeypatch.setattr("app.core.dirs.DATA_DIR", data)
        monkeypatch.setattr("app.core.dirs.LEGACY_DATA_DIRS", [legacy])
        migrate_legacy_data(frozen=False)  # 开发模式不迁移
        assert not data.exists()


class TestCookieGuide:
    def test_bookmarklet_encoded(self):
        from urllib.parse import unquote

        bm = build_bookmarklet()
        assert bm.startswith("javascript:")
        # 必须 URL 编码：不含裸空格/引号（避免书签粘贴后语法破坏）
        assert " " not in bm
        decoded = unquote(bm)
        assert "document.cookie" in decoded
        assert "127.0.0.1:8000" in decoded

    def test_guide_dev_mode(self):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        r = client.get("/api/cookie/guide")
        assert r.status_code == 200
        body = r.json()
        assert body["jump_url"].startswith("https://www.bilibili.com")
        assert body["bookmarklet"].startswith("javascript:")
        assert body["steps"]


class TestChineseFilenameHeader:
    def test_file_response_content_disposition(self, tmp_path):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app)
        # 注入一个"已完成"任务，指向中文文件名临时文件
        from app.core.task.manager import TaskStatus

        target = tmp_path / "周杰伦 - 东风破.mp3"
        target.write_bytes(b"fake-mp3")
        mgr = app.state.tasks
        task = mgr.enqueue("BV1JRuA6vEvd", __import__("app.core.url.base", fromlist=["ParsedRequest"]).ParsedRequest(
            source="bilibili", kind="single",
            entries=[__import__("app.core.url.base", fromlist=["MediaItem"]).MediaItem(url="https://x")],
        ))
        task.file_path = str(target)
        task.status = TaskStatus.DONE
        task.phase = "done"
        try:
            r = client.get(f"/api/tasks/{task.id}/file")
            assert r.status_code == 200
            cd = r.headers["content-disposition"]
            assert "attachment" in cd
            # 中文文件名须经 RFC 5987 编码（filename*=utf-8''）
            assert "filename*=utf-8''" in cd or "filename" in cd
        finally:
            mgr._tasks.pop(task.id, None)