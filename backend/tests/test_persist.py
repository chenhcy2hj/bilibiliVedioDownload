"""任务历史持久化测试（P3）：写盘时机 / 启动恢复 / 中断标记 / 裁剪 / 损坏容错 / finished_at。"""
import json
import time
from pathlib import Path

from app.core.cookie.base import CookieStatus
from app.core.settings.service import SettingsService
from app.core.task.manager import TaskManager, TaskStatus
from app.core.task.persist import HistoryStore, TaskRecord
from app.core.url.base import MediaItem, ParsedRequest

REQ = ParsedRequest(
    source="bilibili", kind="single", entries=[MediaItem(url="https://x")]
)


class FakeCookieOK:
    def is_valid(self, cookie: str | None = None) -> CookieStatus:
        return CookieStatus(valid=True, uname="tester", message="ok")

    def get_cookie_file(self):
        return None


class HangingDownloader:
    """占位下载器：挂起 worker 线程，避免异步执行干扰状态断言。"""

    def download(
        self, request, task_id, output_dir, cookie_file, cancel_event, on_progress
    ):
        time.sleep(3600)


def make_manager(tmp_path: Path) -> TaskManager:
    svc = SettingsService(
        settings_file=tmp_path / "settings.json", default_output_dir=tmp_path / "out"
    )
    return TaskManager(
        settings=svc,
        cookie=FakeCookieOK(),
        downloader=HangingDownloader(),
        history=HistoryStore(path=tmp_path / "tasks.json"),
    )


def read_records(tmp_path: Path) -> list[dict]:
    data = json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))
    return data["tasks"]


class TestWrite:
    def test_terminal_status_writes_full_record(self, tmp_path: Path):
        mgr = make_manager(tmp_path)
        task = mgr.enqueue("BV1JRuA6vEv", REQ)
        mgr._fail(task, "auth", "Cookie 无效，请重新获取")

        rec = read_records(tmp_path)[0]
        assert rec["id"] == task.id
        assert rec["input_url"] == "BV1JRuA6vEv"
        assert rec["source"] == "bilibili"
        assert rec["kind"] == "single"
        assert rec["entry_count"] == 1
        assert rec["status"] == "failed"
        assert rec["error_code"] == "auth"
        assert rec["error_message"]
        assert rec["file_path"] is None
        assert rec["created_at"]
        assert rec["finished_at"]  # 终态必须带 finishing 时间

    def test_progress_updates_are_not_persisted(self, tmp_path: Path):
        """同一 status 的进度更新（200ms 级）不触发写盘。"""
        mgr = make_manager(tmp_path)
        task = mgr.enqueue("BV1JRuA6vEv", REQ)
        # 状态切换（pending → downloading）写一次
        mgr._set_status(task, TaskStatus.DOWNLOADING, "downloading")
        snap = (tmp_path / "tasks.json").read_text(encoding="utf-8")
        for i in range(5):
            mgr._set_status(task, TaskStatus.DOWNLOADING, "downloading")  # 未变化
            mgr._set(task, progress=0.1 * (i + 1), speed=1024)
        assert (tmp_path / "tasks.json").read_text(encoding="utf-8") == snap


class TestRestore:
    def test_load_history_restores_terminal_and_interrupts_active(self, tmp_path: Path):
        path = tmp_path / "tasks.json"
        path.write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "id": "t1",
                            "input_url": "BV1",
                            "source": "bilibili",
                            "kind": "single",
                            "entry_count": 1,
                            "title": "曲名",
                            "status": "done",
                            "error_code": None,
                            "error_message": None,
                            "file_path": "/tmp/a.mp3",
                            "created_at": "2026-08-28T12:00:00",
                            "finished_at": "2026-08-28T12:01:00",
                        },
                        {
                            "id": "t2",
                            "input_url": "BV2",
                            "source": "bilibili",
                            "kind": "single",
                            "entry_count": 2,
                            "title": None,
                            "status": "downloading",
                            "error_code": None,
                            "error_message": None,
                            "file_path": None,
                            "created_at": "2026-08-28T12:02:00",
                            "finished_at": None,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        mgr = make_manager(tmp_path)
        mgr.load_history()
        tasks = {t.id: t for t in mgr.list()}
        assert mgr._queue.empty()  # 恢复的任务不重新入队

        # 终态原样恢复
        assert tasks["t1"].status == TaskStatus.DONE
        assert tasks["t1"].title == "曲名"
        assert tasks["t1"].file_path == "/tmp/a.mp3"
        assert tasks["t1"].finished_at is not None
        assert tasks["t1"].request.source == "bilibili"

        # 进行中 → 中断（interrupted + finished_at=now）且写回
        assert tasks["t2"].status == TaskStatus.INTERRUPTED
        assert tasks["t2"].finished_at is not None
        assert tasks["t2"].request.entries  # entry_count=2 → 2 个条目
        by_id = {r["id"]: r for r in read_records(tmp_path)}
        assert by_id["t2"]["status"] == "interrupted"
        assert by_id["t2"]["finished_at"]

    def test_missing_file_loads_empty(self, tmp_path: Path):
        mgr = make_manager(tmp_path)
        mgr.load_history()
        assert mgr.list() == []

    def test_corrupt_file_loads_empty(self, tmp_path: Path):
        (tmp_path / "tasks.json").write_text("{not json", encoding="utf-8")
        mgr = make_manager(tmp_path)
        mgr.load_history()  # 不崩溃
        assert mgr.list() == []

    def test_invalid_record_skipped(self, tmp_path: Path):
        path = tmp_path / "tasks.json"
        path.write_text(
            json.dumps(
                {
                    "tasks": [
                        {"id": "bad"},  # 缺字段
                        {
                            "id": "ok",
                            "input_url": "BV1",
                            "source": "bilibili",
                            "kind": "single",
                            "entry_count": 1,
                            "title": None,
                            "status": "done",
                            "error_code": None,
                            "error_message": None,
                            "file_path": None,
                            "created_at": "2026-08-28T12:00:00",
                            "finished_at": None,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        mgr = make_manager(tmp_path)
        mgr.load_history()
        ids = [t.id for t in mgr.list()]
        assert ids == ["ok"]


class TestTrim:
    def test_save_keeps_latest_500(self, tmp_path: Path):
        store = HistoryStore(path=tmp_path / "tasks.json")
        records = [
            TaskRecord(
                id=f"t{i}",
                input_url="BV1",
                source="bilibili",
                kind="single",
                entry_count=1,
                title=None,
                status="done",
                error_code=None,
                error_message=None,
                file_path=None,
                created_at=f"2026-08-28T12:{i // 60:02d}:{i % 60:02d}",
                finished_at=None,
            )
            for i in range(501)
        ]
        store.save(records)
        saved = json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))
        assert len(saved["tasks"]) == 500
        ids = [r["id"] for r in saved["tasks"]]
        assert "t500" in ids  # 保留最新
        assert "t0" not in ids


class TestResponse:
    def test_finished_at_in_response(self, tmp_path: Path):
        mgr = make_manager(tmp_path)
        task = mgr.enqueue("BV1JRuA6vEv", REQ)
        assert mgr.to_response(task).finished_at is None  # 进行中无
        mgr._fail(task, "network", "网络异常")
        resp = mgr.to_response(task)
        assert resp.status == TaskStatus.FAILED
        assert resp.finished_at is not None
        assert resp.input_url == "BV1JRuA6vEv"