"""YtDlpDownloader：复用现有 installVideo.py 的 yt-dlp 配置，接入进度/错误分类。

M5 增强：
- 先 extract_info(download=False) 预探测标题，生成唯一成品路径（重复文件自动加序号）；
- FFmpegLocator 定位 ffmpeg（PATH → 捆绑目录），找不到明确报错；
- 取消：钩子抛 DownloadCancelled 真正中止下载。
"""
from pathlib import Path
from threading import Event

import yt_dlp
from yt_dlp.utils import DownloadCancelled
from yt_dlp.utils import DownloadError as YtDownloadError

from app.config import BUNDLED_FFMPEG_DIR, REFERER, UA
from app.core.downloader.base import (
    Downloader,
    DownloadError,
    DownloadResult,
    ProgressEvent,
    TaskCanceled,
)
from app.core.downloader.ffmpeg import FFmpegLocator, FfmpegNotFoundError
from app.core.url.base import ParsedRequest


def classify_error(exc: Exception) -> DownloadError:
    """把 yt-dlp 原始异常分类为业务错误码。"""
    if isinstance(exc, TaskCanceled):
        return DownloadError("canceled", "任务已取消")
    if isinstance(exc, FfmpegNotFoundError):
        return DownloadError("convert", str(exc))
    msg = str(exc)
    if isinstance(exc, YtDownloadError):
        if "HTTP Error 412" in msg:
            return DownloadError("auth", "B站返回 412（反爬），Cookie 可能已失效，请重新获取")
        if "ffmpeg" in msg.lower() or "postprocessing" in msg.lower():
            return DownloadError("convert", f"转码失败（检查 FFmpeg 是否可用）: {msg[:200]}")
        if "HTTP Error 404" in msg:
            return DownloadError("not_found", "资源不存在（分P 可能不存在或视频已删除）")
        if "Read timed out" in msg or "Connection" in msg or "temporary" in msg.lower():
            return DownloadError("network", f"网络错误: {msg[:200]}")
        return DownloadError("network", f"下载失败: {msg[:200]}")

    if isinstance(exc, PermissionError):
        return DownloadError("path", "输出目录不可写，请检查设置")
    if isinstance(exc, OSError):
        return DownloadError("path", f"文件系统错误: {exc}")
    return DownloadError("network", f"未知错误: {exc}")


def unique_path(output_dir: Path, filename: str) -> Path:
    """同名文件已存在时自动加序号： title.mp3 → "title (1).mp3" → (2)…"""
    target = output_dir / filename
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    i = 1
    while (output_dir / f"{stem} ({i}){suffix}").exists():
        i += 1
    return output_dir / f"{stem} ({i}){suffix}"


def calc_progress(d: dict) -> float | None:
    """统一下载进度（0~1）：

    1. 字节比例：total_bytes / total_bytes_estimate 已知时；
    2. 片段比例兜底：B 站 DASH 分片下载 total 为 None，用 fragment_index/fragment_count；
    3. 两者都未知 → None（由前端显示不确定态）。
    """
    total = d.get("total_bytes") or d.get("total_bytes_estimate")
    downloaded = d.get("downloaded_bytes") or 0
    if total:
        return min(downloaded / total, 1.0)
    index = d.get("fragment_index")
    count = d.get("fragment_count")
    if count and index:
        return min(index / count, 1.0)
    return None


class YtDlpDownloader(Downloader):
    def __init__(self, ffmpeg_locator: FFmpegLocator | None = None) -> None:
        self._ffmpeg = ffmpeg_locator or FFmpegLocator(bundled_dir=BUNDLED_FFMPEG_DIR)

    def download(
        self,
        request: ParsedRequest,
        task_id: str,
        output_dir: Path,
        cookie_file: Path | None,
        cancel_event: Event,
        on_progress: callable,
    ) -> DownloadResult:
        result = DownloadResult(ok=False)
        audio_format = request.options.get("audio_format", "mp3")
        audio_quality = request.options.get("audio_quality", "192")

        # FFmpeg 定位：找不到直接失败并给可读指引
        try:
            ffmpeg_bin = self._ffmpeg.locate()
            ffmpeg_location = str(ffmpeg_bin.parent)
        except FfmpegNotFoundError as e:
            raise DownloadError("convert", str(e))

        for entry in request.entries:
            if cancel_event.is_set():
                raise TaskCanceled()

            base_opts = self._base_opts(
                output_dir=output_dir,
                cookie_file=cookie_file,
                ffmpeg_location=ffmpeg_location,
            )
            progress_ctx = {"downloaded": 0.0, "total": None, "progress": None}

            def make_hooks(ctx: dict):
                def progress_hook(d: dict, _ctx: dict = ctx) -> None:
                    if cancel_event.is_set():
                        raise DownloadCancelled("任务已取消")
                    status = d.get("status")
                    if status == "downloading":
                        downloaded = d.get("downloaded_bytes") or 0
                        total = d.get("total_bytes") or d.get("total_bytes_estimate")
                        progress = calc_progress(d)
                        ctx["downloaded"] = downloaded or 0
                        ctx["total"] = total
                        ctx["progress"] = progress
                        on_progress(
                            ProgressEvent(
                                task_id=task_id,
                                status="downloading",
                                phase="downloading",
                                progress=progress,
                                downloaded=downloaded,
                                total=total,
                                speed=d.get("speed"),
                                eta=d.get("eta"),
                            )
                        )
                    elif status == "finished":
                        on_progress(
                            ProgressEvent(
                                task_id=task_id,
                                status="finished",
                                phase="converting",
                                progress=1.0,
                                downloaded=ctx["downloaded"],
                                total=ctx["total"],
                            )
                        )

                def postprocessor_hook(d: dict, _ctx: dict = ctx) -> None:
                    if cancel_event.is_set():
                        raise DownloadCancelled("任务已取消")
                    if d.get("status") == "started":
                        on_progress(
                            ProgressEvent(
                                task_id=task_id,
                                status="converting",
                                phase="converting",
                                downloaded=ctx["downloaded"],
                                total=ctx["total"],
                            )
                        )

                return [progress_hook], [postprocessor_hook]

            # 1. 预探测标题（download=False），用于唯一成品路径
            try:
                with yt_dlp.YoutubeDL(base_opts) as ydl:
                    info = ydl.extract_info(entry.url, download=False)
            except TaskCanceled:
                raise
            except DownloadCancelled as e:
                if cancel_event.is_set():
                    raise TaskCanceled() from e
                raise classify_error(e)
            except Exception as e:  # yt-dlp 异常种类繁多，统一分类
                if cancel_event.is_set():
                    raise TaskCanceled() from e
                raise classify_error(e)

            title = (info or {}).get("title") or f"video-{task_id[:8]}"
            final_path = unique_path(output_dir, f"{title}.{audio_format}")
            progress_hooks, postprocessor_hooks = make_hooks(progress_ctx)
            # 探测完成：把视频标题回传任务（前端"名称"展示用）
            on_progress(
                ProgressEvent(
                    task_id=task_id,
                    status="metadata",
                    phase="parsing",
                    title=title,
                )
            )

            # 2. 正式下载：outtmpl 直接指向唯一成品路径（无 %(title)s，杜绝覆盖）
            ydl_opts = {
                **base_opts,
                "outtmpl": str(final_path.with_suffix("")) + ".%(ext)s",
                "progress_hooks": progress_hooks,
                "postprocessor_hooks": postprocessor_hooks,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": audio_format,
                        "preferredquality": audio_quality,
                    }
                ],
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(entry.url, download=True)
            except TaskCanceled:
                raise
            except DownloadCancelled as e:
                if cancel_event.is_set():
                    raise TaskCanceled() from e
                raise classify_error(e)
            except Exception as e:  # yt-dlp 异常种类繁多，统一分类
                if cancel_event.is_set():
                    raise TaskCanceled() from e
                raise classify_error(e)

            if final_path.exists() and final_path not in result.file_paths:
                result.file_paths.append(final_path)

        result.ok = True
        return result

    def _base_opts(
        self,
        output_dir: Path,
        cookie_file: Path | None,
        ffmpeg_location: str,
    ) -> dict:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "http_headers": {"User-Agent": UA, "Referer": REFERER},
            "extractargs": {"bilibili": {"prefer_multi_flv": False}},
            "retries": 2,
            "ffmpeg_location": ffmpeg_location,
        }
        if cookie_file is not None:
            opts["cookiefile"] = str(cookie_file)
        return opts