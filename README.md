# Bilibili Audio Downloader

从B站视频下载音频并转换为MP3格式。

---

## ⚠️ 个人使用声明

> 本项目仅供**个人学习、技术研究**使用，请勿用于商业用途或任何盈利目的。

- 请遵守[哔哩哔哩用户服务协议](https://www.bilibili.com/blackboard/blackboard-help.html)及中华人民共和国相关法律法规；
- 请仅下载您本人拥有版权或有权限获取的内容；**请勿下载、传播受版权保护的商业内容**；
- 使用本项目产生的任何风险（包括但不限于账号风控、封禁、法律纠纷）由使用者自行承担；
- 输出内容仅限个人学习交流，如需公开使用，请事先获得相应权利人的授权；
- 如本项目内容涉及您的合法权益，请联系作者删除相关内容。

---

## Web 界面功能

- **条形码动态进度条**：纯白主题；下载中条纹滚动动画、转码琥珀色、完成绿色静态条码，附实时百分比与速度；
- **多形态链接解析**：支持标准链接（带/不带尾斜杠）、裸 BV 号、b23.tv 短链、多P 分集（`?p=`）；
- **Cookie 一键无感获取**：点击"获取 Cookie"后端弹出浏览器窗口，扫码/登录后**自动捕获、校验并保存**（无需复制粘贴或书签操作）；书签脚本与手动粘贴保留为兜底；Cookie 失效时自动联动提示；
- **下载目录可配置**：设置面板修改输出目录（打包版支持系统原生目录选择器）；
- **批量任务**：多行 URL 一次创建，串行下载（反爬友好），支持取消与成品下载。

## 开发模式运行（Web 版）

> 完整架构设计见 `docs/design-analysis.md`；各阶段开发任务与规范见 `docs/development-guide.md`。

**一次性依赖安装：**

```bash
# 1. FFmpeg（macOS：brew install ffmpeg；其他平台官网下载并加入 PATH）
brew install ffmpeg

# 2. 后端虚拟环境（需 Python 3.12）
python3.12 -m venv venv
venv/bin/pip install -r requirements.txt

# 3. 前端依赖（Node 18+）
cd frontend
npm install
npm install three
```

**启动（两个终端）：**

```bash
# 终端 1：后端（http://127.0.0.1:8000）
cd backend
../venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
# 终端 2：前端（http://localhost:5173）
cd frontend
npm run dev
```

浏览器打开 `http://localhost:5173` 即可看到页面；后端健康检查可访问 `http://127.0.0.1:8000/api/health`。

> 端口约定（开发模式）：后端 `8000`、前端 `5173`。打包版使用动态端口（见设计文档 §5.1）。

## 桌面版（macOS / Windows 打包）

**双平台全部由 GitHub Actions 远端构建并自动发布**（无需本地打包）：

```bash
git tag -a v0.1.1 -m "release"
git push origin v0.1.1
```

推送 `v*` 标签后自动完成：macOS arm64（macos-15 runner）+ Windows x64 并行构建 → 自动创建/更新 GitHub Release 并上传两个 zip。Release 地址：`https://github.com/chenhcy2hj/bilibiliVedioDownload/releases`。

**使用要点：**
- 双击 `BiliDownloader.app` 启动（未签名应用首次需右键 → 打开）；
- 打包版数据目录与开发模式隔离：macOS `~/Library/Application Support/BiliDownloader`、Windows `%APPDATA%\BiliDownloader`；
- 动态端口 + 随机 token 防本地越权（API 需 `X-Auth-Token`，页面自动携带）；
- 打包版未捆绑浏览器组件，"获取 Cookie"请使用手动粘贴方式（书签回传仅开发模式适用）；

**生产模式（单端口，无需 Vite）：**

```bash
# 1. 构建前端产物（frontend/dist）
cd frontend
npm run build

# 2. 启动后端（自动托管前端页面，同一端口访问）
cd backend
../venv/bin/uvicorn app.main:app --port 8000
```

浏览器打开 `http://127.0.0.1:8000` 即可，页面与 API 同源（WebSocket 无需代理）。

**常见问题排查：**

| 现象 | 处理 |
|------|------|
| 页面打不开 / 连接状态一直 closed | 确认后端在 `8000` 端口运行（`curl http://127.0.0.1:8000/api/health`） |
| 前端连不上后端 API | 开发模式确认后端在 `8000`（Vite 代理指向该端口）；生产模式确认构建后重启 uvicorn |
| 下载任务立刻失败提示 Cookie 失效 | 点"获取 Cookie"按引导用书签回传或粘贴（见 `docs/manual-test-plan.md` §4） |
| 端口 8000 被占用 | `lsof -i :8000` 找到占用进程后关闭，或换 `--port 8001`（同步改 vite.config.js 代理目标） |
| 任务失败"转码失败（检查 FFmpeg）" | 确认 `ffmpeg -version` 可用 |

## 前置准备

### 1. Python 3

确保系统已安装 Python 3：

```bash
python3 --version
```

### 2. FFmpeg

音频转码依赖 FFmpeg，需提前安装：

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# 从 https://ffmpeg.org/download.html 下载并添加到 PATH
```

### 3. yt-dlp

建议在虚拟环境中安装：

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install yt-dlp
```

### 4. B站Cookie

由于B站反爬机制，必须提供登录Cookie才能下载。

**获取Cookie步骤：**

1. 在浏览器中登录 [bilibili.com](https://www.bilibili.com)
2. 按 `F12` 打开开发者工具 → `Network` 标签
3. 刷新页面，点击任意请求，在请求头中找到 `Cookie` 字段
4. 复制完整的Cookie值，保存到 `bilibiliCookie.txt` 文件中

**Cookie文件格式：** 一行纯文本，格式如：

```
key1=value1; key2=value2; key3=value3
```

**转换为yt-dlp可用格式：**

```bash
python3 convert_cookie.py
```

这会生成 `bilibiliCookie_netscape.txt`，供下载脚本使用。

> Cookie有效期有限，如遇到412错误，请重新获取Cookie。

## 使用方法

### 下载单个视频

编辑 `installVideo.py` 底部的URL：

```python
if __name__ == "__main__":
    url = "https://www.bilibili.com/video/BVxxxxxxxx"
    extract_audio(url)
```

然后运行：

```bash
source venv/bin/activate   # Windows: venv\Scripts\activate
python installVideo.py
```

### 批量下载

将多个URL填入列表：

```python
if __name__ == "__main__":
    urls = [
        "https://www.bilibili.com/video/BV1PN411P7RZ",
        "https://www.bilibili.com/video/BV17t4y1N72d",
        # ... 更多URL
    ]
    for url in urls:
        extract_audio(url)
```

### 输出

音频文件保存在 `output/` 目录下，默认格式为 MP3（192kbps）。

## 文件说明

| 文件 | 说明 |
|------|------|
| `backend/` | FastAPI 后端（接口化：URL 解析 / 下载 / 任务 / Cookie / 设置模块） |
| `frontend/` | Vue3 + three.js 前端（3D 任务可视化 + 2D 操作面板） |
| `docs/` | 设计文档（design-analysis.md）与阶段开发指导（development-guide.md） |
| `installVideo.py` | 旧版 CLI 脚本，下载B站视频并提取音频（新架构上线后保留） |
| `convert_cookie.py` | 旧版 Cookie 转换脚本（逻辑已内聚到后端 CookieStore，保留兼容） |
| `requirements.txt` | 后端依赖版本锁定 |
| `bilibiliCookie.txt` | 从浏览器获取的原始Cookie（需自行获取，不上传至仓库） |
| `bilibiliCookie_netscape.txt` | 转换后的Cookie（自动生成，不上传至仓库） |
| `output/` | 旧版 CLI 输出目录（Web 版经设置面板可配置输出位置） |
