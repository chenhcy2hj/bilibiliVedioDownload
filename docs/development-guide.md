# 阶段性开发指导文档（v0.1）

> 用于指导本项目（B站音频下载器：FastAPI + Vue3/three.js + pywebview 桌面打包）各阶段开发任务与规范。
> 设计依据：[design-analysis.md](./design-analysis.md)。开发过程中如设计与实现冲突，先更新设计文档再改代码。

---

## 0. 总则与通用规范

### 0.1 阶段总览

| 阶段 | 名称 | 目标 | 依赖 |
|------|------|------|------|
| M1 | 环境准备 | 工具链就绪 + 项目骨架可运行 | 无 |
| M2 | 后端核心 | 接口化后端 + 全部 REST API，可 curl 验收 | M1 |
| M3 | 进度流 | WebSocket 事件推送 + 取消任务 | M2 |
| M4 | 前端 | Vue3 + three.js 页面全流程打通 | M2/M3 |
| M5 | 打磨 | Cookie 引导、设置面板、错误处理、README | M4 |
| M6 | 打包分发 | macOS/Windows 独立产物 | M5 |

### 0.2 全局编码规范

**Python（后端）**
- 遵循 PEP 8；Python 3.12；一律类型注解（type hints）；
- 目录规范（backend/app/）：

  ```
  app/
    main.py            # FastAPI 入口（注册路由/静态托管/CORS）
    config.py          # 静态配置（端口、设备模式、数据目录解析）
    schemas/           # Pydantic 模型（请求/响应/事件）
    api/               # 路由层：tasks / cookie / settings / capabilities / ws
    core/
      url/             # UrlParser 抽象 + Registry + BilibiliParser
      downloader/      # Downloader 抽象 + YtDlpDownloader
      cookie/          # CookieValidator 抽象 + Bilibili 实现 + CookieStore + CookieService
      settings/        # SettingsService（下载目录等可配置项）
      task/            # TaskManager、任务状态机、进度事件
  tests/               # pytest 单元测试，与模块一一对应
  ```

- 抽象一律用 `abc.ABC`；新增能力 = 新增实现类，**禁止修改已有分发/调度逻辑**（开闭原则）；
- 路径一律 `pathlib.Path`，禁止字符串拼接路径；
- 外部请求（B站 API、短链重定向）统一封装在对应模块，禁止散落在路由层；
- 日志统一 `logging`，格式 `时间 级别 模块 消息`；**Cookie 值、token 禁止写入日志**；
- 统一错误结构：API 错误响应 `{"code": <业务码>, "message": <原因>, "data": null}`；
- 提交前跑通 `pytest` 与 `ruff`（或等价 lint）。

**任务历史持久化规范（v0.1.1 P3，跨版本常态）**
- 状态变更**必须**走 `TaskManager._set_status()` 统一入口（status 实际变化才触发写盘；进度事件走 `_set()` 不写盘）；
- 写盘 = 全量快照 → `HistoryStore.save()`：tmp 文件 + `os.replace` 原子写、`threading.Lock` 并发保护、按 `created_at` 裁剪 `MAX_HISTORY=500`；
- `tasks.json` 只存终态字段（id/input_url/source/kind/entry_count/title/status/error_*/file_path/created_at/finished_at），瞬时量（进度/速度）禁止落盘；
- 新增任务字段/状态时：同步 `persist.TaskRecord` 与 `HistoryStore._valid` 校验；恢复任务需可经 `to_response` 直出（避免依赖运行期 request）。

**发布包捆绑规范（v0.1.1 P5，跨版本常态）**
- 捆绑目标目录约定（`Packaging/bilidownloader.spec` datas 目标）：`_browsers/`（Playwright Chromium，只捆有头版 `chromium-<数字>*`）、`ffmpeg/`、`frontend/dist`；
- 运行时定位：res === 打包模式 → 由 `launcher.py` 在 import app.main 之前通过环境变量/常量注入（如 `PLAYWRIGHT_BROWSERS_PATH=_MEIPASS/_browsers`）；开发模式走系统级缓存/路径；
- 新增捆绑资源四件套：workflow 安装步骤 + spec datas + 运行时注入 + 缺失时的明确兜底错误（`BrowserUnavailable` 类，禁止静默崩溃）。

**前端（Vue3 + three.js）**
- Composition API（`<script setup>`）；
- 目录规范（frontend/src/）：

  ```
  src/
    main.js / App.vue
    api/            # REST 与 WS 封装（唯一网络入口）
    scenes/         # three.js 场景（SceneBuilder、TaskRingNode…）
    components/     # 2D 叠层组件（UrlForm、TaskPanel、SettingsPanel、CookieGuide…）
    store.js        # 轻量 reactive 状态（任务列表/视图设置）
  ```

- three.js 仅收敛在 scenes/ 模块内，组件通过 ref 访问场景实例；**组件卸载时必须 dispose 几何体/材质/轨道控制器并移除监听**；
- 场景自适应：监听 resize、devicePixelRatio 处理；
- 不允许在组件内散落 `fetch`/`WebSocket`，统一走 api/ 封装。
- 一阶段一提交，禁止大杂烩提交。

**API 与数据契约**
- 字段一律 **snake_case**（前后端一致，不做驼峰转换）；
- WS 事件统一 `{type: "task.created" | "task.progress" | "task.phase" | "task.done" | "task.failed" | "task.canceled", payload: {...}}`；
- 版本前缀 `/api/v1`（v1 阶段即 `/api`，后续升级加前缀即可）。

**Git 提交规范**
- 格式：`<type>(<scope>): <中文描述>`，type ∈ feat/fix/docs/refactor/chore/test；
- 示例：`feat(url): 新增 b23.tv 短链解析`、`fix(cookie): 修复 nav 接口超时未处理`；
- 禁止提交：Cookie 文件、`venv/`、`node_modules/`、`dist/`、`data/`、`output/`（.gitignore 兜底）。

---

## M1 环境准备

### 任务清单
1. 安装 FFmpeg：`brew install ffmpeg`，验证 `ffmpeg -version`；
2. 创建后端虚拟环境：`python3.12 -m venv venv`，安装 `fastapi uvicorn[standard] yt-dlp pytest ruff`，导出 `requirements.txt`；
3. 创建前端工程：`npm create vite@latest frontend`（Vue 模板）+ `npm i three`，锁定 `package-lock.json`；
4. 建立目录骨架：`backend/app/...`、`backend/tests/`、`frontend/`（见 §0.2）；根目录 `README.md` 补充开发模式启动说明；
5. 更新 `.gitignore`：`venv/`、`node_modules/`、`dist/`、`data/`、浏览器 Cookie 文件、`output/`；
6. 验证最小链路：后端起一个 hello 路由（`uvicorn app.main:app`），前端 `vite dev` 可打开。

### 注意事项
- **不要用系统 Python 3.9** 建 venv，必须 3.12（brew 的 python3.12 也可）；
- ffmpeg 装完必须 `-version` 验证，二进制不存在属于阻塞项；
- Cookie 文件（`bilibiliCookie.txt` / `*_netscape.txt`）**任何情况下不得提交 git**；
- 端口约定：开发 后端 `8000`、前端 `5173`（打包版动态端口，见 M6）。

### 验收标准
- `ffmpeg -version`、`python3.12 --version`、`node --version` 均正常；
- `uvicorn app.main:app` 启动成功；`vite dev` 页面可访问；
- `git status` 干净，依赖清单已锁定。

---

## M2 后端核心

### 任务清单
1. **URL 解析接口**（核心扩展点）：
   - `UrlParser`（抽象）：`match(url)` / `parse(url) -> ParsedRequest`；
   - `UrlParserRegistry`：`register()` / `dispatch()`，未匹配抛 `UnsupportedUrlError`；
   - `BilibiliParser`：识别 3 种输入形态——标准链接（带/不带尾斜杠）、裸 BV 号、b23.tv 短链（先解析重定向取真实地址）；提取 `?p=N` 多P 参数写入 `entries`（kind=multi）。
2. **下载器**：`Downloader`（抽象：`download(request, task_id, on_progress)`）+ `YtDlpDownloader`：平移现有 `installVideo.py` 配置（`bestaudio/best`、`FFmpegExtractAudio` 192k、`cookiefile` Netscape、UA/Referer 请求头）；
3. **任务管理**：`Task` 状态机 `pending → parsing → downloading → converting → done | failed`；`TaskManager` 串行队列；入队时从 `SettingsService` 快照 `output_dir`（yt-dlp `outtmpl`）；
4. **Cookie 模块**：`CookieValidator`（抽象）+ `BilibiliCookieValidator`（带 Cookie 请求 `https://api.bilibili.com/x/web-interface/nav`，`code==0` 有效、`-101` 失效）+ `CookieStore`（存原始 + 转 Netscape）+ `CookieService`（状态查询/提交校验保存）；
5. **设置模块**：`SettingsService.get_settings() / set_output_dir()`；校验：绝对路径 → 不存在则 `mkdir -p` → 失败返回明确原因；持久化 `data/settings.json`；
6. **REST**：`POST/GET/DELETE /api/tasks`、`GET /api/tasks/{id}/file`、`GET /api/capabilities`、`GET/POST /api/cookie`、`GET /api/cookie/status`、`GET/PUT /api/settings`；
7. **单测**：parser 三形态 + 非法 URL；registry 未匹配抛错；settings 校验规则（相对路径拒绝/自动创建/不可写报错）；cookie 校验 mock。

### 注意事项
- 开闭原则：后续新平台 = 新增 parser 类 + `register()`，**禁止改 registry/dispatch 业务逻辑**；
- b23.tv 短链解析注意：跟随重定向拿最终 URL，请求带 UA，失败时返回明确错误而非静默；
- yt-dlp 调用**必须**携带 cookiefile，无 Cookie 时提示"先获取 Cookie"而不是直接报 yt-dlp 原始错误；
- Cookie 校验请求注意 Referer/UA 头与超时（网络异常视为"无法判断"，不要误报"已失效"）；
- 文件名来自 yt-dlp 标题（`%(title)s`），含中文字符/特殊符号，`outtmpl` 无需 sanitize（yt-dlp 自带），但**不要**在代码里二次转义；
- 任务失败时记录原因分类：`network / auth(412) / convert / path`。

### 验收标准
- `curl -X POST /api/tasks -d '{"urls":["BV1JRuA6vEvd"]}'` 创建任务成功（如无 Cookie，返回业务码提示而非 500）；
- `curl /api/capabilities` 返回 `["bilibili:standard", "bilibili:bare-bvid", "bilibili:short-link"]` 一类能力清单；
- `curl -X PUT /api/settings -d '{"output_dir":"/tmp/bili_out"}'` 成功创建目录并持久化；非法路径返回统一错误结构；
- `pytest` 全绿。

---

## M3 进度流

### 任务清单
1. WebSocket 端点 `/api/ws`：连接后推当前全量任务快照，之后推增量事件；
2. yt-dlp `progress_hooks`（downloaded/total/speed/eta）与 `postprocessor_hooks`（converting 阶段）接入 TaskManager；
3. 进度事件节流：同一任务进度推送间隔不小于 500ms（避免 WS 风暴）；
4. 支持取消：`DELETE /api/tasks/{id}` → 中止 yt-dlp 子进程 → 事件 `task.canceled`；
5. 事件数据结构：`{type, payload:{task_id, status, phase, downloaded, total, speed, eta, error_code, message}}`。

### 注意事项
- 事件队列线程安全：进度回调线程 → 线程安全队列 → WS 消费者，**禁止在回调里直接写 WebSocket**；
- 412/风控错误映射到 `auth` 类别，前端据此弹出"Cookie 失效，请重新获取"；
- 断线语义：客户端重连后靠"全量快照"补齐状态，不做历史事件补发；
- `speed/eta` 单位统一（B/s、秒），前端负责格式化；缺省值用 null 而非 0（避免误显示"0B/s"）。

### 验收标准
- 创建一个任务，用 WS 客户端（wscat 等）能收到 `parsing → downloading → converting → done` 全阶段事件；
- 下载中途 `DELETE` 任务，收到 `task.canceled` 且子进程终止（无残留 ffmpeg 进程）；
- 断线重连后能收到全量快照。

---

## M4 前端

### 任务清单
1. Vue3 工程按 §0.2 目录搭建，`api/` 层封装 REST + WS（含重连与全量快照处理）；
2. 任务面板：**纯白主题** + **条形码动态进度条**（下载中条纹滚动动画、转码琥珀色、完成绿色静态条码；进度优先使用后端 `progress` 字段，节流 200ms）；
3. 2D 叠层组件：URL 批量输入（多行）、解析预览（标题/条目数/来源，create 前可预览）、格式选择（MP3 192k）、任务列表/状态徽标、设置面板（显示/修改下载目录）、Cookie 状态条（有效→用户名 / 失效→"重新获取"入口）；
4. REST + WS 全流程联调：输入 URL → 3D 节点出现 → 进度弧增长 → 完成（绿色）→ 点击节点可下载成品；
5. 生产模式联调：后端托管 `frontend/dist` 静态文件，验证同一端口访问；
6. 开发模式：Vite proxy 指向 `127.0.0.1:8000`（避免本地开发 CORS 问题）。

### 注意事项
- WS 收到未知/畸形消息：忽略并告警日志，不崩溃页面；
- 磁盘错误（output_dir 不可写）来自后端统一错误结构，前端展示 message 并在设置面板高亮；
- **不做浏览器降级体验**：打包版仅 pywebview 窗口；开发模式用浏览器正常开发即可；
- 三个示例 URL 作为冒烟用例：带尾斜杠 / 无尾斜杠 / 裸 BV（不含网络请求，立即可验证解析）。

### 验收标准
- 冒烟：三个示例 URL 均能在页面上解析并下载（有 Cookie 时），3D 节点完整走完状态流转；
- 修改下载目录成功（含路径不可写时的错误提示）；新任务进入新目录，进行中任务不受影响；
- 强制关闭后端再启动，前端 WS 自动重连并恢复快照；
- 长任务（1 小时级别）页面无内存增长异常（DevTools 观察）。

---

## M5 打磨

### 任务清单
1. **Cookie 无感获取（主路径）**：`POST /api/cookie/acquire` → Playwright 弹出持久化 Chromium 窗口（profile 存数据目录）→ 页面内 fetch nav 轮询登录态（2s） → 登录成功自动捕获 bilibili 域 Cookie → 自动保存 + Netscape 转换（300s 超时/取消返回 None，进行中并发 409）；前端轮询 `/api/cookie/status`（`acquiring`/`acquire_message` 字段）展示结果；**书签脚本（guide 接口生成，URL 编码后必须真实浏览器验证一次）与手动粘贴作为兜底**；
2. **设置面板完善**：pywebview 环境调用原生目录选择对话框（`window.pywebview` folder dialog）回填路径；浏览器环境手动输入；
3. **FFmpegLocator**：定位顺序 系统 PATH → 应用捆绑目录 →（都找不到）明确报错"FFmpeg 未找到，请重新安装应用"；
4. **数据目录迁移**：检测打包模式（`sys.frozen`）→ 数据目录切到平台用户目录（macOS `~/Library/Application Support/BiliDownloader`、Windows `%APPDATA%\BiliDownloader`），自动创建 `data/`、`output/` 默认子目录；
5. 成品下载优化：中文文件名（RFC 5987 编码）、重复文件处理、下载完成后清理中间文件；
6. 错误提示体系：任务失败原因（network/auth/convert/path）对应可读文案 + 建议动作（如"重新获取 Cookie"）；
7. `.gitignore` 复核；根目录 README 更新为最终使用说明（含个人使用声明）。

### 注意事项
- 书签脚本生成：JS 代码需 **URL 编码**后放入 `javascript:` 协议，注意引号转义——生成后必须在真实浏览器测一次再交付；
- CORS 策略：仅本地开发对 `127.0.0.1:5173`/`bilibili.com`（书签回传来源）放开；打包版同源（pywebview 加载本地页面）无需 CORS；
- Cookie 状态条与任务联动：`task.failed(auth)` 事件触发"重新获取 Cookie"提示；
- 数据目录迁移只做一次（检测到旧路径存在才迁移），避免重复搬移；
- 输出目录校验失败信息要能区分：路径不存在（可自动创建）/ 无权限 / 是文件而非目录。

### 验收标准
- 书签回传 → 后端校验 + 自动转换 Netscape → 页面显示登录用户名；粘贴兜底同样可用；
- 打包模式（或模拟 `sys.frozen`）下，输出与配置落到平台用户目录且可配置覆盖；
- 中文标题文件下载无乱码；失败任务均有可读原因与建议。

---

## M6 打包分发

### 任务清单
1. **launcher.py**（应用入口）：启动 uvicorn（**端口 0 动态分配** → 随机 token：HTTP `X-Auth-Token` + WS `?token=`，仅保护 `/api/*`）→ 拉起 pywebview 窗口（macOS WKWebView / Windows WebView2，js_api 暴露 `choose_dir`）；**启动失败系统弹窗报错退出，不做浏览器降级**；
2. **PyInstaller 双平台远端构建**（`packaging/bilidownloader.spec`）：onedir + macOS `.app` BUNDLE；bundles：前端 dist、对应平台静态 ffmpeg（npm `@ffmpeg-installer/*` 渠道）、yt-dlp；**v0.1.1 起捆绑 Playwright Chromium**（`PLAYWRIGHT_BROWSERS_PATH` 指向包内目录），打包版恢复无感获取 Cookie；
3. **构建与发布全自动化**（`.github/workflows/release.yml`）：矩阵双平台并行（macos-15 arm64 / windows-latest x64），推送 `v*` 标签触发；构建成功后 `publish` job（`permissions: contents: write`）自动创建/更新 Release 并上传双平台 zip（`overwrite_files` 支持重发）；`workflow_dispatch` 仅产 artifact 不发布；
4. 状态下发：`GET /api/health`（版本号 + yt-dlp 版本），前端"关于"显示，便于排查与提示升级；
5. 双平台产物验证：mac 本机完整验收 `.app`（动态端口、token 鉴权、静态入口放行、真实下载链路）；Windows 产物在真实 Windows 环境人工验收（CI 无法代替 GUI 验证）。

### 注意事项
- PyInstaller **不支持交叉编译**：Windows 包必须在 Windows 构建（CI）；两个平台是**独立产物**，各自捆绑对应架构 ffmpeg；
- 端口固定 8000 不允许出现在打包版：动态端口 + token 防微信/其他本地进程误调用；token 不落日志；
- 数据目录一律走平台用户目录（M5 迁移逻辑），打包版**禁止**往安装目录写 cookie/output；
- yt-dlp 随包固化：升级 = 重新构建两个平台并分别发版；版本信息展示在"关于"页；
- macOS 未签名应用首次打开需"右键 → 打开"（Gatekeeper），在交付说明中写明；
- WebView2：Win11/新版 Win10 自带；老系统需在交付说明中提示预装（v1 不自动安装）；
- CI 密钥保护：GitHub Actions 中不应出现 Cookie 等敏感内容（构建产物不含用户数据）；
- **构建发布全流程走远端**（tag 触发矩阵构建 + 自动 Release），禁止本地出包与手工上传资产（facts：本地构建仅用于开发验证，如 PyInstaller 缓存/签名留待 CI）；
- Chromium 捆绑（v0.1.1）：CI 侧 `playwright install chromium` 后经 spec datas 捆绑，运行时 `PLAYWRIGHT_BROWSERS_PATH` 指向包内目录；打包版无感获取恢复后，`guide` 接口不再做"打包版降级"分支。

### 验收标准
- mac 包：双击 .app → 窗口出现 → 全流程（cookie 引导 → 下载 → 转码 → 成品）通过；
- Windows 包：真实 Windows 机器或虚拟机同样全流程通过（至少冒烟：解析 + 下载 + 转码）；
- 双平台产物各自独立、互不依赖，`GET /api/health` 正常；
- 端口冲突、ffmpeg 缺失等异常场景给出可读错误而非崩溃静默。

---

## 风险与全局注意事项（贯穿所有阶段）

| 风险 | 说明 | 应对 |
|------|------|------|
| B站风控（412/封禁） | 频繁/并发请求触发；Cookie 失效即 412 | 任务**串行**、控制频率、auth 错误单独识别并提示重取 Cookie |
| Cookie 时效 | 有效期不定，失效无感知 | 下载前 `CookieService.status()` 检查；前端状态条常驻显示 |
| yt-dlp 时效 | B 站接口变动导致解析失败 | 版本固化但可升级；`GET /api/health` 展示版本，升级 = 重新发版 |
| 版权/合规 | 内容受版权保护 | README 个人使用声明；仅个人学习；不传播不商用 |
| 路径/权限 | 输出目录不可写、磁盘满 | SettingsService 校验先行；错误分类 path 并给出建议 |
| 本机安全 | 本地服务被其他进程调用 | 打包版动态端口 + token；开发版仅绑 127.0.0.1 |
| 历史列表膨胀 | tasks.json 持久化后历史增长 | 保留最近 500 条自动裁剪；列表渲染上限提示 |
| 交叉编译限制 | Windows 产物无法在 mac 构建 | 一律走 CI；避免在本地跑 fake 的 win 包验证 |

> 本指导文档与 design-analysis.md 同步维护：任何阶段的实现偏差，先更新两处文档再继续编码。