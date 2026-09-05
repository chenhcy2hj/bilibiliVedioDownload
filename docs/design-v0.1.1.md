# v0.1.1 技术方案设计（P2–P6）

> 前置：需求共识见 `docs/roadmap.md` §1；本文件为 P2–P6 的实现级设计（数据结构、接口、流程、边界）。
> 状态：设计定稿、待实施。实施中如发现与现实冲突，先更新本文件再改代码。

---

## P2 · 批量上限（≤10 条）

### 目标
单次提交最多 10 条链接（正常 1 条），前后端双重拦截。

### 设计
**常量**：`app/config.py` 新增 `MAX_URLS_PER_BATCH = 10`。

**后端**（`app/api/tasks.py` `create_tasks`）：
1. 先对 `body.urls` 做 strip + 去空行，得到有效行数 `n`；
2. `n > MAX_URLS_PER_BATCH` → `raise ApiError("BATCH_TOO_LARGE", "单次最多提交 10 条链接", status_code=422)`；
3. 其余逻辑不变（n == 0 仍走 `EMPTY_URLS`）。

**前端**（`UrlForm.vue`）：
- 常量 `MAX_ROWS = 10`；`rows.length > MAX_ROWS` 时：提交按钮禁用 + 行内红字提示「最多 10 条（当前 N）」；
- 不阻塞粘贴，仅提交拦截。

### 边界与错误处理
- 空行/纯空白行不计入数量；`n=0` 走既有 `EMPTY_URLS`；
- 恰好 10 条放行。

### 测试
- 后端：10 条 → 201；11 条（含空白行干扰）→ 422 `BATCH_TOO_LARGE`；10 条中有空行仍放行。

### 涉及文件
`backend/app/config.py`、`backend/app/api/tasks.py`、`backend/tests/test_api.py`、`frontend/src/components/UrlForm.vue`。

---

## P3 · 任务历史 JSON 持久化

### 目标
任务终态（done/failed/canceled）与启动时识别的中断任务跨重启保留；**保留最近 500 条**；进行中任务启动后标记「中断」归入历史。

### 数据文件
`data/tasks.json`（新增 `TASKS_FILE = DATA_DIR / "tasks.json"`，打包模式自动落入平台用户目录）。

结构：
```json
{
  "tasks": [
    {
      "id": "12fd4b3c45d5",
      "input_url": "BV1JRuA6vEvd",
      "source": "bilibili",
      "kind": "single",
      "entry_count": 1,
      "title": "xxx | null",
      "status": "done | failed | canceled | interrupted",
      "error_code": "auth | null",
      "error_message": "... | null",
      "file_path": "/abs/a.mp3 | null",
      "created_at": "2026-08-28T12:00:00+00:00",
      "finished_at": "2026-08-28T12:01:00+00:00 | null"
    }
  ]
}
```
只保存终态字段（不保存进度/速度等瞬时量）。

### 写入时机（状态机驱动，非进度驱动）
- `TaskManager._set_task_status()` 统一状态切换入口（现有 `_set` 拆分出状态字段变更）——**每次 Task.status 变更**（pending→parsing→…→done/failed/canceled）触发 `persist_snapshot()`；
- 进度事件（task.progress，200ms 级）**不写盘**；
- 写盘全量快照：内存中「进行中 + 终态」任务序列化；原子写入（tmp 文件 + `os.replace`）；`threading.Lock` 保护（worker 线程与 API 线程并发）。

### 裁剪
- 写盘后若 > `MAX_HISTORY = 500`：按 `created_at` 保留最新 500 条。

### 启动恢复（`TaskManager.load_history()`，app 启动时调用）
1. 读 `tasks.json`（缺失/损坏 → 空历史，不报错）；
2. `status` 为终态（done/failed/canceled/interrupted）→ 直接恢复进 `_tasks`（**不重新入队、不进进行中**）；
3. `status` 为进行中（pending/parsing/downloading/converting）→ 改写为 **interrupted**（`finished_at=now`）并写回；
4. 恢复的任务不发 WS 增量事件（快照/列表自然可见）。

### 状态枚举
`TaskStatus` 新增 `INTERRUPTED = "interrupted"`；`to_response` 透传（新增 `finished_at` 字段）。

### 前端
- `TaskPanel.vue`：状态徽标新增 `interrupted`（灰，文案"中断"），归入历史分组（history 过滤条件加入 interrupted）；
- 历史行失败/中断可重试（见 P4）。

### 边界与错误处理
- tasks.json 损坏 → 按空历史启动并重写（不崩溃）；
- 写盘失败（磁盘满）→ 仅日志告警，不影响任务运行；
- 并发写：同一时刻只允许一个写盘（锁 + 串行 worker 天然低竞争）。

### 测试
- 写入：任务终态后文件存在且字段完整；进行中不产生写入；
- 恢复：预置文件 → 终态恢复 / 进行中变 interrupted 且写回；
- 裁剪：写入 501+ 条 → 保留最新 500；
- 损坏文件容错；`finished_at` 透传。

### 涉及文件
`backend/app/config.py`、`backend/app/core/task/persist.py`（新增）、`backend/app/core/task/manager.py`、`backend/app/schemas/task.py`、`backend/app/main.py`（启动调 load_history）、`frontend/src/components/TaskPanel.vue`、`backend/tests/test_persist.py`（新增）。

---

## P4 · 历史重试按钮

### 目标
历史行（failed / interrupted / canceled）一键重试：同一 URL 重新入队。

### 设计
- **后端零改动**：复用 `POST /api/tasks`（按 `input_url` 重新走 registry.dispatch → enqueue）；
- 前端 `TaskPanel.vue` 历史行：`status ∈ {failed, interrupted, canceled}` 时渲染「重试」按钮：
  ```js
  async function retry(t) {
    await api.createTasks([t.input_url])
    // 成功：新任务经 WS 出现在进行中；按钮短暂"已重试"态
  }
  ```
- 重试失败（如 URL 已不支持）→ 展示错误（alert 或行内提示）。

### 边界
- done 行不显示重试（有"下载"按钮）；
- 重试产生**新任务**（不修改历史记录）；新旧可能重复下载（文件名去重兜底 `(1)` 后缀）。

### 测试
- 前端构建验证；后端补一条 API 测试：同 URL 重复 create → 201 且两任务并存。

---

## P5 · Chromium 捆绑发布包（打包版恢复无感获取）

### 目标
发布包内置有头 Chromium；打包版「获取 Cookie」恢复与开发模式一致的无感捕获。

### 构建链路（`.github/workflows/release.yml`）
在 PyInstaller 打包步骤前：
```bash
pip install playwright          # requirements.txt 已含
python -m playwright install chromium
```
- macos-15 runner（arm64）→ `~/Library/Caches/ms-playwright/chromium-*`
- windows-latest → `%LOCALAPPDATA%\ms-playwright\chromium-*`
- 下载 ~160MB，构建时长 +1~2 分钟（接受）。

### spec 捆绑（`packaging/bilidownloader.spec`）
- `excludes` 移除 `playwright`（需要打包其 Python 库）；
- datas 增加（按平台取缓存路径，glob `chromium-<数字>*`，排除 headless shell 节省 ~100MB）：
  ```python
  _browsers = glob.glob(str(PW_CACHE / "chromium-[0-9]*"))
  datas += [(d, f"_browsers/{Path(d).name}") for d in _browsers]
  ```
- 目标目录 `_browsers` → onedir 下位于 `Contents/Frameworks/_browsers`（macOS）/ 可执行同目录（Windows），即 `sys._MEIPASS/_browsers`。

### 运行时定位（`backend/app/launcher.py`）
在 import app.main **之前**（模块级启动路径起点）：
```python
if is_packaged():
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH",
        str(Path(getattr(sys, "_MEIPASS", Path(sys.argv[0]).resolve().parent)) / "_browsers"),
    )
```
`browser.py` 保持惰性 import 与 `BrowserUnavailable` 兜底（防个别包未捆绑时的崩溃，改为明确错误）。

### guide 文案回正（`backend/app/api/cookie.py`）
- 移除「打包版仅支持手动粘贴」分支语义；
- 打包版：`bookmarklet=None`（动态端口使书签回传不适用），steps 改为「点击获取 Cookie → 弹内置浏览器窗口完成登录 → 自动捕获保存；书签/粘贴仍为兜底」；
- 开发模式不变。

### 体积与时间
- 解压后 ~450MB（原 80MB），zip ~180-200MB（原 40MB）；
- CI 构建时间 +1~2 分钟。

### 测试与验收
- 单测：guide 打包版分支按新文案断言（模拟 `is_packaged`）；
- 远端产物验收：解压 .app/.exe → 点「获取 Cookie」弹出内置 Chromium → 登录自动捕获；
- 本地开发模式不受影响（仍走系统 ms-playwright 缓存）。

---

## P6 · 发布与回归

### 流程
1. 全量回归：`pytest`（存量 83 + 新增用例）+ `ruff` 全绿 + 前端 `npm run build` 通过；
2. 更新 `docs/project-status.md`（P1–P6 移交"已完成"，未完成 #1 移除）与 `docs/roadmap.md`（勾选 v0.1.1 清单）；
3. 推送 `v0.1.1` 标签 → 双平台自动构建 + 自动发布（Release 资产含 Chromium；body 模板已含免责）；
4. 真实设备验收：mac 右键打开 → 无感 Cookie → 下载冒烟；Windows 实体/虚拟机构同类验证；
5. 验收结果回填 `docs/manual-test-plan.md`。

### 风险与回退
- CI 下载 Chromium 失败（网络）→ workflow 重跑（幂等）；
- 若发现捆绑后体积/启动异常 → 回退为「按需下载」方案（roadmap Q3 备选），需回到本设计修订。

---

## 涉及文件总览（P2–P6）

| 文件 | 变更 |
|------|------|
| `backend/app/config.py` | `MAX_URLS_PER_BATCH`、`TASKS_FILE`、`MAX_HISTORY` |
| `backend/app/api/tasks.py` | 批量上限校验 |
| `backend/app/api/cookie.py` | guide 打包版文案回正 |
| `backend/app/core/task/persist.py`（新增） | tasks.json 写入/裁剪/恢复 |
| `backend/app/core/task/manager.py` | 状态变更触发持久化、load_history、INTERRUPTED |
| `backend/app/schemas/task.py` | `INTERRUPTED` 枚举、`finished_at` 字段 |
| `backend/app/core/downloader/base.py` | ProgressEvent 无变更（终态由 Task 状态携带） |
| `backend/app/launcher.py` | PLAYWRIGHT_BROWSERS_PATH 注入 |
| `frontend/src/components/UrlForm.vue` | ≤10 提示与拦截 |
| `frontend/src/components/TaskPanel.vue` | interrupted 徽标、重试按钮 |
| `packaging/bilidownloader.spec` | 捆绑 chromium（移除 excludes） |
| `.github/workflows/release.yml` | 增加 `playwright install chromium` |
| `backend/tests/test_persist.py`（新增）、`test_api.py`、`test_acquire.py` | 新用例 |
| `docs/project-status.md`、`docs/roadmap.md` | 状态流转 |