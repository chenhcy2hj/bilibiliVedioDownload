# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：BiliDownloader 桌面应用。

- onedir 模式（COLLECT）；macOS 额外生成 .app（BUNDLE，zip 直解压运行）
- 资源捆绑：frontend/dist（前端产物）、ffmpeg 静态二进制（对应平台/架构）
- 排除 playwright（打包版不捆绑 Chromium，Cookie 走手动/粘贴引导）
- 构建产物：dist/BiliDownloader/（Windows），dist/BiliDownloader.app（macOS）
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent             # 项目根（本 spec 位于 packaging/ 下）
BACKEND = ROOT / "backend"
FRONTEND_DIST = ROOT / "frontend" / "dist"

if sys.platform == "darwin":
    FFMPEG_DIR = ROOT / "packaging" / "ffmpeg-macos-arm64"
else:
    FFMPEG_DIR = ROOT / "packaging" / "ffmpeg-windows-x64"

datas = [
    (str(FRONTEND_DIST), "frontend/dist"),
    (str(FFMPEG_DIR), "ffmpeg"),
]

# uvicorn 动态导入的模块需显式收集
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "pywebview.platforms.base",
]
if sys.platform == "darwin":
    hiddenimports += [
        "pywebview.platforms.cocoa",
        "pywebview.platforms.cocoa_frame",
    ]
else:
    hiddenimports += ["pywebview.platforms.edgechromium", "pythonnet", "clr_loader"]

excludes = ["playwright", "playwright._impl", "pytest", "tests"]

a = Analysis(
    [str(BACKEND / "app" / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BiliDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI 应用（无终端窗口）
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="BiliDownloader",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="BiliDownloader.app",
        icon=None,
        bundle_identifier="local.bilidownloader",
        info_plist={
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )