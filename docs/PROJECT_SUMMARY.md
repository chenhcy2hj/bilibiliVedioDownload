# 项目速览 PROJECT_SUMMARY（新会话入口文档）

> **新开窗口/新上下文时，先读本文件**（约 5 分钟读完）即可获得项目全貌。
> 需要细节时按 §6 文档地图定向读取对应文档，不必重复通读。
> 本文件由 docs/ 各文档浓缩而成；任何功能/计划变更后应重新生成或增量更新（模板见 §9）。

---

## 1. 项目定位（一句话）

**B站音频下载器**：FastAPI 后端 + Vue3 纯白 Web UI + pywebview 桌面打包，支持标准链接/裸BV号/b23.tv短链/多P 分集，串行下载转 MP3（192k 默认），双平台（macOS arm64 / Windows x64）由 **GitHub Actions 远端构建并自动发布**。**公开可用、不对使用者负责**（MIT License，三处免责：README/应用内"关于"/Release notes）。

## 2. 技术栈与目录结构

```
bilibiliVedioDownload/
├─ backend/app/          # FastAPI（Python 3.12 venv）
│  ├─ main.py            # 组装单例/路由/CORS/token 鉴权/静态托管/启动数据目录初始化
│  ├─ launcher.py        # 打包版入口：uvicorn port=0 动态端口 + 随机 token + pywebview 窗口
│  ├─ pywebview_api.py   # js_api：choose_dir 原生目录选择
│  ├─ api/               # tasks/cookie/settings_route/capabilities/ws/errors
│  ├─ core/url/          # UrlParser 抽象 + Registry + BilibiliParser（3 形态 + ?p）
│  ├─ core/downloader/   # Downloader 抽象 + YtDlpDownloader + FFmpegLocator
│  ├─ core/cookie/       # CookieValidator + Bilibili 实现 + Store(Netscape) + Service + Browser(Playwright)
│  ├─ core/settings/     # SettingsService（输出目录可配置）
│  ├─ core/task/         # TaskManager（状态机+串行队列+WS 事件）
│  └─ core/dirs.py       # 数据目录初始化/旧数据迁移
├─ backend/tests/        # pytest（当前 83 个）+ conftest（测试数据目录隔离）
├─ frontend/             # Vue3 + Vite（纯白主题，无 3D；three.js 已移除）
│  └─ src/{api, scenes(已删), components, store.js}
├─ packaging/bilidownloader.spec   # PyInstaller（onedir + .app BUNDLE + ffmpeg/chromium 捆绑）
├─ .github/workflows/release.yml   # tag v* → 矩阵构建(macos-15 arm64/windows-latest x64) → 自动 Release
├─ docs/                 # 六份文档（见 §6）
└─ data/                 # 运行数据（gitignore）：cookie/settings/tasks.json/browser_profile/downloads
```

## 3. 核心架构与关键决策（按重要性）

1. **URL 解析接口化（扩展性核心）**：`UrlParser.match()/parse()` + `Registry.dispatch()`；新平台 = 新增实现类 + `register()`，不改业务代码。BilibiliParser 支持：标准链接（尾斜杠可选）/裸 BV 号/短链（重定向解析）/?p 分P。
2. **下载链路**：先 `extract_info(download=False)` 预探测标题（回传 Task.title 作前端"名称"）→ `unique_path` 重名加 `(1)` 后缀 → 下载。**进度统一**：`calc_progress()` 字节比例优先、分片下载（total 缺失）用 `fragment_index/count` 兜底 — 修复过"进度不动"的坑。取消：hook 抛 `DownloadCancelled`。
3. **任务管理**：状态机 `pending→parsing→downloading→converting→done|failed|canceled`；串行队列；WS 事件 `{type, payload}`（created/progress/phase/done/failed/canceled/snapshot），**进度节流 200ms**（快速任务也能看到进度）。错误分类：auth/network/convert/not_found/path。
4. **Cookie**：开发模式**无感获取**（Playwright 弹窗→登录→自动捕获，持久化 profile 复用登录态）；校验走 `x/web-interface/nav`（code==0）；自动转 Netscape；下载前时效检查（失效→任务 failed(auth)+前端联动提示）。**v0.1.1 起打包版捆绑 Chromium 恢复无感**（roadmap P5）。兜底：书签脚本（仅固定端口开发模式）/手动粘贴。
5. **设置**：输出目录可配置（绝对路径校验/自动创建/写探针，`data/settings.json` 持久化）；任务级格式选项（mp3/128-320k）。
6. **打包版安全**：动态端口（port 0）+ 随机 token（HTTP `X-Auth-Token`、WS `?token=`，**仅保护 /api/\***，静态入口放行以免页面 401）；启动失败系统弹窗退出，**无浏览器降级**；数据目录平台隔离（macOS `~/Library/Application Support/BiliDownloader`、Windows `%APPDATA%\BiliDownloader`）。
7. **发布全自动**：推 `v*` 标签 → `release.yml` 矩阵并行构建 → publish job（**`permissions: contents: write` 必须**，`overwrite_files` 支持重发）自动建/更新 Release 并上传双平台 zip；`workflow_dispatch` 只产 artifact 不发布。
8. **前端**：单文件 `store.js`（reactive，无 pinia）；任务分组必须用 `computed`（曾踩"计数更新但列表为空"的响应式坑）；纯白主题 + 条形码动态进度条（下载蓝滚动/转码琥珀/100% 绿）。

## 4. 现状与计划

**v0.1.0 已交付**（Release 双平台资产在线）：全部功能 + 打包 + 自动发布。
**v0.1.1 进行中**：P1 许可免责 ✅ 已完成；**P2 批量≤10 / P3 tasks.json 历史持久化（500 裁剪+中断标记）/ P4 重试按钮 / P5 Chromium 捆绑 / P6 发布回归** —— 技术方案已定稿（`design-v0.1.1.md`），待实施。
**已知限制**：打包版无感 Cookie 待 P5；Windows 未真机验收；mac 包未签名（右键打开）；WebView2 依赖老 Windows；任务历史内存态待 P3；412 冷却明确不做（低频基线）。

## 5. 常用命令速查

```bash
# 启动（开发）
cd backend && ../venv/bin/uvicorn app.main:app --reload --port 8000   # 后端（托管 frontend/dist）
cd frontend && npm run dev                                            # 前端 5173（代理 /api→8000）

# 测试与规范
cd backend && ../venv/bin/python -m pytest tests/   # 全部用例
cd backend && ../venv/bin/ruff check app tests      # lint

# 前端构建（改前端后必须 build，或直接 dev 模式）
cd frontend && npm run build                        # 产物 frontend/dist（后端同端口托管）

# 发布（唯一官方路径：远端构建+自动发布）
git tag -a vX.Y.Z -m "release" && git push origin vX.Y.Z

# 本机 PyInstaller（仅开发验证，禁止作为发布渠道）
./venv/bin/pyinstaller packaging/bilidownloader.spec --noconfirm
```

## 6. 文档地图（按读取优先级）

| 文档 | 用途 | 何时读 |
|------|------|--------|
| **PROJECT_SUMMARY（本文件）** | 新会话入口速览 | 每次新对话先读 |
| `design-analysis.md` | 设计决策大全（API 表/架构图/决策表/里程碑） | 需要设计细节或改动设计时 |
| `roadmap.md` | v0.1.1 清单+验收 / v0.1.2+ 候选 / 明确不做 | 规划后续版本时 |
| `design-v0.1.1.md` | P2–P6 实现级技术方案（数据结构/接口/流程/涉及文件） | **实施 v0.1.1 前必读** |
| `development-guide.md` | 编码规范/分阶段任务与验收标准 | 编码、提交规范 |
| `project-status.md` | 已完成/未完成/可扩展状态流转 | 查状态与限制 |
| `manual-test-plan.md` | 手动验收用例（SF/U/S/C/D/W/V/E/P） | 交付验收 |

## 7. 环境与陷阱速查（本机）

- **Python 3.12**（`/opt/homebrew` 版建 venv）；不要用系统 3.9；
- **npm**：本机 `~/.npm` 有 root 权限遗留 → `npm install` 需 `--cache ./frontend/.npm-cache`（或用户已修复权限）；
- **pip**：PyPI 直连有 SSL 中断 → 常用 `-i https://pypi.tuna.tsinghua.edu.cn/simple`；
- **沙箱**：brew 安装、PyInstaller（写 `~/Library/Application Support/pyinstaller`）、playwright 下载、用户目录写入均需 `danger-full-access` 提权；
- **测试隔离**：`tests/conftest.py` 设 `BILIDL_DATA_DIR` 临时目录，隔离真实用户数据（cookie/设置）——新增测试依赖全局状态时会踩此坑；
- **静态托管**：`frontend/dist` 存在时 `/` 返回页面、无则 JSON；API 路由注册在 mount 之前；
- **VS 代码可忽略告警**：GitHub Actions Node20 deprecation 无害。

## 8. 文档变更纪律

- 实施偏差：先更新 `design-analysis.md` / `design-v0.1.1.md` 再改代码；
- 版本流转：`project-status.md` + `roadmap.md` 勾选；
- 功能/计划变化后：按 §9 模板**重新生成或增量更新本速览**。

## 9. 生成/更新「新会话总结文档」的提示词模板

> 用法：把下面模板发给 AI（可原样使用或按需裁剪）；生成后入库 `docs/PROJECT_SUMMARY.md` 并提交。

```
请把当前项目 docs/ 目录下的所有文档浓缩总结，生成单份速览文档写入
docs/PROJECT_SUMMARY.md（若已存在则增量更新），要求：

1. 面向"零上下文新会话"读者：只读这一份就能了解——项目定位、
   技术栈与目录结构、核心架构与关键决策、数据文件布局、现状与后续计划、
   常用命令、环境与陷阱、文档地图；
2. 只保留事实（文件名、命令、端口、常量、决策、约定），删除过程性
   叙述（历史讨论轮次、实施过程、踩坑细节仅保留结论）；
3. 控制在一次读完的长度（约 200 行内），用表格和短列表压缩信息；
4. 文档地图一节标注每份 source 文档的职责与读取时机，并注明本速览
   为第一优先级入口；
5. 结尾保留 §9 说明：本文件由该模板生成，变更后需重新生成；
6. 完成后提交推送，并核对：新文档中的命令/路径/常量与源码一致
   （抽查 backend/app/config.py、commands 与 workflow 文件）。
```

---

> 本文件为入口速览；权威细节以 §6 文档地图对应文档为准。