"""TaskManager：任务状态机 + 串行执行队列 + 进度事件回调。

线程模型：yt-dlp 为同步阻塞调用，使用单工作线程串行消费队列（反爬友好）；
进度经 on_event 回调同步转发（M3 接入 WebSocket 推送）。
"""
import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.cookie.service import CookieService
from app.core.downloader.base import DownloadError, ProgressEvent, TaskCanceled
from app.core.downloader.ytdlp import YtDlpDownloader
from app.core.settings.service import SettingsService
from app.core.task.persist import ACTIVE_STATUSES, HistoryStore, TaskRecord
from app.core.url.base import MediaItem, ParsedRequest
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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None  # 终态时间（done/failed/canceled/interrupted）
    cancel_event: threading.Event = field(default_factory=threading.Event)


# 终态集合（finished_at 赋值 + 进历史分组的判断依据）
TERMINAL_STATUSES = {
    TaskStatus.DONE,
    TaskStatus.FAILED,
    TaskStatus.CANCELED,
    TaskStatus.INTERRUPTED,
}


class TaskManager:
    def __init__(
        self,
        settings: SettingsService,
        cookie: CookieService,
        downloader=None,
        history: HistoryStore | None = None,
    ) -> None:
        self._settings = settings
        self._cookie = cookie
        self._downloader = downloader or YtDlpDownloader()
        self._history = history if history is not None else HistoryStore()
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
        self._persist()  # pending 也写盘：重启后可恢复为 interrupted
        self._start_worker_if_needed()
        return task

    def cancel(self, task_id: str) -> Task | None:
        task = self.get(task_id)
        if task is None:
            return None
        if task.status in TERMINAL_STATUSES:
            return task
        task.cancel_event.set()
        return task

    # ---- 启动恢复（app 启动时调用） ----

    def load_history(self) -> None:
        """恢复历史：终态任务直接进 _tasks（不回队、不进进行中）；
        进行中任务改写为 interrupted（finished_at=now）并写回。
        恢复的任务不发 WS 增量事件（snapshot/列表自然可见）。
        """
        records = self._history.load()
        if not records:
            return
        now = datetime.now(timezone.utc)
        rewrote = False
        restored: list[Task] = []
        with self._lock:
            for rec in records:
                if rec.id in self._tasks:
                    continue
                if TaskStatus(rec.status) in ACTIVE_STATUSES:
                    rec.status = TaskStatus.INTERRUPTED.value
                    rec.finished_at = now.isoformat()
                    rewrote = True
                restored.append(self._restored_task(rec))
            for task in restored:
                self._tasks[task.id] = task
        if rewrote:
            self._persist()

    def _restored_task(self, rec: TaskRecord) -> Task:
        """历史记录 → 只读 Task（request 仅保留展示所需字段，不重新入队）。"""
        return Task(
            id=rec.id,
            input_url=rec.input_url,
            request=ParsedRequest(
                source=rec.source,
                kind=rec.kind,
                entries=[MediaItem(url="") for _ in range(rec.entry_count)],
            ),
            output_dir=Path(""),
            status=TaskStatus(rec.status),
            title=rec.title,
            error_code=rec.error_code,
            error_message=rec.error_message,
            file_path=rec.file_path,
            created_at=self._history._parse_iso(rec.created_at) or datetime.now(timezone.utc),
            finished_at=self._history._parse_iso(rec.finished_at),
        )

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

        self._set_status(task, TaskStatus.PARSING, "parsing")

        def on_progress(event: ProgressEvent) -> None:
            if event.status == "metadata":
                # 探测完成：记录视频标题（任务"名称"展示）
                self._set(task, title=event.title)
                self._emit(event)
                return
            if event.status == "finished":
                self._set_status(task, TaskStatus.CONVERTING, "converting")
                self._set(
                    task,
                    progress=1.0,
                    downloaded=event.downloaded,
                    total=event.total,
                )
                self._emit(event)
                return
            if event.status == "downloading":
                self._set_status(task, TaskStatus.DOWNLOADING, "downloading")
                self._set(
                    task,
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
            self._set(
                task,
                error_code="canceled",
                error_message="任务已取消",
            )
            task.cancel_event.clear()
            self._set_status(task, TaskStatus.CANCELED, "canceled")
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
        self._set(task, file_path=str(file_path) if file_path else None)
        self._set_status(task, TaskStatus.DONE, "done")
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

    def _set_status(self, task: Task, status: TaskStatus, phase: str | None = None) -> None:
        """统一状态切换入口：status 实际变化时触发一次持久化（P3）。

        - 进度事件（同一 status 反复设置）不写盘；
        - 终态（done/failed/canceled/interrupted）记录 finished_at。
        """
        with self._lock:
            changed = task.status != status
            task.status = status
            if phase is not None:
                task.phase = phase
            if status in TERMINAL_STATUSES and task.finished_at is None:
                task.finished_at = datetime.now(timezone.utc)
        if changed:
            self._persist()

    def _persist(self) -> None:
        """全量快照写盘（进行中 + 终态）；失败由 HistoryStore 内部告警不抛出。"""
        with self._lock:
            tasks = list(self._tasks.values())
        self._history.save([HistoryStore.to_record(t) for t in tasks])

    def _fail(self, task: Task, code: str, message: str) -> None:
        # 先落字段再切状态：保证写盘快照含完整错误信息
        self._set(task, error_code=code, error_message=message)
        task.cancel_event.clear()
        self._set_status(task, TaskStatus.FAILED, "failed")
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
            finished_at=task.finished_at,
        )