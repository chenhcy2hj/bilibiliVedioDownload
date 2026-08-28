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


class TestHealth:
    def test_health(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"