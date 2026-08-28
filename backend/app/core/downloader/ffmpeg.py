"""FFmpeg 定位器：系统 PATH → 应用捆绑目录 → 明确报错。

打包版（M6）把 ffmpeg 静态二进制随产物分发，运行时按此顺序定位：
1. 系统 PATH（用户自装）
2. 应用捆绑目录（spec 数据文件 / sys._MEIPASS）
"""
import shutil
from pathlib import Path


class FfmpegNotFoundError(Exception):
    """定位失败：给出明确指引而非静默失败。"""


class FFmpegLocator:
    def __init__(self, bundled_dir: Path | None = None) -> None:
        self._bundled_dir = bundled_dir

    def locate(self) -> Path:
        exe = shutil.which("ffmpeg")
        if exe:
            return Path(exe)
        if self._bundled_dir is not None:
            for name in ("ffmpeg", "ffmpeg.exe"):
                candidate = self._bundled_dir / name
                if candidate.exists():
                    return candidate
        raise FfmpegNotFoundError(
            "FFmpeg 未找到：系统 PATH 与应用捆绑目录均不存在，"
            "请安装 FFmpeg 并加入 PATH，或重新安装本应用"
        )