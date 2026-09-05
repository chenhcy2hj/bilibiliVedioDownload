# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：BiliDownloader 桌面应用。

- onedir 模式（COLLECT）；macOS 额外生成 .app（BUNDLE，zip 直解压运行）
- 资源捆绑：frontend/dist（前端产物）、ffmpeg 静态二进制（对应平台/架构）
- Chromium 不在本 spec 捆绑（P5 实施修正 2026-09-05）：macOS 上 PyInstaller 对
  收集二进制执行 ad-hoc 签名会失败（Chrome.app 含嵌套 Framework 无法重签）；
  改由 release.yml 打包完成后直接拷贝 ms-playwright 缓存目录进产物
  （macOS Contents/Frameworks/_browsers；Windows _internal/_browsers），
  保留 Google 原始签名，运行时通过 PLAYWRIGHT_BROWSERS_PATH 定位。
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

# playwright 库随包（供 Playwright 运行时定位捆绑的 Chromium）；pytest/tests 不打包
excludes = ["pytest", "tests"]

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