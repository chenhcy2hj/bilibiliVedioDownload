# 项目状态总览（v0.1.0）

> 更新日期：2026-08-28（Release v0.1.0 发布后；v0.1.1 规划见 `docs/roadmap.md`）。
> 详细设计见 `design-analysis.md`，开发规范见 `development-guide.md`，测试方案见 `manual-test-plan.md`。

---

## 一、已完成的交付

### 1.1 功能（M1–M5 全部完成）

| 模块 | 状态 | 说明 |
|------|------|------|
| URL 解析接口化 | ✅ | `UrlParser` 抽象 + Registry 注册分发；BilibiliParser 支持标准链接（带/不带尾斜杠）、裸 BV 号、b23.tv 短链、`?p=` 分P |
| 下载服务 | ✅ | yt-dlp 平移 + 标题预探测 + 文件名去重（`title (1).mp3`）+ 进度统一化（字节/分片比例兜底）+ 取消（DownloadCancelled） |
| 任务管理 | ✅ | 状态机（pending→parsing→downloading→converting→done/failed/canceled）、串行队列、task.done 产物路径 |
| WebSocket 进度 | ✅ | 快照 + 增量事件、200ms 节流、自动重连、`{type, payload}` 契约 |
| Cookie 获取 | ✅ | **开发模式无感获取**（Playwright 弹窗自动捕获、持久化登录态）+ 书签脚本 + 手动粘贴兜底；校验（nav 接口）、Netscape 自动转换、时效检查（任务前拦截） |
| 设置 | ✅ | 下载目录可配置（绝对路径校验/自动创建/写探针）、settings.json 持久化、任务级格式选项（mp3/128-320k） |
| 桌面界面 | ✅ | 纯白主题（需求变更：移除 three.js 所有 3D 样式）、任务行 = 名称（视频标题）+ 条形码动态进度条 + 百分比（100% 绿色） |
| 错误体系 | ✅ | auth/network/convert/not_found/path 分类 + 前端建议动作 + auth 失效联动提示 |
| 数据目录 | ✅ | 开发/打包双模式（平台用户目录）、旧数据一次性迁移、Cookie 与输出隔离 |

### 1.2 打包与发布（M6 + 自动化）

| 事项 | 状态 | 说明 |
|------|------|------|
| 桌面启动器 | ✅ | pywebview 窗口、动态端口（port 0）、随机 token（HTTP Header / WS query 校验、静态入口放行）、失败弹窗退出（无浏览器降级）、`choose_dir` 原生目录选择 |
| macOS 产物 | ✅ | 远端构建（macos-15 arm64 runner）：`BiliDownloader-macOS-arm64.zip`（.app，~80MB，zip 40MB） |
| Windows 产物 | ✅ | 远端构建（windows-latest x64 runner）：`BiliDownloader-Windows-x64.zip` |
| 自动发布 | ✅ | `.github/workflows/release.yml`：推送 `v*` 标签 → 双平台并行构建 → publish 自动创建/更新 Release + 上传两平台 zip（overwrite_files） |
| 静态 FFmpeg | ✅ | npm `@ffmpeg-installer/*` 渠道（内置二进制，规避 GitHub 直连下载不稳）；spec 捆绑 + 运行时定位（PATH → 捆绑目录 → 报错） |
| 版本信息 | ✅ | `/api/health` 暴露应用/yt-dlp 版本，设置面板"关于"展示 |

### 1.3 质量与文档

- 自动化测试 **83 passed**（parser 形态/registry、设置校验、Cookie 校验与获取、WS 事件流/节流、取消、进度计算、token 鉴权、M5 全部）；ruff 全绿
- 文档：`design-analysis.md`（设计）、`development-guide.md`（分阶段开发规范）、`manual-test-plan.md`（手动测试方案）、`README.md`（使用与发布说明）
- 代码与 Release 全部推送远端（main @ 4c01550；Release v0.1.0 双平台资产）

---

## 二、未完成 / 已知限制

| # | 事项 | 影响 | 处理建议 |
|---|------|------|----------|
| 1 | ~~打包版无感获取 Cookie 不可用~~ | 已规划修复：**v0.1.1 捆绑 Chromium 进发布包**（roadmap P5），打包版恢复与开发模式一致的无感捕获 | roadmap P5（v0.1.1） |
| 2 | **Windows 包未在真实 Windows 机器验收** | CI 构建成功 ≠ 功能验证（GUI/下载/WebView2） | 在 Win10/11 解压按 `manual-test-plan.md` §1/§5 冒烟 |
| 3 | **未签名/未公证** | macOS 首次需"右键 → 打开"；正式分发需 Developer ID + notarization | 如对外分发再处理（需开发者证书） |
| 4 | **WebView2 依赖**（Windows） | Win11/新版 Win10 自带；老系统需预装 | 发布说明中提示；如需静默安装再扩展 |
| 5 | **任务历史为内存态** | 后端重启后任务列表清空（成品文件仍在） | 可选：SQLite/JSON 持久化任务记录 |
| 6 | **多P 仅下载指定分P** | `?p=2` 只处理所选分P，不做"全部 P"批量 | 后续增加 playlist 能力 |
| 7 | **无 CI 测试门禁** | workflow 只构建发布，未跑 pytest/ruff | 可在 workflow 加 test job 防回归 |
| 8 | 下载并发恒定串行、无限速/代理/自定义 UA 配置 | 特网场景受限 | 设置面板扩展项 |

---

## 三、可扩展事项（按优先级建议）

> 后续计划以此处与 `docs/roadmap.md` §2 为准（roadmap 为权威版本）。

### 高优先（补齐体验）
1. **打包版无感获取 Cookie**：首次点击"获取 Cookie"时按需下载 Chromium 到数据目录（体积不随包分发）；
2. **CI 测试门禁**：release workflow 增加 `test` job（pytest + ruff + 前端 build），失败即中止发布；
3. **任务历史持久化**：重启恢复任务列表与状态（失败重试信息）；
4. **真实 Windows 验收清单**：以 testing 结果图像化记录（截图/日志），沉淀到 `manual-test-plan.md`。

### 中优先（增强功能）
5. **更多 URL 形态**：B 站合集/收藏夹/音频区（au）、b23.tv 短链真实解析联调、多P 全选批量；
6. **接入更多平台**：YouTube 等 —— 只需新增 `UrlParser` 实现 + `registry.register()`，无需改业务代码（接口化红利）；
7. **视频下载支持**：输出选项加 Video（当前仅音频 MP3 192k）；
8. **下载优化**：并发数可配置、限速、重试策略、格式选择扩展（FLAC/WAV）；
9. **文件名自定义模板**（如 `标题 - UP主`、日期前缀）。

### 低优先（锦上添花）
10. **深色/浅色主题切换**（当前固定纯白，可复用 old palette 做暗色）；
11. **系统通知/托盘**（pywebview 事件 → 系统通知：完成/失败提醒）；
12. **自动更新检查**（对比 Release 版本，提示下载新版）；
13. **i18n**（文案国际化）；
14. **移动端适配**（响应式布局，当前桌面优先）；
15. **正式签名/公证 + 安装包**（dmg/NSIS + 自动更新通道）—— 如未来公开展示所需；
16. **播放/试听集成**（成品列表内嵌播放器）。

---

## 四、发版操作速查

```bash
# 一键发布（远端自动构建 + Release）
git tag -a vX.Y.Z -m "release"
git push origin vX.Y.Z
```

Release 地址：https://github.com/chenhcy2hj/bilibiliVedioDownload/releases