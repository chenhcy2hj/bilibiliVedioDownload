"""任务相关数据模型。"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"
    INTERRUPTED = "interrupted"  # 进程重启时未完成任务，归入历史（P3）


class TaskCreateRequest(BaseModel):
    urls: list[str] = Field(min_length=1, description="支持的链接：标准BV/裸BV/b23.tv短链")
    audio_format: str = Field(default="mp3", description="输出音频格式")
    audio_quality: str = Field(default="192", description="输出音频码率 kbps")


class TaskResponse(BaseModel):
    id: str
    source: str
    kind: str
    input_url: str
    entry_count: int
    status: TaskStatus
    phase: str = ""
    title: str | None = None
    """视频标题（探测阶段回传），前端任务行"名称"展示；未探测时为 None。"""
    progress: float | None = None
    """0~1 统一下载进度（total 缺失的分片下载用片段比例兜底）。"""
    downloaded: float | None = None
    total: float | None = None
    speed: float | None = None
    eta: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    output_dir: str = ""
    file_path: str | None = None
    created_at: datetime
    finished_at: datetime | None = None