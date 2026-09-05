# B站音频下载器 —— 功能分析与重构设计草案（v0.1）

> 本文档仅做分析与设计，不包含实现。用于为下一阶段编码准备材料、确定实现方式。

---

## 一、现有项目分析

### 1.1 功能定位

目前是一个**命令行**B站音频下载工具：

| 文件 | 职责 |
|------|------|
| `installVideo.py` | 主脚本：yt-dlp 下载音流 → FFmpeg 提取 → 输出 `output/*.mp3`（192kbps），支持 URL 列表批量 |
| `convert_cookie.py` | 把浏览器 Cookie 字符串转换为 yt-dlp 的 Netscape 格式（解决 412 反爬） |
| `output/` | 音频成品目录（当前已积累 20+ 首） |
| `README.md` | 环境准备 + 使用说明 |

### 1.2 环境实测（2025-08 本机）

| 依赖 | 状态 | 说明 |
|------|------|------|
| Python | ✅ 3.9.6（系统）/ 3.12（brew） | 建 venv 建议用 3.12 |
| Node / npm | ✅ v24.14.0 / 11.9.0 | 前端 Vite 可用 |
| FFmpeg | ❌ **未安装** | 转码必需，需 `brew install ffmpeg` |
| yt-dlp | ❌ 未安装 | 需 venv + pip |
| Cookie 文件 | ⚠️ 未创建 | 将接入 §2.2④ 接口化获取/校验流程（.gitignore 已排除） |

### 1.3 现有痛点

1. URL 硬编码在脚本 `__main__` 中，改任务要改源码；
2. 无进度展示（除控制台日志）；
3. 并发全开、失败仅打印后 continue，无任务级状态管理；
4. 只认 `bilibili.com/video/BVxxx`，换平台/换链接形态（短链、裸BV、合集、音频区）都要改代码；
5. 每次运行是"一次性脚本"，无服务化能力；
6. Cookie 获取/校验/转换全手动，失效无感知（412 才知道）。

---

## 二、目标架构

### 2.1 总体结构

```
┌──────────────────────────────┐      REST / WebSocket
│  前端（Vite + Vue3，纯白主题） │ ◄─────────────────┐
│  · 任务面板：条形码动态进度条   │                   │
│  · DOM 叠层：URL 输入、选项、   │                   │
│    任务列表、成品下载          │                   │
└──────────────────────────────┘                   │
                                                    ▼
┌──────────────────────────────────────────────────────────┐
│  后端（Python + FastAPI，模块化 + 接口化）                  │
│                                                            │
│  url/        UrlParser 抽象接口 + Registry（可扩展解析器）   │
│  downloader/ Downloader 抽象接口 + YtDlp 实现               │
│  cookie/     CookieService（校验/存储/转换，接口化）         │
│  settings/   SettingsService（下载目录等用户可配置项）       │
│  task/       TaskManager（状态机 + 串行队列 + 进度事件）     │
│  api/        REST 路由 + WebSocket 进度推送                 │
│  schemas/    数据模型（Pydantic）                           │
│  config.py   配置（输出目录、Cookie、端口等）                │
└──────────────────────────────────────────────────────────┘
                                │ yt-dlp 子进程
                                ▼
                     B站 / 未来其他平台 + FFmpeg 转码
```

### 2.2 后端接口化核心（重点）

**① URL 解析接口 —— 本次扩展性设计的关键点**

```python
class UrlParser(ABC):
    source: str                      # 如 "bilibili"
    @abstractmethod
    def match(self, url: str) -> bool: ...          # 识别是否本解析器负责
    @abstractmethod
    def parse(self, url: str) -> ParsedRequest: ... # 解析成统一结构

class UrlParserRegistry:
    def register(self, parser: UrlParser): ...      # 插拔注册
    def dispatch(self, url: str) -> ParsedRequest: ... # 按 match 分发，未匹配抛 UnsupportedUrlError

# 统一输出结构
ParsedRequest {
    source: str,            # 来源平台标识
    kind: str,              # single / multi / audio / playlist
    entries: [MediaItem],   # 一个或多个条目（多P/合集）
    options: {...}          # 默认输出选项（格式、清晰度）
}
```

新增平台/新链接形态 = 新写一个 `UrlParser` 实现 + `registry.register()`，**不改动任何业务代码**。

**BilibiliParser 首批需识别的 3 种输入形态**（示例来自用户提供）：

| 输入形态 | 示例 | 处理方式 |
|----------|------|----------|
| 标准链接（带尾斜杠） | `https://www.bilibili.com/video/BV1hk4y1W76R/` | 正则提取 bvid |
| 标准链接（无尾斜杠） | `https://www.bilibili.com/video/BV1Z8h36gEnp` | 同上，尾斜杠可选 |
| 裸 BV 号（无域名） | `BV1JRuA6vEvd` | 无需网络请求，直接补全为标准链接 |

多P 选集（`?p=N` 参数）在 `parse()` 中提取并写入 `entries`（kind=multi）；b23.tv 短链先解析出真实地址，再走标准流程。

**② 下载器接口**

```python
class Downloader(ABC):
    @abstractmethod
    def download(self, request: ParsedRequest,
                 task_id: str,
                 on_progress: Callable[[ProgressEvent], None]) -> Result: ...
# 实现：YtDlpDownloader（复用现有 installVideo.py 的 yt-dlp 配置）
# 进度来源：yt-dlp progress_hooks / postprocessor_hooks
```

**③ 任务状态机**

`pending → parsing → downloading → converting → done`，分支 `failed / canceled`。
TaskManager 串行执行（降反爬风险），每步产生事件经 WebSocket 推给前端。

**④ Cookie 获取与校验模块（接口化）**

用户诉求：点击"获取 Cookie"时自动跳转 `https://www.bilibili.com/`，判断能否获取到 Cookie 及其有效性，**全部通过后端接口实现**。

**关键约束（浏览器同源策略）**：前端页面运行在 `127.0.0.1`，浏览器禁止其读取 `bilibili.com` 域下的 Cookie，因此"跳转后自动回读"在纯网页内无法实现，需要选择一种回传方式：

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **C. 浏览器自动捕获（已确认主路径）** | 后端 Playwright 弹出真实 Chromium 窗口（持久化登录态）→ 用户扫码/登录 → **自动捕获 Cookie、自动校验保存**，全程零复制粘贴 | 无感体验：点击"获取 Cookie"→ 登录 → 完成；二次获取复用登录态 | 依赖 Chromium（~360MB）；**v0.1.1 起捆绑进发布包**（roadmap P5），打包版恢复无感获取 |
| B. 书签小工具（兜底保留） | 前端新窗口打开 bilibili.com；用户登录后点击应用提供的"收藏夹 JS（bookmarklet）"，脚本在 B 站页面内读取 `document.cookie` 并 POST 回传本地后端 | 不依赖额外浏览器体积 | 首次需手动创建书签；仅开发模式固定端口可用 |
| A. 手动粘贴（兜底） | 跳转 B 站登录后 F12 复制 Cookie 粘贴回应用 | 零依赖、最稳 | 每次手动操作，繁琐 |

回传/捕获的 Cookie 统一由后端接口承接，**校验 → 判定 → 保存 → 转换** 一条链，全部接口化。**主路径为无感获取**（§2.2④方案表 C）：`POST /api/cookie/acquire` → 后端弹出浏览器 → 用户仅需登录 → 自动捕获保存；前端轮询 `GET /api/cookie/status`（`acquiring` 字段）直到结果。书签与粘贴为兜底。

```python
# core/cookie/ 模块
class CookieValidator(ABC):
    @abstractmethod
    def validate(self, cookie: str) -> CookieStatus: ...   # 是否有效 + 登录用户名

class BilibiliCookieValidator(CookieValidator):
    # 实现：带 Cookie 请求 https://api.bilibili.com/x/web-interface/nav
    # code == 0 → 有效；code == -101 → 未登录/失效

class CookieStore:
    def save_raw(self, cookie: str) -> Path          # 写 bilibiliCookie.txt
    def to_netscape(self) -> Path                    # 自动转换 bilibiliCookie_netscape.txt

class CookieService:                                  # 组合：校验 + 存储 + 转换
    def status(self) -> CookieStatus: ...             # 查询当前 Cookie 有效状态
    def submit(self, cookie: str) -> CookieStatus: ... # 校验 → 保存 → 转换 → 返回结果
```

**前端交互流程**：点击"获取 Cookie" → `POST /api/cookie/acquire` → 后端弹出 Chromium 窗口（持久化 profile，二次获取免登录）→ 用户扫码/登录 → **自动捕获并保存** → 前端轮询 `GET /api/cookie/status`（`acquiring=false` 且 `valid=true`）→ 页面展示登录用户名。书签脚本（`GET /api/cookie/guide`）与手动粘贴保留为兜底。下载前 TaskManager 会先经 `CookieService.status()` 检查，过期则任务直接失败并提示重取。

**⑤ 设置模块（下载目录可配置）**

用户诉求：下载文件的保存地址可修改，且通过接口实现。应用设置统一由 `SettingsService` 管理（v1 至少含输出目录，后续可扩展码率、并发数、yt-dlp 参数等）：

```python
# core/settings/ 模块
class SettingsService:
    def get_settings(self) -> AppSettings: ...          # 读取（默认值 + 用户配置合并）
    def set_output_dir(self, path: str) -> AppSettings: ... # 校验 → 创建目录 → 持久化 → 返回
    # 校验规则：必须绝对路径；不存在则自动创建（mkdir -p）；
    #           创建失败/不可写 → 返回明确错误原因
    # 持久化：data/settings.json（数据目录见 §5.1 #2），未配置项回落默认值

# 默认值（可被用户配置覆盖）
#   开发模式：output/；打包模式：平台用户数据目录
#   （macOS ~/Library/Application Support/BiliDownloader、Windows %APPDATA%\BiliDownloader）
```

**生效机制**：任务入队时 TaskManager 读取当前 `output_dir` 快照传给 Downloader（yt-dlp `outtmpl`）；修改设置后**新任务生效，不影响进行中的任务**。任务级目录覆盖（`ParsedRequest.options.output_dir`）作为扩展点预留，v1 不启用。

**前端交互**：设置面板显示当前下载目录 → pywebview 窗口内调用**原生目录选择对话框**（`window.pywebview` 文件夹选择）回填路径 → `PUT /api/settings` 提交；开发浏览器模式手动输入路径。校验失败由后端返回原因并展示。

### 2.3 前端设计（纯白主题 + 条形码进度条）

- **任务面板**：纯白主题；每个任务的进度条为**动态条形码样式**（条形码条纹），下载中条纹滚动动画（扫描效果），转码中变琥珀色，完成变绿色静态条码；附实时百分比与速度显示。
- **DOM 叠层**：URL 输入框（支持批量多行）、解析结果预览（标题/条目数/来源）、格式选择（默认 MP3 192k）、**设置面板（下载目录修改：pywebview 原生目录选择 / 手动输入）**、任务列表与状态徽标、成品文件下载按钮。
- **通信**：`fetch`（REST）+ 浏览器原生 `WebSocket`（进度）。
- 技术：**Vue 3 + Vite**（已确认）——纯白主题单页，无 3D 依赖（three.js 已按用户最新要求移除）。

### 2.4 API 草案（v1）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks` | 提交 URL（可多个），解析并入队 |
| GET | `/api/tasks` | 任务列表 + 状态 |
| DELETE | `/api/tasks/{id}` | 取消/删除任务 |
| GET | `/api/tasks/{id}/file` | 下载成品音频 |
| GET | `/api/capabilities` | 已注册解析器/支持的来源（前端据此展示） |
| GET | `/api/cookie/guide` | 获取 Cookie 引导（书签脚本、操作说明，兜底用） |
| POST | `/api/cookie/acquire` | **无感获取**：弹出浏览器窗口，登录后自动捕获+校验+保存（进行中 409） |
| POST | `/api/cookie` | 提交 Cookie（书签回传/粘贴兜底）：校验 → 保存并自动转 Netscape |
| GET | `/api/cookie/status` | 查询当前 Cookie 状态（valid/uname/acquiring/acquire_message） |
| GET | `/api/settings` | 查询应用设置（当前下载目录等） |
| PUT | `/api/settings` | 更新设置（输出目录）：校验 → 持久化 → 返回新值 |
| WS | `/api/ws` | 任务进度/状态事件推送 |

---

## 三、准备材料清单

### 3.1 软件材料（本机执行）
1. `brew install ffmpeg` —— **当前缺失，必装**；
2. `python3.12 -m venv venv` + `pip install fastapi uvicorn[standard] yt-dlp`；
3. 前端：`npm create vite@latest`（选择 Vue 模板）（Node 已有）。

### 3.2 账号 / 数据材料（需用户提供）
1. **B站登录 Cookie**：按 §2.2④ 的接口化流程获取（一键跳转 B 站 → 书签/粘贴回传 → 后端自动校验、保存并转换，无需手动处理文件格式）。有效期有限，失效时经 `POST /api/cookie` 重取；
2. **测试 URL**（用户提供，恰好覆盖解析器的 3 种输入形态）：

   | 输入形态 | URL |
   |----------|-----|
   | 标准链接（带尾斜杠） | `https://www.bilibili.com/video/BV1hk4y1W76R/` |
   | 标准链接（无尾斜杠） | `https://www.bilibili.com/video/BV1Z8h36gEnp` |
   | 裸 BV 号（无域名） | `BV1JRuA6vEvd` |

3. 项目定位：**公开可用、不对使用者负责**（README 个人使用声明 + 仓库根 `LICENSE`（MIT））；批量基线：**单次 ≤10 条**（`MAX_URLS_PER_BATCH`，roadmap P2）；遵守平台条款，控制并发与频率。

### 3.3 参考资料
- yt-dlp API：`progress_hooks`、`postprocessor_hooks`、`cookiefile`
- FastAPI：WebSocket、BackgroundTasks、Pydantic 模型
- 现有代码：`installVideo.py`（yt-dlp 配置可直接平移）

### 3.4 既定默认（如无异议按此执行）
- 输出目录**可配置**（`GET/PUT /api/settings` 持久化）：默认开发模式 `output/`、打包模式平台用户目录，修改后新任务生效；默认 MP3 192kbps（先不做视频下载，保留扩展位）；
- 本地单机运行：后端 `127.0.0.1:8000`，前端 dev `5173`，生产模式由后端托管前端静态文件；
- Cookie 由后端 `CookieService` 统一管理（文件存储 + 校验 + 自动转换 Netscape，`convert_cookie.py` 逻辑内聚为 CookieStore 实现）；
- 任务默认**串行**执行；
- 打包形态：**pywebview 独立窗口**（系统 WebView），v1 不签名不公证，zip/dmg 直解压运行；macOS / Windows 分别出包，**不设浏览器降级**；
- `.gitignore` 补充前端 `node_modules/`、构建产物。

---

## 四、待确定的实现方式（决策点）

| # | 决策点 | 结论（已确认 ✅） |
|---|--------|------|
| 1 | 后端框架 | ✅ **FastAPI（Python）** —— 复用现有 yt-dlp 逻辑 |
| 2 | 前端工程 | ✅ **Vue 3 + Vite** —— 纯白主题单页；无 3D（three.js 已移除） |
| 3 | 可视化形态 | ✅ **纯白主题 + 条形码动态进度条**（3D 需求已按用户要求移除） |
| 4 | 首版 URL 范围 | ✅ **BV 单视频 + 裸 BV 号 + b23.tv 短链 + 多P(?p=)** —— 用户示例三条链接恰好覆盖三种输入形态（带尾斜杠/无尾斜杠/无域名），共用一个 BilibiliParser |
| 5 | 任务并发 | **串行**（反爬友好） |
| 6 | Cookie 获取与校验 | ✅ **无感获取为主路径**：`POST /api/cookie/acquire` 弹出浏览器窗口，登录后自动捕获+校验+保存（Playwright，持久化登录态，二次免登录）；书签小工具 / 手动粘贴作为兜底；`GET /api/cookie/status` 轮询结果、`GET /api/cookie/guide` 引导 |
| 7 | 输出规格 | **仅音频 MP3，默认 192k**（UI 预留码率选项） |
| 8 | 部署 | **本地单机**（v1） |
| 9 | 旧 CLI 兼容 | **抽公共核心，CLI 与 Web 共用下载服务** |
| 10 | 桌面打包方案 | ✅ **D. pywebview 独立窗口**（系统 WebView 内嵌前端 + 同进程 FastAPI；macOS 用自带 WKWebView、Windows 依赖 WebView2）；**不设浏览器降级**，启动失败即报错退出；**双平台均由远端矩阵 workflow 构建**（推送 v* 标签即自动发布） |
| 12 | 发布自动化 | ✅ 推送 `v*` 标签 → 双平台并行远端构建 → 自动创建/更新 Release + 上传 zip（`release.yml`，permissions: contents:write） |
| 13 | 许可与定位 | ✅ **MIT License + 公开可用不对使用者负责**（README / 应用内"关于" / Release notes 三处免责提示） |
| 11 | 下载目录 | ✅ **可配置**：`SettingsService` + `GET/PUT /api/settings`；pywebview 用原生目录选择器、浏览器模式手动输入；持久化到 settings.json，新任务生效 |

---

## 五、桌面打包（macOS / Windows）设计

### 5.1 结论：核心架构满足，另有 6 项打包工程缺口

**已满足（架构红利，无需改动）**
- ✅ 生产模式下后端托管前端构建产物 → 打成一个可执行程序即可，无需独立静态服务器；
- ✅ 本地单机服务、无外部数据库/消息队列 → 单进程可打包；
- ✅ 模块化/接口化 → 打包所需的"运行环境定位"同样能做成接口，不破坏扩展性设计。

**缺口（打包专属，当前设计未覆盖，需在实现期补齐）**

| # | 缺口 | 影响 | 对应设计 |
|---|------|------|----------|
| 1 | FFmpeg 二进制分发 | 目标机不一定有 ffmpeg；打包版须捆绑静态二进制并动态定位 | `FFmpegLocator` 接口：系统 PATH → 捆绑目录 → 明确报错（未来可扩展自动下载） |
| 2 | 用户数据目录 | cookie/output 不能放安装目录（Windows 权限问题、升级被清空） | 双模式：开发用项目内 `./data`；打包后 macOS `~/Library/Application Support/BiliDownloader`、Windows `%APPDATA%\BiliDownloader` |
| 3 | 启动入口 | 双击图标需拉起服务与界面 | `app/launcher.py`：启动 uvicorn 后拉起 **pywebview 窗口**（内嵌前端页面）；启动失败则报错退出并提示，**不做浏览器降级** |
| 4 | 动态端口 + 本机鉴权 | 固定 8000 易冲突；本机服务需防其他本地程序调用 | 端口 0 动态分配 + 随机 token，启动时注入前端 |
| 5 | 双平台构建 | PyInstaller 不支持交叉编译（Windows 包必须在 Windows 上构建） | GitHub Actions：macOS / windows-latest 双 runner 出产物 |
| 6 | yt-dlp 时效 | B 站反爬频繁，yt-dlp 需随版本更新 | 打包版内置版本查询接口，前端提示"下载新版"而非静默失败 |

### 5.2 候选打包方案

| 方案 | 形态 | 新增依赖 | 体积 | 改动量 | 说明 |
|------|------|----------|------|--------|------|
| **D. pywebview 独立窗口（已确认采用）** | 双击启动 → 系统 WebView 内嵌前端，同进程 FastAPI 服务 | pywebview | ~60-80MB | 中 | 独立窗口体验；macOS 用自带 WKWebView；Windows 需 WebView2（Win11 自带）；Cookie 书签仍需回系统浏览器；**无浏览器降级** |
| B. Electron | 独立窗口 | electron（Node+Python 双运行时） | 150MB+ | 大 | 未采纳（参考对比）：体验上限，但体积与复杂度最高，与 Python 后端割裂 |
| C. Tauri + Python sidecar | 独立窗口 | Rust 工具链 + sidecar 管理 | ~30MB | 大 | 未采纳（参考对比）：体积最小，但引入 Rust，维护成本高 |

### 5.3 双平台独立产物与分发注意

每个平台**各自独立构建**（PyInstaller 不支持交叉编译），分别捆绑对应平台/架构的 ffmpeg 静态二进制：

| 平台 | 构建位置 | 架构 | 捆绑内容 | 产物 |
|------|----------|------|----------|------|
| macOS | 远端 macos-15 runner（GitHub Actions） | arm64 | arm64 ffmpeg + yt-dlp + pywebview（系统 WKWebView）+ Chromium（v0.1.1 起） | `BiliDownloader-macOS-arm64.zip`（内含 .app） |
| Windows | GitHub Actions `windows-latest` 构建 | x64 | x64 ffmpeg + yt-dlp + pywebview（WebView2，Win11 / 新版 Win10 自带，老系统需预装） | `BiliDownloader-Windows-x64.zip`（内含 .exe） |

**分发注意**
- macOS Gatekeeper：未签名应用需"右键 → 打开"；正式分发需 Developer ID + 公证（notarization），**v1 不做**，zip 直解压运行；
- yt-dlp 以 pip 依赖随 PyInstaller 打包，版本号随构建产物固化，升级 = 重新发版；
- **发布全自动化**：推送 `v*` 标签 → `.github/workflows/release.yml` 矩阵构建（macOS arm64 + Windows x64）→ publish 自动创建/更新 GitHub Release 并上传双平台 zip。

### 5.4 对既有设计的影响

- §四 决策表第 10 行（打包方案，已确认 pywebview 独立窗口、无浏览器降级、双平台分别出包）；
- 里程碑增加 **M6 打包分发**；
- §3.4 输出目录默认值：开发模式 `output/`、打包模式平台用户目录（§5.1 #2），均**可被用户经 `PUT /api/settings` 覆盖**。

---

## 六、里程碑建议

- **M1 准备**：装 ffmpeg、建 venv、安装依赖（半日） ✅ 已完成（v0.1.0）
- **M2 后端核心**：UrlParser 接口 + Registry + BilibiliParser 实现 + TaskManager + REST + **Cookie 模块（校验/保存/转换接口）** + **SettingsService（下载目录配置接口）**（无前端，可 curl 验收） ✅ 已完成 (v0.1.0)
- **M3 进度流**：WebSocket 事件推送 + 转码钩子接入 ✅ 已完成（v0.1.0）
- **M4 前端**：Vue3+Vite 工程（纯白主题）+ 条形码进度条 + 任务面板 + 对接 API ✅ 已完成（v0.1.0）
- **M5 打磨**：Cookie 无感获取（Playwright）、设置面板（下载目录）、批量输入、错误提示、取消任务、成品下载、README 更新 ✅ 已完成（v0.1.0）
- **M6 打包分发**：FFmpeg 捆绑 + 数据目录迁移 + **pywebview 启动入口（无浏览器降级）** + PyInstaller 双平台**远端矩阵构建** + tag 自动发布 ✅ 已完成（v0.1.0）
- **v0.1.1**：LICENSE(MIT)+免责、批量≤10、tasks.json 历史持久化（500 裁剪/中断标记/重试）、Chromium 捆绑发布包恢复打包版无感获取 —— 详见 `docs/roadmap.md`

> 风险提示：B站风控（412/封禁风险）——串行下载、控制频率、Cookie 失效即提示重取。