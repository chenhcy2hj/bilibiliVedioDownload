"""M6 打包版 token 鉴权测试：launcher 设置 auth_token 后 HTTP/WS 均须携带。"""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


class TestTokenAuth:
    def test_dev_mode_no_token_required(self):
        """开发模式（auth_token=None）不校验。"""
        app.state.auth_token = None
        client = TestClient(app)
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_packaged_mode_requires_header(self):
        app.state.auth_token = "secret-token-123"
        client = TestClient(app)
        # 无 token → 401 统一错误结构
        r = client.get("/api/health")
        assert r.status_code == 401
        assert r.json()["code"] == "AUTH_REQUIRED"
        # 错误 token → 401
        r = client.get("/api/health", headers={"X-Auth-Token": "wrong"})
        assert r.status_code == 401
        # 正确 token → 200
        r = client.get("/api/health", headers={"X-Auth-Token": "secret-token-123"})
        assert r.status_code == 200

    def test_packaged_mode_static_allowed(self):
        """静态页面/资源不校验 token（浏览器入口加载无法带 header）。"""
        app.state.auth_token = "secret-token-123"
        client = TestClient(app)
        r = client.get("/")
        assert r.status_code == 200
        r = client.get("/assets/x.js")
        assert r.status_code != 401

    def test_packaged_mode_ws_requires_token(self):
        app.state.auth_token = "ws-token"
        client = TestClient(app)
        # 无/错 token → 服务端在 accept 前关闭连接
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/ws"):
            pass
        # 正确 token → 正常收到快照
        with client.websocket_connect("/api/ws?token=ws-token") as ws:
            snap = ws.receive_json()
            assert snap["type"] == "task.snapshot"
        app.state.auth_token = None