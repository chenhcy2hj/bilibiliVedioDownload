"""TaskManager：任务状态机 + 串行执行队列 + 进度事件回调。

线程模型：yt-dlp 为同步阻塞调用，使用单工作线程串行消费队列（反爬友好）；
进度经 on_event 回调同步转发（M3 接入 WebSocket 推送）。
"""
import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.cookie.service import CookieService
from app.core.downloader.base import DownloadError, ProgressEvent, TaskCanceled
from app.core.downloader.ytdlp import YtDlpDownloader
from app.core.settings.service import SettingsService
from app.core.url.base import ParsedRequest
from app.schemas.task import TaskResponse, TaskStatus


@dataclass
class Task:
    id: str
    input_url: str
    request: ParsedRequest
    output_dir: Path
    status: TaskStatus = TaskStatus.PENDING
    phase: str = ""
    title: str | None = None  # 视频标题（下载器探测阶段回传，"名称"展示用）
    progress: float | None = None  # 0~1 统一进度（分片下载 - 片段比例兜底）
    downloaded: float | None = None
    total: float | None = None
    speed: float | None = None
    eta: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    file_path: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    cancel_event: threading.Event = field(default_factory=threading.Event)


class TaskManager:
    def __init__(
        self,
        settings: SettingsService,
        cookie: CookieService,
        downloader=None,
    ) -> None:
        self._settings = settings
        self._cookie = cookie
        self._downloader = downloader or YtDlpDownloader()
        self._tasks: dict[str, Task] = {}
        self._queue: queue.Queue[Task] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        # 事件出口：由 API/WS 层设置（M3 接入 WebSocket）
        self.on_event = None  # type: callable | None

    # ---- 只读 ----

    def list(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    # ---- 任务生命周期 ----

    def enqueue(self, input_url: str, request: ParsedRequest) -> Task:
        task = Task(
            id=uuid.uuid4().hex[:12],
            input_url=input_url,
            request=request,
            output_dir=self._settings.get_output_dir(),
        )
        with self._lock:
            self._tasks[task.id] = task
        self._queue.put(task)
        self._emit(ProgressEvent(task_id=task.id, status="pending", phase="queued"))
        self._start_worker_if_needed()
        return task

    def cancel(self, task_id: str) -> Task | None:
        task = self.get(task_id)
        if task is None:
            return None
        if task.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELED):
            return task
        task.cancel_event.set()
        return task

    # ---- 内部：串行工作线程 ----

    def _start_worker_if_needed(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._loop, daemon=True, name="task-worker")
        self._worker.start()

    def _loop(self) -> None:
        while True:
            task = self._queue.get()
            try:
                self._execute(task)
            except Exception:  # noqa: BLE001 - 兜底，防止工作线程退出
                self._fail(task, "unknown", "内部错误")
            finally:
                self._queue.task_done()

    def _execute(self, task: Task) -> None:
        # 下载前检查 Cookie 时效（设计文档：过期则任务直接失败并提示重取）
        status = self._cookie.is_valid()
        if not status.valid:
            self._fail(task, "auth", status.message or "Cookie 无效，请重新获取")
            return

        self._set(task, status=TaskStatus.PARSING, phase="parsing")

        def on_progress(event: ProgressEvent) -> None:
            if event.status == "metadata":
                # 探测完成：记录视频标题（任务"名称"展示）
                self._set(task, title=event.title)
                self._emit(event)
                return
            if event.status == "finished":
                self._set(
                    task,
                    status=TaskStatus.CONVERTING,
                    phase="converting",
                    progress=1.0,
                    downloaded=event.downloaded,
                    total=event.total,
                )
                self._emit(event)
                return
            if event.status == "downloading":
                self._set(
                    task,
                    status=TaskStatus.DOWNLOADING,
                    phase="downloading",
                    progress=event.progress,
                    downloaded=event.downloaded,
                    total=event.total,
                    speed=event.speed,
                    eta=event.eta,
                )
            self._emit(event)

        cookie_file = self._cookie.get_cookie_file()
        try:
            result = self._downloader.download(
                request=task.request,
                task_id=task.id,
                output_dir=task.output_dir,
                cookie_file=cookie_file,
                cancel_event=task.cancel_event,
                on_progress=on_progress,
            )
        except TaskCanceled:
            task.status = TaskStatus.CANCELED
            task.phase = "canceled"
            task.error_code = "canceled"
            task.error_message = "任务已取消"
            task.cancel_event.clear()
            self._emit(
                ProgressEvent(
                    task_id=task.id,
                    status="canceled",
                    phase="canceled",
                    error_code="canceled",
                    error_message="任务已取消",
                )
            )
            return
        except DownloadError as e:
            self._fail(task, e.code, e.message)
            return

        file_path = result.file_paths[0] if result.file_paths else None
        with self._lock:
            task.status = TaskStatus.DONE
            task.phase = "done"
            task.file_path = str(file_path) if file_path else None
        self._emit(
            ProgressEvent(
                task_id=task.id,
                status="done",
                phase="done",
                progress=1.0,
                downloaded=task.downloaded,
                total=task.total,
            )
        )

    # ---- 内部工具 ----

    def _set(self, task: Task, **fields) -> None:
        with self._lock:
            for k, v in fields.items():
                setattr(task, k, v)

    def _fail(self, task: Task, code: str, message: str) -> None:
        with self._lock:
            task.status = TaskStatus.FAILED
            task.phase = "failed"
            task.error_code = code
            task.error_message = message
            task.cancel_event.clear()
        self._emit(
            ProgressEvent(
                task_id=task.id,
                status="failed",
                phase="failed",
                error_code=code,
                error_message=message,
            )
        )

    def _emit(self, event: ProgressEvent) -> None:
        if self.on_event is not None:
            try:
                self.on_event(event)
            except Exception as exc:  # noqa: BLE001 - 事件出口异常不影响任务流程
                logging.getLogger(__name__).warning(
                    "任务事件回调异常: %s", exc, exc_info=False
                )

    # ---- 输出 ----

    def to_response(self, task: Task) -> TaskResponse:
        return TaskResponse(
            id=task.id,
            source=task.request.source,
            kind=task.request.kind,
            input_url=task.input_url,
            entry_count=len(task.request.entries),
            status=task.status,
            phase=task.phase,
            title=task.title,
            progress=task.progress,
            downloaded=task.downloaded,
            total=task.total,
            speed=task.speed,
            eta=task.eta,
            error_code=task.error_code,
            error_message=task.error_message,
            output_dir=str(task.output_dir),
            file_path=task.file_path,
            created_at=task.created_at,
        )