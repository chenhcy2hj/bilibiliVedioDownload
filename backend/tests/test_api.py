"""API 冒烟测试：capabilities / tasks / settings / cookie 状态 与统一错误结构。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestCapabilities:
    def test_capabilities(self):
        r = client.get("/api/capabilities")
        assert r.status_code == 200
        parsers = r.json()["parsers"]
        assert any(p["source"] == "bilibili" for p in parsers)


class TestTasksAPI:
    def test_create_task_no_cookie_ok(self):
        """无 Cookie 时任务可创建（执行阶段会 failed(auth)），不得 500。"""
        r = client.post("/api/tasks", json={"urls": ["BV1JRuA6vEvd"]})
        assert r.status_code == 201
        body = r.json()
        assert len(body) == 1
        assert body[0]["source"] == "bilibili"
        assert body[0]["status"] in (
            "pending", "parsing", "downloading", "converting", "done", "failed", "canceled",
        )

    def test_create_task_unsupported_url(self):
        r = client.post("/api/tasks", json={"urls": ["https://example.com/xxx"]})
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "UNSUPPORTED_URL"
        assert body["message"]

    def test_create_task_batch_10_ok(self):
        """恰好 10 条放行。"""
        urls = ["BV1JRuA6vEv" + str(i) for i in range(10)]
        r = client.post("/api/tasks", json={"urls": urls})
        assert r.status_code == 201
        assert len(r.json()) == 10

    def test_create_task_batch_10_with_blank_lines_ok(self):
        """10 条中含空行/纯空白行仍放行（空行不计入数量）。"""
        urls = ["BV1JRuA6vEv" + str(i) for i in range(8)]
        urls += ["", "   ", " "]
        r = client.post("/api/tasks", json={"urls": urls})
        assert r.status_code == 201
        assert len(r.json()) == 8

    def test_create_task_batch_too_large(self):
        """11 条 → 422 BATCH_TOO_LARGE（含空白行干扰也不放行）。"""
        urls = ["BV1JRuA6vEv" + str(i) for i in range(10)]
        urls += ["", "BV1JRuA6vEvX", "  "]
        r = client.post("/api/tasks", json={"urls": urls})
        assert r.status_code == 422
        body = r.json()
        assert body["code"] == "BATCH_TOO_LARGE"
        assert body["message"]

    def test_retry_same_url_creates_second_task(self):
        """P4 重试：同一 URL 重复提交 → 201 且两个任务并存（不覆盖历史记录）。"""
        r1 = client.post("/api/tasks", json={"urls": ["BV1JRuA6vEvd"]})
        r2 = client.post("/api/tasks", json={"urls": ["BV1JRuA6vEvd"]})
        assert r1.status_code == 201
        assert r2.status_code == 201
        ids = [r.json()[0]["id"] for r in (r1, r2)]
        assert ids[0] != ids[1]
        all_tasks = client.get("/api/tasks").json()
        matched = [t for t in all_tasks if t["id"] in ids]
        assert len(matched) == 2

    def test_list_tasks(self):
        client.post("/api/tasks", json={"urls": ["BV1JRuA6vEvd"]})
        r = client.get("/api/tasks")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_cancel_missing_task_404(self):
        r = client.delete("/api/tasks/not-exist")
        assert r.status_code == 404
        assert r.json()["code"] == "TASK_NOT_FOUND"

    def test_download_file_not_ready(self):
        r = client.post("/api/tasks", json={"urls": ["BV1JRuA6vEvd"]})
        task_id = r.json()[0]["id"]
        r2 = client.get(f"/api/tasks/{task_id}/file")
        # 未完成（或无成品）→ 409 或 200（若恰好完成且无文件则 409）
        assert r2.status_code in (200, 409)


class TestSettingsAPI:
    def test_get_settings_default(self):
        r = client.get("/api/settings")
        assert r.status_code == 200
        body = r.json()
        assert body["output_dir"]
        assert body["audio_format"] == "mp3"

    def test_update_settings_invalid_path(self):
        r = client.put("/api/settings", json={"output_dir": "relative/x"})
        assert r.status_code == 422
        assert r.json()["code"] == "INVALID_PATH"
        assert r.json()["message"]


class TestCookieAPI:
    def test_status_without_cookie_file(self):
        r = client.get("/api/cookie/status")
        assert r.status_code == 200
        body = r.json()
        assert body["valid"] is False

    def test_guide(self):
        r = client.get("/api/cookie/guide")
        assert r.status_code == 200
        assert "bilibili.com" in r.json()["jump_url"]

    def test_guide_packaged_branch(self, monkeypatch):
        """P5：打包版 guide 回正——内置浏览器无感文案 + 书签/粘贴兜底（bookmarklet=None）。"""
        import app.api.cookie as cookie_api

        monkeypatch.setattr(cookie_api, "is_packaged", lambda: True)
        r = client.get("/api/cookie/guide")
        assert r.status_code == 200
        body = r.json()
        assert body["bookmarklet"] is None
        steps = " ".join(body["steps"])
        assert "内置浏览器" in steps  # 无感获取文案（P5 回正）
        assert "粘贴" in steps  # 手动粘贴仍为兜底
        assert "请使用手动粘贴方式" not in steps  # 旧"仅手动"语义已移除


class TestHealth:
    def test_health(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"