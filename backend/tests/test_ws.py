"""WebSocket 进度推送测试：快照/事件流/节流/类型映射。"""
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.ws import EventPusher
from app.core.downloader.base import ProgressEvent
from app.core.task.manager import Task
from app.core.url.base import MediaItem, ParsedRequest
from app.main import app

client = TestClient(app)


def make_task(task_id: str = "t1") -> Task:
    return Task(
        id=task_id,
        input_url="BV1JRuA6vEvd",
        request=ParsedRequest(
            source="bilibili", kind="single", entries=[MediaItem(url="https://www.bilibili.com/video/BV1JRuA6vEvd")]
        ),
        output_dir=Path("/tmp"),
    )


class TestWsEndpoint:
    def test_snapshot_then_created_then_failed(self):
        with client.websocket_connect("/api/ws") as ws:
            # 1. 全量快照
            snap = ws.receive_json()
            assert snap["type"] == "task.snapshot"
            assert isinstance(snap["payload"]["tasks"], list)

            # 2. 创建任务（无 Cookie → 快速 failed(auth)）
            client.post("/api/tasks", json={"urls": ["BV1JRuA6vEvd"]})

            seen: set[str] = set()
            for _ in range(10):
                msg = ws.receive_json()
                seen.add(msg["type"])
                if msg["type"] == "task.failed":
                    break
            assert "task.created" in seen
            assert "task.failed" in seen


class FakeTasks:
    def __init__(self, task: Task):
        self._task = task

    def get(self, task_id: str):
        return self._task

    def to_response(self, task: Task) -> dict:
        return {"id": task.id, "status": task.status}


class RecordingManager:
    def __init__(self):
        self.items: list[dict] = []

    def broadcast(self, payload: dict) -> None:
        self.items.append(payload)


class TestEventPusher:
    def test_progress_throttled_within_interval(self):
        mgr = RecordingManager()
        pusher = EventPusher(mgr, FakeTasks(make_task()))
        pusher.push(ProgressEvent(task_id="t1", status="downloading", downloaded=1, total=10))
        pusher.push(ProgressEvent(task_id="t1", status="downloading", downloaded=2, total=10))
        assert len(mgr.items) == 1
        assert mgr.items[0]["type"] == "task.progress"

    def test_status_event_not_throttled(self):
        mgr = RecordingManager()
        pusher = EventPusher(mgr, FakeTasks(make_task()))
        pusher.push(ProgressEvent(task_id="t1", status="downloading"))
        pusher.push(ProgressEvent(task_id="t1", status="failed", error_code="auth", error_message="x"))
        assert len(mgr.items) == 2
        assert mgr.items[1]["type"] == "task.failed"

    def test_type_mapping(self):
        assert EventPusher._map_type(ProgressEvent("t", "pending")) == "task.created"
        assert EventPusher._map_type(ProgressEvent("t", "downloading")) == "task.progress"
        assert EventPusher._map_type(ProgressEvent("t", "converting")) == "task.phase"
        assert EventPusher._map_type(ProgressEvent("t", "done")) == "task.done"
        assert EventPusher._map_type(ProgressEvent("t", "failed")) == "task.failed"
        assert EventPusher._map_type(ProgressEvent("t", "canceled")) == "task.canceled"