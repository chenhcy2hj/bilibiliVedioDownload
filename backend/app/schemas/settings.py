"""应用设置数据模型。"""
from pydantic import BaseModel, Field


class AppSettings(BaseModel):
    output_dir: str
    audio_format: str = "mp3"
    audio_quality: str = "192"


class SettingsUpdateRequest(BaseModel):
    output_dir: str = Field(min_length=1, description="下载输出目录（绝对路径）")