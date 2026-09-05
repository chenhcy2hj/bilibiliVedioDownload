"""静态配置与路径解析。

开发模式：数据目录固定项目内 data/；
打包模式（M5/M6）：迁移到平台用户目录（sys.frozen 检测）。
"""
import os
import sys
from pathlib import Path

APP_NAME = "BiliDownloader"
APP_VERSION = "0.1.1"

DEV_HOST = "127.0.0.1"
DEV_PORT = 8000

# 项目根目录（backend/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _platform_data_dir() -> Path:
    """打包模式下的平台用户数据目录（M5 启用，开发模式不用）。"""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False))


def resolve_data_dir(is_frozen: bool) -> Path:
    """数据目录解析（可单测）：打包模式 → 平台用户目录；开发模式 → 项目内 data/。"""
    if is_frozen:
        return _platform_data_dir()
    return PROJECT_ROOT / "data"


# 数据目录：开发模式项目内 data/；打包模式平台用户目录
# 可用环境变量 BILIDL_DATA_DIR 覆盖（测试隔离用）
DATA_DIR = Path(os.environ["BILIDL_DATA_DIR"]) if os.environ.get("BILIDL_DATA_DIR") else resolve_data_dir(is_packaged())

DEFAULT_OUTPUT_DIR = DATA_DIR / "downloads"

COOKIE_RAW_FILE = DATA_DIR / "bilibiliCookie.txt"
COOKIE_NETSCAPE_FILE = DATA_DIR / "bilibiliCookie_netscape.txt"
SETTINGS_FILE = DATA_DIR / "settings.json"

# 兼容旧版：Cookie 文件曾在项目根目录
LEGACY_COOKIE_RAW = PROJECT_ROOT / "bilibiliCookie.txt"

# 历史数据目录（打包模式首次启动时若检测到则迁移一次，避免重复搬移）
LEGACY_DATA_DIRS: list[Path] = [Path.home() / ".bili-downloader"]

# FFmpeg 捆绑目录：打包版由 PyInstaller 置入 _MEIPASS/ffmpeg（M6）；
# 开发模式 None → FFmpegLocator 走系统 PATH
def _bundled_ffmpeg_dir() -> Path | None:
    if is_packaged():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.argv[0]).resolve().parent))
        return base / "ffmpeg"
    return None


BUNDLED_FFMPEG_DIR = _bundled_ffmpeg_dir()

# Bilibili 接口
BILI_HOST = "https://www.bilibili.com"
BILI_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
BILI_JUMP_URL = "https://www.bilibili.com/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
REFERER = "https://www.bilibili.com"

# 默认音频规格
DEFAULT_AUDIO_FORMAT = "mp3"
DEFAULT_AUDIO_QUALITY = "192"

# 单次提交 URL 上限（v0.1.1 P2）
MAX_URLS_PER_BATCH = 10

# 任务历史持久化（v0.1.1 P3）：终态任务写盘；保留最近 N 条
TASKS_FILE = DATA_DIR / "tasks.json"
MAX_HISTORY = 500