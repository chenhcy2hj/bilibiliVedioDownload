# 项目速览 PROJECT_SUMMARY（新会话入口文档）

> **新开窗口/新上下文只需读本文件**：历史脉络、当前任务、工作约定、验收方式全部内置。
> 开场词（已内置，无需复制任何模板）：**「读取 docs/PROJECT_SUMMARY.md，按其中当前进度继续」**。
> 需要细节时按 §6 文档地图定向读取；本文件由 docs/ 各文档浓缩，变更后按 §11 重新生成。

---

## 1. 项目定位（一句话）

**B站音频下载器**：FastAPI 后端 + Vue3 纯白 Web UI + pywebview 桌面打包，支持标准链接/裸BV号/b23.tv短链/多P 分集，串行下载转 MP3（192k 默认），双平台（macOS arm64 / Windows x64）由 **GitHub Actions 远端构建并自动发布**。**公开可用、不对使用者负责**（MIT License；README / 应用内"关于" / Release notes 三处免责）。

## 2. 历史脉络与当前进度（新会话从这里接续）

| 阶段 | 内容 | 状态 |
|------|------|------|
| CLI 时代 | `installVideo.py` + `convert_cookie.py`：URL 硬编码、无 UI、无 Cookie 管理 | 已淘汰（保留兼容） |
| 设计 | `design-analysis.md`：接口化 UrlParser/Downloader/Cookie/Settings；决策：FastAPI、Vue3、纯白 UI、串行、pywebview 打包 | 已定稿 |
| M1–M6 实施 | 后端核心 → WS 进度 → 前端 → 打磨 → 打包；中途需求变更：3D 全部移除改纯白+条形码进度条；无感 Cookie（书签→Playwright）；进度分片兜底修复；打包改远端自动发布 | ✅ 完成（v0.1.0） |
| v0.1.0 发布 | Release 双平台资产在线；tag 推送即自动构建+发布 | ✅ 已发布 |
| **v0.1.1（已完成）** | **P1 许可免责 ✅ / P2 批量≤10 ✅ / P3 历史持久化 ✅ / P4 历史重试 ✅ / P5 Chromium 捆绑 ✅ / P6 发布+双平台真机验收 ✅**（2026-09-05 全量闭环） | ✅ 完成 |

**v0.1.1 关键事实**：Release 资产 mac 248MB / win 276MB（含 Chromium）；Windows 打包版曾因 windowed 模式 stdio=None 启动崩溃 → `launcher._ensure_stdio()` 修复并重发修复版（真机确认）；git 历史曾含 `output/` 23 个 mp3（~130MB）→ `filter-repo` 重写历史彻底清除（main/v0.1.0/v0.1.1 均 force push；无 Cookie/凭据泄露，SESSDATA 均为测试假值）。

**下一步（接续点）**：v0.1.1 已闭环。后续迭代按 `docs/roadmap.md` §2 候选推进（高优先：CI 测试门禁、任务历史清空/搜索、多P 全选批量）。开启 v0.1.2 前先读 `roadmap.md` 更新计划、`design-analysis.md` 设计方案，再实施。

## 3. 技术栈与目录结构

```
bilibiliVedioDownload/
├─ backend/app/
│  ├─ main.py            # 组装单例/路由/CORS/token 鉴权/静态托管/数据目录初始化/load_history
│  ├─ launcher.py        # 打包版入口：_ensure_stdio + uvicorn port=0 动态端口 + 随机 token + pywebview + _browsers 注入
│  ├─ pywebview_api.py   # js_api：choose_dir 原生目录选择
│  ├─ api/               # tasks/cookie/settings_route/capabilities/ws/errors
│  ├─ core/url/          # UrlParser 抽象 + Registry + BilibiliParser（3 形态 + ?p）
│  ├─ core/downloader/   # Downloader 抽象 + YtDlpDownloader + FFmpegLocator
│  ├─ core/cookie/       # Validator + Bilibili 实现 + Store(Netscape) + Service + Browser(Playwright)
│  ├─ core/settings/     # SettingsService（输出目录可配置）
│  ├─ core/task/         # TaskManager（状态机+串行队列+WS 事件）+ persist.py（历史写盘/裁剪/恢复）
│  └─ core/dirs.py       # 数据目录初始化/迁移
├─ backend/tests/        # pytest（当前 98 个）+ conftest（数据目录隔离）
├─ frontend/             # Vue3 + Vite 纯白主题（three.js 已移除）；src/{api,components,store.js}
├─ packaging/bilidownloader.spec   # PyInstaller（onedir + .app BUNDLE + ffmpeg；Chromium 由 workflow 直拷）
├─ .github/workflows/release.yml   # tag v* → 矩阵构建(macos-15 arm64/windows-latest x64) → Playwright Chromium 安装 → 直拷 _browsers → 自动 Release
├─ docs/                 # 七份文档（见 §6）
└─ data/                 # 运行数据(gitignore)：cookie/settings/tasks.json/browser_profile/downloads
```

## 4. 核心架构与关键决策（按重要性）

1. **URL 解析接口化（扩展性核心）**：`UrlParser.match()/parse()` + `Registry.dispatch()`；新平台 = 新增实现类 + `register()`，不改业务逻辑。BilibiliParser：标准链接（尾斜杠可选）/裸 BV 号/短链（重定向）/?p 分P。**BV 号正则 `BV[0-9A-Za-z]{10}`（BV 后必须 10 位，测试用 `BV1JRuA6vEvd` 12 字符）。**
2. **批量上限（P2）**：`MAX_URLS_PER_BATCH=10`；后端先 strip+去空行统计，超限 422 `BATCH_TOO_LARGE`；前端超限禁用提交+行内提示（不阻塞粘贴）。
3. **下载链路**：预探测标题（`extract_info(download=False)` 回传 Task.title）→ `unique_path` 重名加 `(1)` → 下载。进度统一 `calc_progress()`：字节比例优先、分片（total 缺失）`fragment_index/count` 兜底。取消：hook 抛 `DownloadCancelled`。
4. **任务管理 + 历史（P3）**：状态机 `pending→parsing→downloading→converting→done|failed|canceled|interrupted`；串行队列；WS 事件 `{type,payload}`（snapshot/created/progress/phase/done/failed/canceled），**进度节流 200ms**；错误分类 auth/network/convert/not_found/path。历史持久化：终态写 `data/tasks.json`（原子写 tmp+os.replace、`threading.Lock`、按 created_at 裁剪 `MAX_HISTORY=500`）；**状态机驱动写盘**（进度事件不写盘）；启动 `load_history()`：终态进历史、进行中→`interrupted`（灰徽标）；`finished_at` 透传。**P4 历史行 failed/interrupted/canceled 一键重试**（复用 POST /api/tasks，done 行"下载"链接）。
5. **Cookie**：开发模式**无感获取**（Playwright 弹窗→登录→自动捕获，持久化 profile 复用登录态）；校验 `x/web-interface/nav`（code==0）；自动转 Netscape；下载前时效检查（失效→failed(auth)+前端联动）。**P5 打包版捆绑有头 Chromium**：CI `playwright install chromium` → PyInstaller 打包后 workflow **直拷** `_browsers/`（macOS `Contents/Frameworks/_browsers`、Windows `_internal/_browsers`，保留原始签名——不进 PyInstaller datas，macOS 重签 Chrome.app 会失败）；launcher 在 import app.main 前 `setdefault PLAYWRIGHT_BROWSERS_PATH=_MEIPASS/_browsers`；guide 打包版文案为无感获取+粘贴兜底（bookmarklet=None）。兜底：书签（仅开发模式固定 8000 端口）/手动粘贴。
6. **设置**：输出目录可配置（绝对路径/自动创建/写探针，`data/settings.json`）；任务级格式 mp3/128-320k。
7. **打包版**：`launcher.py` **`_ensure_stdio()` 必在首位**（windowed 下 stdout/stderr=None，uvicorn 日志配置访问 isatty 崩溃——Windows 实测）；动态端口（port 0）+ 随机 token（HTTP `X-Auth-Token`、WS `?token=`，仅保护 /api/*，静态入口放行）；启动失败弹窗退出，无浏览器降级；数据目录平台隔离。
8. **发布全自动**：推 `v*` 标签 → 矩阵并行构建（含 Chromium，zip 实测 mac 248MB/win 276MB）→ publish job（`permissions: contents: write`、`overwrite_files`）自动建/更新 Release；`workflow_dispatch` 仅产 artifact。
9. **前端**：单文件 `store.js`（reactive）；任务分组**必须 `computed`**（踩过"计数更新列表为空"坑）；条形码进度条（下载蓝滚动/转码琥珀/100% 绿）；CookieBar 一键无感获取 + 手动方式折叠兜底。

## 5. 常用命令速查

```bash
# 启动（开发）
cd backend && ../venv/bin/uvicorn app.main:app --reload --port 8000   # 后端（托管 frontend/dist）
cd frontend && npm run dev                                            # 前端 5173（代理 /api→8000）

# 测试与规范（每次改动必跑）
cd backend && ../venv/bin/python -m pytest tests/   # 全量用例（当前 98）
cd backend && ../venv/bin/ruff check app tests      # lint
cd frontend && npm run build                        # 前端构建（改动前端后必须 build）

# 发布（唯一官方路径：远端构建+自动发布）
git tag -a vX.Y.Z -m "release" && git push origin vX.Y.Z

# 本机 PyInstaller（仅开发验证，禁止作为发布渠道；未装 chromium 缓存会失败）
./venv/bin/pyinstaller packaging/bilidownloader.spec --noconfirm
```

## 6. 文档地图（按读取优先级）

| 文档 | 用途 | 何时读 |
|------|------|--------|
| **PROJECT_SUMMARY（本文件）** | 新会话入口：历史/当前/约定/验收 | 每次新对话先读 |
| `design-analysis.md` | 设计决策大全（API 表/架构/决策表/里程碑） | 设计细节或改动设计 |
| `roadmap.md` | v0.1.1 清单（已全勾）+ v0.1.2+ 候选 / 明确不做 | 规划版本 |
| `design-v0.1.1.md` | P2–P6 实现级方案 + 实施偏差记录 | 改 v0.1.1 相关代码前 |
| `development-guide.md` | 编码规范 + P3 持久化/P5 捆绑规范 | 编码、提交规范 |
| `project-status.md` | 已完成/未完成/可扩展 + 发布期修复记录 | 查状态与限制 |
| `manual-test-plan.md` | 手动验收用例（SF/U/S/C/D/W/V/E/P/H） | 交付验收 |

## 7. 环境与陷阱（本机）

- **Python 3.12**（`/opt/homebrew` 建 venv）；不用系统 3.9；
- **npm**：`~/.npm` 有 root 权限遗留 → 必要时 `--cache ./frontend/.npm-cache`；
- **pip**：PyPI 直连 SSL 不稳 → `-i https://pypi.tuna.tsinghua.edu.cn/simple`；
- **沙箱提权（danger-full-access）**：brew 安装、PyInstaller（写 `~/Library/Application Support/pyinstaller`）、playwright 下载、用户目录写入；
- **测试隔离**：`tests/conftest.py` 设 `BILIDL_DATA_DIR` 临时目录——新增测试勿依赖全局 `data/`；
- **静态托管**：`frontend/dist` 存在时 `/` 返回页面；API 路由注册在 mount 之前；
- **GitHub Actions**：Node20 deprecation 警告无害；
- **git 历史重写**：filter-repo 装于 venv（`venv/bin/git-filter-repo`），须在 mirror clone 上运行。

## 8. 工作约定（怎么做）

1. **文档优先**：实施前先读对应设计文档；实现偏差 → 先更新设计文档再改代码；
2. **门禁**：每次改动后跑 pytest 全量 + ruff + 前端 build，全绿才提交；
3. **提交格式**：`<type>(<scope>): <中文描述>`，type ∈ feat/fix/docs/refactor/chore/test；
4. **发布纪律**：构建发布一律走远端 tag 触发；禁止本地 PyInstaller 产物上传 Release；
5. **沙箱**：系统级操作（brew/缓存/用户目录/网络下载）先试普通模式，被拒后提权并说明理由；
6. **不干扰用户环境**：不擅自杀用户进程、不抢占 8000/5173 端口（端口占用时先检查再决定）；
7. **Cookie 安全**：Cookie 值/token 不落日志不上传；用户 Cookie 位于 `data/` 或打包版用户目录；
8. **git 安全**：`output/`/`data/` 等运行产物**禁止跟踪**（曾发生 23 个 mp3 被推公开仓库，已重写历史清除）；提交前 `git status` 检查无产物文件；mp3 等大文件不入库。

## 9. 验收方式（怎么验收）

- **代码门禁**：`pytest` 全量绿（当前 98）+ `ruff check` 零错 + `npm run build` 通过；
- **功能验收**：逐项对照 `roadmap.md` §1 验收标准（v0.1.1 P1–P6 全部 ✅）；
- **手动验收**：按 `manual-test-plan.md`（冒烟 SF / URL 解析 U / 设置 S / Cookie C（含 C09 打包版内置浏览器）/ 下载 D / 历史与重试 H / WS W / 错误 E / 性能 P）；
- **发布验收**：推 tag → Actions 全绿 → `gh release view` 确认双平台资产（v0.1.1：mac 248MB / win 276MB，含 Chromium）→ 真机冒烟（mac 右键打开、win 解压运行；下载链路需真实 Cookie）。

## 10. 文档变更纪律

- 功能/计划变化 → 先更新对应设计/计划文档，再按 §11 重新生成本速览；
- 版本流转 → `project-status.md` + `roadmap.md` 勾选；
- 每份 docs 文档的职责见 §6 地图，避免信息重复维护。

## 11. 新会话开场与生成/更新本文档

> 本节的完整操作规范（强制流程/模板/维护时机）已迁移至仓库根 **`SKILL.md`**，新会话直接指它。

**新会话开场（已内置，一行即可）**：

```
读取 SKILL.md 与 docs/PROJECT_SUMMARY.md，按其中「当前进度」接续：
实施 v0.1.1 前必读 docs/design-v0.1.1.md，遵守 §8 约定，按 §9 验收。
```

**生成/更新本总结文档的提示词模板**（功能或计划实质变化后使用）：

```
请将 docs/ 下所有文档浓缩为 docs/PROJECT_SUMMARY.md（存在则增量更新），要求：
1. 面向零上下文新会话：只读本文件即可知晓 历史脉络/当前任务/工作约定/验收方式；
2. 只保留事实（路径、命令、端口、常量、决策、勾选状态），删除过程性叙述；
3. 控制在一次读完（约 200 行），表格与短列表压缩；
4. §历史与当前进度 必须标注精确接续点（下一步做什么、先读哪份文档）；
5. §工作约定/§验收方式 为可执行的检查单；
6. 抽查命令与路径与源码一致（config.py、workflow、spec）后提交推送。
```

---

> 本文件为入口速览；权威细节以 §6 文档地图对应文档为准。