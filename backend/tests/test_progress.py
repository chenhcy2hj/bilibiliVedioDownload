"""下载进度计算与传递测试（M5 修复：分片下载 total 缺失导致进度不展示）。"""
import time

from app.core.downloader.base import DownloadResult, ProgressEvent
from app.core.downloader.ytdlp import calc_progress
from app.core.settings.service import SettingsService
from app.core.task.manager import TaskManager, TaskStatus
from app.core.url.base import MediaItem, ParsedRequest


class TestCalcProgress:
    def test_byte_ratio(self):
        assert calc_progress({"downloaded_bytes": 50, "total_bytes": 100}) == 0.5

    def test_estimate_ratio(self):
        assert calc_progress({"downloaded_bytes": 25, "total_bytes_estimate": 100}) == 0.25

    def test_fragment_fallback(self):
        # B 站 DASH 分片：total 缺失，用片段比例
        d = {"downloaded_bytes": 999, "fragment_index": 7, "fragment_count": 10}
        assert calc_progress(d) == 0.7

    def test_fragment_partial(self):
        assert calc_progress({"fragment_index": 3, "fragment_count": 8}) == 0.375

    def test_unknown_returns_none(self):
        assert calc_progress({"downloaded_bytes": 10}) is None
        assert calc_progress({}) is None

    def test_clamped_to_one(self):
        assert calc_progress({"downloaded_bytes": 150, "total_bytes": 100}) == 1.0


class FakeCookieOK:
    def is_valid(self, cookie=None):
        from app.core.cookie.base import CookieStatus

        return CookieStatus(valid=True, uname="t", message="ok")

    def get_cookie_file(self):
        return None


class ProgressDownloader:
    """按事件序列发送进度，模拟真实下载事件流。"""

    def download(self, request, task_id, output_dir, cookie_file, cancel_event, on_progress):
        for idx in range(1, 6):
            on_progress(
                ProgressEvent(
                    task_id=task_id,
                    status="downloading",
                    phase="downloading",
                    progress=idx / 5,          # 分片比例兜底路径
                    downloaded=idx * 1024,
                    total=None,                # total 未知（分片下载场景）
                    speed=1024 * 1024,
                    eta=10 - idx,
                )
            )
            time.sleep(0.01)
        on_progress(ProgressEvent(task_id=task_id, status="finished", phase="converting", progress=1.0))
        return DownloadResult(ok=True)


def test_progress_flows_through_manager_and_response(tmp_path):
    svc = SettingsService(settings_file=tmp_path / "s.json", default_output_dir=tmp_path / "out")
    mgr = TaskManager(settings=svc, cookie=FakeCookieOK(), downloader=ProgressDownloader())
    events = []
    mgr.on_event = lambda e: events.append(e)
    req = ParsedRequest(source="bilibili", kind="single", entries=[MediaItem(url="https://x")])
    task = mgr.enqueue("进度测试", req)

    deadline = time.time() + 5
    while time.time() < deadline:
        if mgr.get(task.id).status == TaskStatus.DONE:
            break
        time.sleep(0.02)
    assert mgr.get(task.id).status == TaskStatus.DONE

    # 进度事件被记录（含 0.2 / 0.4 ... 1.0）
    progresses = [e.progress for e in events if e.progress is not None]
    assert 0.2 in progresses and 1.0 in progresses

    # to_response 携带 progress 字段（WS payload 依据）
    resp = mgr.to_response(task)
    assert resp.progress == 1.0