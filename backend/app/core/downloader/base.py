"""下载器接口：解析结果 → 本地音频文件，含进度回调与错误分类。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

from app.core.url.base import ParsedRequest


@dataclass
class ProgressEvent:
    task_id: str
    status: str                    # downloading / converting / finished / error / metadata
    phase: str = ""                # downloading / converting / parsing
    title: str | None = None       # metadata 事件携带视频标题
    progress: float | None = None  # 0~1 统一进度（字节比例；分片下载用片段比例兜底）
    downloaded: float | None = None
    total: float | None = None
    speed: float | None = None
    eta: float | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class DownloadResult:
    ok: bool
    file_paths: list[Path] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class DownloadError(Exception):
    """下载失败，携带分类码。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class TaskCanceled(Exception):
    """任务被用户取消。"""


class Downloader(ABC):
    @abstractmethod
    def download(
        self,
        request: ParsedRequest,
        task_id: str,
        output_dir: Path,
        cookie_file: Path | None,
        cancel_event: Event,
        on_progress: callable,
    ) -> DownloadResult:
        """下载并转码 request 的 entries；通过 on_progress 上报 ProgressEvent。"""