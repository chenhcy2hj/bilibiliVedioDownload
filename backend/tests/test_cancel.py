"""取消任务测试：长任务经 Downloader 检查 cancel_event 中止 → CANCELED。"""
import time
from pathlib import Path

from app.core.cookie.base import CookieStatus
from app.core.downloader.base import DownloadResult, ProgressEvent, TaskCanceled
from app.core.settings.service import SettingsService
from app.core.task.manager import TaskManager, TaskStatus
from app.core.url.base import MediaItem, ParsedRequest


class FakeCookieOK:
    def is_valid(self, cookie: str | None = None) -> CookieStatus:
        return CookieStatus(valid=True, uname="tester", message="ok")

    def get_cookie_file(self):
        return None


class SlowDownloader:
    """模拟长下载：先发 downloading 事件，每 20ms 检查一次取消标志。"""

    def download(
        self, request, task_id, output_dir, cookie_file, cancel_event, on_progress
    ):
        on_progress(
            ProgressEvent(task_id=task_id, status="downloading", downloaded=0, total=100)
        )
        for _ in range(500):
            if cancel_event.is_set():
                raise TaskCanceled()
            time.sleep(0.02)
        return DownloadResult(ok=True)


def wait_status(mgr: TaskManager, task_id: str, expect: TaskStatus, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = mgr.get(task_id)
        if task is not None and task.status == expect:
            return task
        time.sleep(0.02)
    raise AssertionError(f"任务 {task_id} 未在 {timeout}s 内到达 {expect}")


def test_cancel_long_running_task(tmp_path: Path):
    svc = SettingsService(settings_file=tmp_path / "settings.json", default_output_dir=tmp_path / "out")
    mgr = TaskManager(settings=svc, cookie=FakeCookieOK(), downloader=SlowDownloader())
    req = ParsedRequest(source="bilibili", kind="single", entries=[MediaItem(url="https://x")])

    task = mgr.enqueue("测试链接", req)
    # 等待 worker 进入 downloading 阶段（轮询，避免时序抖动）
    wait_status(mgr, task.id, TaskStatus.DOWNLOADING)

    mgr.cancel(task.id)
    t = wait_status(mgr, task.id, TaskStatus.CANCELED)
    assert t.error_code == "canceled"


def test_cancel_after_done_is_noop(tmp_path: Path):
    svc = SettingsService(settings_file=tmp_path / "settings.json", default_output_dir=tmp_path / "out")
    mgr = TaskManager(settings=svc, cookie=FakeCookieOK(), downloader=SlowDownloader())
    req = ParsedRequest(source="bilibili", kind="single", entries=[MediaItem(url="https://x")])
    task = mgr.enqueue("测试链接", req)
    mgr.cancel(task.id)  # 可能在执行中或已完成，均不应抛错
    assert mgr.get(task.id) is not None