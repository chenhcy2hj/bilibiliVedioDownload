"""WebSocket 进度推送（M3）。

- 连接建立：推送 task.snapshot 全量快照，之后推增量事件；
- 事件类型：task.created / task.progress / task.phase / task.done / task.failed / task.canceled；
- 跨线程：TaskManager 在 worker 线程调用 pusher.push → broadcast 经
  loop.call_soon_threadsafe 投递到事件循环，每个连接由独立 sender task 发送；
- 节流：同一任务 task.progress 推送间隔 >= 500ms（避免 WS 风暴），
  状态变化事件（done/failed/canceled 等）不节流。
"""
import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.downloader.base import ProgressEvent

logger = logging.getLogger(__name__)

PROGRESS_INTERVAL_SEC = 0.2  # 进度节流：快速任务（<1s 完成）也能看到多次更新

router = APIRouter(tags=["ws"])


class ConnectionManager:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connections: dict[WebSocket, asyncio.Queue] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue()
        self._connections[ws] = q
        asyncio.create_task(self._sender(ws, q))

    async def disconnect(self, ws: WebSocket) -> None:
        self._connections.pop(ws, None)

    def broadcast(self, payload: dict) -> None:
        """任意线程可调用（TaskManager worker 线程）。"""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._enqueue_all, payload)

    def _enqueue_all(self, payload: dict) -> None:
        for q in list(self._connections.values()):
            q.put_nowait(payload)

    async def _sender(self, ws: WebSocket, q: asyncio.Queue) -> None:
        try:
            while True:
                payload = await q.get()
                await ws.send_text(json.dumps(payload, ensure_ascii=False, default=str))
        except Exception:  # noqa: BLE001 - 连接断开/发送失败即清理
            self._connections.pop(ws, None)


class EventPusher:
    """把 TaskManager 的 ProgressEvent 映射为 WS envelope，并在出口节流。"""

    def __init__(self, manager: ConnectionManager, tasks) -> None:
        self._manager = manager
        self._tasks = tasks
        self._last_progress: dict[str, float] = {}

    def push(self, event: ProgressEvent) -> None:
        task = self._tasks.get(event.task_id)
        if task is None:
            return
        event_type = self._map_type(event)
        if event_type == "task.progress":
            now = time.monotonic()
            if now - self._last_progress.get(event.task_id, 0.0) < PROGRESS_INTERVAL_SEC:
                return  # 节流：丢弃本次进度推送（任务内存状态仍已更新）
            self._last_progress[event.task_id] = now
        else:
            self._last_progress.pop(event.task_id, None)
        self._manager.broadcast(
            {"type": event_type, "payload": task_to_json(self._tasks.to_response(task))}
        )

    @staticmethod
    def _map_type(event: ProgressEvent) -> str:
        status = event.status
        if status in ("pending", "queued"):
            return "task.created"
        if status == "downloading":
            return "task.progress"
        if status in ("converting", "finished"):
            return "task.phase"
        if status == "done":
            return "task.done"
        if status == "failed":
            return "task.failed"
        if status == "canceled":
            return "task.canceled"
        return "task.phase"


def task_to_json(response) -> dict:
    """TaskResponse → 可 JSON 序列化 dict（pydantic model_dump mode=json）。"""
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    return response


@router.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    app = ws.app
    manager: ConnectionManager = app.state.ws_manager
    tasks: Any = app.state.tasks

    # 打包版 token 校验（开发模式 auth_token 为 None → 放行）
    expected = getattr(app.state, "auth_token", None)
    if expected and ws.query_params.get("token") != expected:
        await ws.close(code=4401)
        return

    manager.bind_loop(asyncio.get_running_loop())
    await manager.connect(ws)
    # 全量快照：断线重连后靠它补齐状态
    snapshot = {
        "type": "task.snapshot",
        "payload": {
            "tasks": [task_to_json(tasks.to_response(t)) for t in tasks.list()]
        },
    }
    await ws.send_text(json.dumps(snapshot, ensure_ascii=False, default=str))
    try:
        while True:
            await ws.receive_text()  # 保持连接存活；客户端消息暂不处理
    except WebSocketDisconnect:
        await manager.disconnect(ws)