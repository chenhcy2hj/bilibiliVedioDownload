"""任务历史持久化：data/tasks.json 原子写盘、按量裁剪、启动恢复（v0.1.1 P3）。

约定：
- 只保存终态字段（不保存进度/速度等瞬时量）；
- 写盘为全量快照（进行中 + 终态任务），由 TaskManager 在状态机变更点调用；
- 进度事件（200ms 级）不写盘；
- 原子写入（tmp 文件 + os.replace）+ threading.Lock（worker 线程与 API 线程并发）；
- 写盘失败仅日志告警，不影响任务运行。
"""
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app.config import MAX_HISTORY, TASKS_FILE
from app.schemas.task import TaskStatus

logger = logging.getLogger(__name__)

# 进行中状态：进程重启后自动改写为 interrupted（归入历史）
ACTIVE_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.PARSING,
    TaskStatus.DOWNLOADING,
    TaskStatus.CONVERTING,
}


@dataclass
class TaskRecord:
    """tasks.json 中的单条记录（终态字段；瞬时量不落盘）。"""

    id: str
    input_url: str
    source: str
    kind: str
    entry_count: int
    title: str | None
    status: str
    error_code: str | None
    error_message: str | None
    file_path: str | None
    created_at: str  # ISO 字符串
    finished_at: str | None


class HistoryStore:
    """tasks.json 读写；损坏容错、原子写入、按 created_at 裁剪。"""

    def __init__(self, path: Path = TASKS_FILE, max_history: int = MAX_HISTORY) -> None:
        self.path = Path(path)
        self.max_history = max_history
        self._lock = threading.Lock()

    # ---- 读 ----

    def load(self) -> list[TaskRecord]:
        """读取历史；文件缺失/损坏/非法行 → 跳过（不崩溃，按空历史启动）。"""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except Exception as exc:  # noqa: BLE001 - 损坏文件容错
            logger.warning("任务历史读取失败（按空历史启动）: %s", exc)
            return []
        records: list[TaskRecord] = []
        for item in raw.get("tasks", []) if isinstance(raw, dict) else []:
            try:
                if not self._valid(item):
                    continue
                records.append(TaskRecord(**item))
            except (TypeError, ValueError):
                logger.warning("跳过非法历史记录: %s", item)
        return records

    @staticmethod
    def _valid(item: dict) -> bool:
        """字段齐全 + status 是合法枚举值才接受。"""
        required = {
            "id", "input_url", "source", "kind", "entry_count", "title",
            "status", "error_code", "error_message", "file_path",
            "created_at", "finished_at",
        }
        if not required.issubset(item.keys()):
            return False
        try:
            TaskStatus(item["status"])
        except ValueError:
            return False
        return True

    # ---- 写 ----

    def save(self, records: list[TaskRecord]) -> bool:
        """全量写盘 + 按 created_at 保留最新 max_history 条；返回是否写成功。

        锁保护：worker 线程与 API 线程可能并发触发写盘，同一时刻只允许一个
        写盘（tmp 文件唯一，避免交错覆盖）。
        """
        ordered = sorted(records, key=lambda r: r.created_at, reverse=True)
        trimmed = ordered[: self.max_history]
        payload = {"tasks": [asdict(r) for r in trimmed]}
        with self._lock:
            try:
                tmp = self.path.with_name(self.path.name + ".tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)
                return True
            except Exception as exc:  # noqa: BLE001 - 磁盘满等：仅告警不影响任务
                logger.warning("任务历史写盘失败: %s", exc)
                return False

    # ---- 序列化辅助 ----

    @staticmethod
    def to_record(task) -> TaskRecord:
        """Task → TaskRecord（终态字段；瞬时量丢弃）。"""
        return TaskRecord(
            id=task.id,
            input_url=task.input_url,
            source=task.request.source,
            kind=task.request.kind,
            entry_count=len(task.request.entries),
            title=task.title,
            status=task.status.value,
            error_code=task.error_code,
            error_message=task.error_message,
            file_path=task.file_path,
            created_at=task.created_at.isoformat(),
            finished_at=task.finished_at.isoformat() if task.finished_at else None,
        )

    @staticmethod
    def _parse_iso(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None