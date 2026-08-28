"""设置模块：应用可配置项（v1 至少输出目录）的读取、校验与持久化。

持久化文件：data/settings.json；未配置项回落默认值。
"""
import json
import os
from pathlib import Path

from app.api.errors import ApiError

DEFAULT_SETTINGS = {
    "output_dir": None,   # None 表示使用默认输出目录（不写盘）
}


class SettingsService:
    def __init__(self, settings_file: Path, default_output_dir: Path) -> None:
        self._settings_file = settings_file
        self._default_output_dir = default_output_dir
        self._data: dict = self._load()

    # ---- 读取 ----

    def _load(self) -> dict:
        raw = dict(DEFAULT_SETTINGS)
        try:
            if self._settings_file.exists():
                raw.update(json.loads(self._settings_file.read_text("utf-8")))
        except (json.JSONDecodeError, OSError):
            pass  # 损坏的配置按默认处理
        return raw

    def get_settings(self) -> dict:
        output_dir = self._data.get("output_dir") or str(self._default_output_dir)
        return {
            "output_dir": str(output_dir),
            "audio_format": "mp3",
            "audio_quality": "192",
        }

    def get_output_dir(self) -> Path:
        return Path(self.get_settings()["output_dir"])

    # ---- 修改 ----

    def set_output_dir(self, path: str) -> dict:
        """校验（绝对路径 → 自动创建 → 可写检查）→ 持久化 → 返回新设置。"""
        p = Path(path.strip())
        if not p.is_absolute():
            raise ApiError("INVALID_PATH", "输出目录必须是绝对路径", status_code=422)
        if p.exists() and not p.is_dir():
            raise ApiError("INVALID_PATH", "路径已存在但不是目录", status_code=422)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            raise ApiError("INVALID_PATH", "路径已存在但不是目录", status_code=422)
        except OSError as e:
            raise ApiError("PATH_NOT_WRITABLE", f"无法创建输出目录: {e}", status_code=422)
        if not p.is_dir():
            raise ApiError("INVALID_PATH", "路径已存在但不是目录", status_code=422)
        if not os.access(p, os.W_OK):
            raise ApiError("PATH_NOT_WRITABLE", "输出目录不可写，请检查权限", status_code=422)
        # 写入探针，进一步确认可写性
        probe = p / ".bili_write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as e:
            raise ApiError("PATH_NOT_WRITABLE", f"输出目录不可写: {e}", status_code=422)

        self._data["output_dir"] = str(p)
        self._persist()
        return self.get_settings()

    def _persist(self) -> None:
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)
        self._settings_file.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )