"""M1 冒烟测试：hello 与 health 路由可访问。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    """/ 在静态托管模式下返回前端页面；否则返回 JSON 状态。"""
    r = client.get("/")
    assert r.status_code == 200
    ctype = r.headers.get("content-type", "")
    if ctype.startswith("application/json"):
        assert r.json()["status"] == "ok"
    else:
        assert "html" in ctype  # frontend/dist 静态托管模式


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["version"] == "0.1.0"