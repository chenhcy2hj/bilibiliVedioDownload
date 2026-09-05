# 后续计划 · Roadmap（v0.1.1 → v0.2.0）

> 来源：基于 `design-analysis.md` 的多轮设计拷问（2026-08-28）收敛共识。
> 配套：`project-status.md`（已完成/未完成/可扩展）、`development-guide.md`（开发规范）、`manual-test-plan.md`（测试方案）。

---

## 0. 决策根（所有规划的前提，已确认 ✅）

| 维度 | 决策 |
|------|------|
| 产品定位 | **公开可用、不对使用者负责**：Release 公开；README / Release notes / 应用内"关于"区三处免责提示（"仅供个人学习，风控与合规责任由使用者承担"），不做首次运行强制弹窗 |
| 许可 | **MIT**（仓库根新增 `LICENSE`；与公开仓库意图一致） |
| 安全基线 | Cookie 明文存储 + token 鉴权（保持现状）；文档与 UI 提示"Cookie 仅存本机、勿在共享设备使用" |
| 批量基线 | 单次 ≤10 条（正常 1 条）；串行下载；**不做 412 冷却**（低频前提下，真遇到再补） |
| 打包 | macOS / Windows 全部远端构建 + 自动发布（tag 触发）；**Chromium 捆绑进发布包**（接受体积：zip ~180-200MB） |

---

## 1. v0.1.1 计划（已收口清单）

> 目标：本版本只做以下 5 项，其余一律不掺入。

### P1 · 开源许可与免责声明 ✅
- [x] 仓库根新增 `LICENSE`（MIT，作者 chenhcy2hj）
- [x] README 个人使用声明升级："使用者自行承担风控与合规责任"措辞 + **MIT 许可段落**
- [x] `docs/design-analysis.md` §3.2 / 决策表同步定位
- [x] Release notes 模板（`release.yml` body）加入免责行
- [x] 前端设置面板"关于"区加一行："仅供个人学习，风控与合规责任由使用者承担"

**验收**：✅ 仓库含 LICENSE；三处免责提示可见；`gh release view` 模板含免责（commit 6fc80ed）。

### P2 · 批量上限（≤10） ✅
- [x] 后端：`MAX_URLS_PER_BATCH = 10` 常量；`POST /api/tasks` 超出返回 `422 + BATCH_TOO_LARGE` 业务码
- [x] 前端 UrlForm：行内提示"最多 10 条"；超出后禁用提交并提示
- [x] 测试：后端超限 422；前端逻辑随构建验证

**验收**：✅ 粘贴 11 条 → 前端提示且后端拒绝；≤10 正常（测试 3 条：10 放行 / 含空行放行 / 11 拒绝）。

### P3 · 任务历史 JSON 持久化 ✅
- [x] `data/tasks.json`：终态（done/failed/canceled）写盘；**保留最近 500 条自动裁剪**；写盘带锁（防 worker 线程与 API 并发冲突）
- [x] 启动时恢复：终态任务进历史分组；**进行中任务标记"中断"（interrupted，灰色徽标）归入历史**
- [x] TaskManager 生命周期接入：`enqueue/终态` 更新持久化；`clear_history()` 未做（见 §2 候选）
- [x] 前端：TaskPanel 增加"中断"徽标样式（灰）；历史分组含 interrupted
- [x] 测试：持久化恢复、500 裁剪、中断标记

**验收**：✅ 终态写盘/恢复/中断标记/裁剪/损坏容错/finished_at 透传（test_persist.py 8 条）。

### P4 · 历史重试按钮 ✅
- [x] 历史行（failed / interrupted / canceled）增加"重试"按钮：复用 `POST /api/tasks`（同一 URL 重新入队，URL 取自 `input_url`）
- [x] 测试：重试入队成功、不产生重复持久化记录（同 URL 重复 create → 新任务并存）

**验收**：✅ 失败任务点"重试"→ 新任务入队执行；done 行提供"下载"链接。

### P5 · 打包版恢复无感获取 Cookie（捆绑 Chromium） ✅
- [x] `release.yml` 矩阵构建：`pip install playwright` + `playwright install chromium`（每平台调取对应版本）
- [x] `packaging/bilidownloader.spec`：playwright 库随包（excludes 移除）；**Chromium 由 release.yml 打包后直拷产物 `_browsers/`**（实施修正：spec datas 方案在 macOS 上触发 PyInstaller 重签 Chrome.app 失败，2026-09-05）
- [x] 运行时定位：launcher/main 设置 `PLAYWRIGHT_BROWSERS_PATH` 指向包内浏览器目录（`sys._MEIPASS/_browsers`）
- [x] `api/cookie.py` guide：**移除"打包版仅支持手动粘贴"分支**，与开发模式一致（无感获取文案 + 书签/粘贴兜底）
- [ ] 体积与构建时间确认：zip ~180-200MB、CI +1~2 分钟（P6 远端产物核验）
- [ ] 测试：打包版（本地 mac 验收）acquire 弹出窗口（P6 真机验收）；`is_packaged` 分支单测 ✅ 已加

**验收**：⏳ 远端构建产物内含有头 Chromium；打包版点"获取 Cookie"弹窗登录自动捕获；guide 返回无感文案（单测已过，真机待 P6）。

### P6 · 发布与回归 🔵
- [x] 全量回归：存量 83 测试 + 新增用例全绿（96 passed）；ruff 通过
- [ ] 推送 `v0.1.1` 标签 → 双平台自动构建 + 自动发布（Release 资产含 Chromium）
- [x] 更新 `docs/project-status.md`（v0.1.1 移交"已完成/待发布"）
- [ ] 真实设备验收（mac：右键打开 → 无感 Cookie → 下载；Windows：虚拟/实体机同流程）

**验收**：Release v0.1.1 双平台资产就绪；`manual-test-plan.md` §4/§5 在新产物上通过。

---

## 2. v0.1.2+ 候选（维持优先级，不掺入 v0.1.1）

### 高优先
- 多P 全选批量下载（合集/收藏夹形态解析）
- GitHub workflow 增加 test job（pytest + ruff 门禁，失败中止发布）
- 任务历史手动清空按钮（P3 若未含）+ 搜索/过滤
- 真实 Windows 验收沉淀（截图/日志回填 manual-test-plan）

### 中优先
- 更多 URL 形态：B 站音频区（au）、b23.tv 真实短链联调、合集
- 更多平台接入：YouTube 等（新增 `UrlParser` 实现 + `register()`，接口化红利）
- 视频下载支持（当前仅音频 MP3 192k）
- 下载优化：并发数可配置、限速、格式扩展（FLAC/WAV）
- 文件名自定义模板

### 低优先
- 深色/浅色主题切换
- 系统通知 / 托盘
- 自动更新检查（对拍 Release 版本）
- i18n 国际化
- 移动端响应式适配
- 正式签名/公证 + dmg/NSIS 安装包
- 成品列表内嵌播放器

---

## 3. 明确不做（当前共识，除非现实触发）

| 项 | 原因 |
|----|------|
| 412 冷却机制 | 低频基线（单次 ≤10、常 1 条）概率低；真遇到再补 |
| 首次运行强制免责弹窗 | 影响体验，且对传播场景无拦截力 |
| Cookie 加密（钥匙串/DPAPI） | 本地单机工具复杂度不值；以"勿在共享设备使用"提示代替 |
| 应用内按需下载 Chromium | 已被 P5 捆绑方案取代（体积换体验） |

---

## 4. 变更联动清单（实施时同步维护）

| 随 P1-P6 变更的文件 | 动作 |
|---------------------|------|
| `LICENSE`（新增）、`README.md` | P1 |
| `backend/app/api/tasks.py` + schemas + UrlForm.vue | P2 |
| `backend/app/core/task/manager.py` + `core/task/persist.py`（新增）+ TaskPanel.vue | P3/P4 |
| `packaging/bilidownloader.spec`、`.github/workflows/release.yml`、`app/launcher.py` 或 `config.py` | P5 |
| `docs/design-analysis.md`（§2.4/决策表）、`docs/project-status.md`、`docs/manual-test-plan.md` | 全项同步 |
| `docs/development-guide.md` | P3/P5 规范补充（持久化写盘规范、捆绑目录约定） |