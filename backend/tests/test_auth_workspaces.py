"""Authentication and tenant-boundary checks, using disposable databases only."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from starlette.websockets import WebSocketDisconnect

from app.application import create_app
from app.core.auth_service import COOKIE_NAME

PASSWORD = "Test-password-12345"


class AccountWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.app = create_app(self.directory.name, ["http://testserver"])
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.directory.cleanup()

    def register(self, name):
        self.client.cookies.clear()
        response = self.client.post("/api/auth/register", json={"username": name, "display_name": "测试教师", "password": PASSWORD})
        self.assertEqual(response.status_code, 201, response.text)
        token = response.cookies[COOKIE_NAME]
        self.client.cookies.clear()
        return response.json()["user"], {"Cookie": f"{COOKIE_NAME}={token}"}

    def upload(self, cookie, value):
        workbook = Workbook()
        workbook.active.title = "概况"
        workbook.active.append(["名称", "数量"])
        workbook.active.append([value, 10])
        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()
        return self.client.post("/api/upload", headers=cookie, files={"files": ("same.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

    def test_registration_login_logout_and_password_storage(self):
        user, cookie = self.register("teacher_a")
        self.assertEqual(self.client.get("/api/auth/me", headers=cookie).json()["user"], user)
        duplicate = self.client.post("/api/auth/register", json={"username": "TEACHER_A", "password": PASSWORD})
        self.assertEqual(duplicate.status_code, 409)
        wrong = self.client.post("/api/auth/login", json={"username": "teacher_a", "password": "incorrect"})
        self.assertEqual(wrong.status_code, 401)
        signed_in = self.client.post("/api/auth/login", json={"username": "TEACHER_A", "password": PASSWORD})
        self.assertEqual(signed_in.status_code, 200)
        self.assertIn("HttpOnly", signed_in.headers["set-cookie"])
        self.assertIn("SameSite=lax", signed_in.headers["set-cookie"])
        token = signed_in.cookies[COOKIE_NAME]
        with self.app.state.auth.connect() as conn:
            stored = conn.execute("SELECT password_hash FROM users").fetchone()[0]
            sessions = [row[0] for row in conn.execute("SELECT token_hash FROM sessions")]
        self.assertNotIn(PASSWORD, stored)
        self.assertNotIn(token, sessions)
        self.assertTrue(stored.startswith("pbkdf2_sha256$600000$"))
        self.client.cookies.clear()
        active_cookie = {"Cookie": f"{COOKIE_NAME}={token}"}
        self.assertEqual(self.client.post("/api/auth/logout", headers=active_cookie).status_code, 200)
        self.assertEqual(self.client.get("/api/tables", headers=active_cookie).status_code, 401)
        validation = self.client.post("/api/auth/register", json={"username": "bad", "password": "short"})
        self.assertEqual(validation.status_code, 422)
        self.assertNotIn('"input"', validation.text)

    def test_anonymous_requests_and_untrusted_origins_are_rejected(self):
        for endpoint in ("/api/tables", "/api/health", "/api/pipeline/status", "/api/pipeline/config", "/api/pipeline/stream", "/api/exports/report.docx", "/static/charts/test.png"):
            self.assertEqual(self.client.get(endpoint).status_code, 401, endpoint)
        with self.assertRaises(WebSocketDisconnect) as error:
            with self.client.websocket_connect("/api/pipeline/ws"):
                pass
        self.assertEqual(error.exception.code, 4401)
        blocked = self.client.post("/api/auth/register", headers={"Origin": "https://untrusted.example"}, json={"username": "blocked", "password": PASSWORD})
        self.assertEqual(blocked.status_code, 403)
        _, cookie = self.register("teacher_a")
        self.assertEqual(self.client.get("/api/pipeline/stream", headers=cookie | {"Origin": "https://untrusted.example"}).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/logout", headers=cookie | {"Sec-Fetch-Site": "cross-site"}).status_code, 403)

    def test_files_cells_directory_imports_and_tasks_are_isolated(self):
        user_a, cookie_a = self.register("teacher_a")
        user_b, cookie_b = self.register("teacher_b")
        self.assertEqual(self.upload(cookie_a, "甲账号专属记录").status_code, 200)
        self.assertEqual(self.client.get("/api/tables", headers=cookie_b).json()["total_cells"], 0)
        self.assertEqual(self.upload(cookie_b, "乙账号专属记录").status_code, 200)
        a = self.app.state.workspaces.get(user_a["id"])
        b = self.app.state.workspaces.get(user_b["id"])
        cell = next(cell for cell in a.cell_lake.get_all_cells() if cell["raw_value"] == "甲账号专属记录")
        own = self.client.get(f'/api/cell/{cell["cell_id"]}', headers=cookie_a).json()["cell"]
        other = self.client.get(f'/api/cell/{cell["cell_id"]}', headers=cookie_b).json()["cell"]
        self.assertEqual(own["raw_value"], "甲账号专属记录")
        self.assertEqual(other["raw_value"], "乙账号专属记录")
        (a.export_dir / "private.docx").write_bytes(b"account-a-report")
        (a.chart_dir / "private.png").write_bytes(b"account-a-chart")
        self.assertEqual(self.client.get("/api/exports/private.docx", headers=cookie_a).content, b"account-a-report")
        self.assertEqual(self.client.get("/api/exports/private.docx", headers=cookie_b).status_code, 404)
        self.assertEqual(self.client.get("/static/charts/private.png", headers=cookie_b).status_code, 404)
        self.assertEqual(self.client.get("/api/exports/%2e%2e%5c%2e%2e%5caccounts.db", headers=cookie_a).status_code, 404)
        blocked = self.client.post("/api/scan_directory", headers=cookie_b, json={"directory_path": str(a.upload_dir), "clear_existing": True})
        self.assertEqual(blocked.status_code, 403)
        self.assertGreater(b.cell_lake.count(), 0)
        traversal = self.client.post("/api/upload", headers=cookie_a, files={"files": ("../escape.xlsx", b"invalid")})
        self.assertEqual(traversal.status_code, 400)
        a.pipeline.sections_plan = [{"id": "private_section", "section_title": "甲账号章节"}]
        self.assertEqual(self.client.get("/api/pipeline/status", headers=cookie_b).json()["sections_plan"], [])
        a.operation_lock.acquire()
        try:
            self.assertEqual(self.client.post("/api/pipeline/config", headers=cookie_a, json={}).status_code, 409)
            self.assertEqual(self.client.post("/api/pipeline/config", headers=cookie_b, json={}).status_code, 200)
        finally:
            a.operation_lock.release()

    def test_accounts_config_and_last_report_survive_restart(self):
        user, cookie = self.register("teacher_a")
        secret = "test-only-private-model-key"
        self.assertEqual(self.upload(cookie, "个人报表").status_code, 200)
        response = self.client.post("/api/pipeline/config", headers=cookie, json={"api_key": secret, "model": "my-model", "agent_mode": "python_native"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(secret, self.client.get("/api/pipeline/config", headers=cookie).text)
        with self.app.state.auth.connect() as conn:
            encrypted = conn.execute("SELECT encrypted_key FROM model_configs").fetchone()[0]
        self.assertNotIn(secret, encrypted)
        self.client.post("/api/pipeline/config", headers=cookie, json={"model": "my-model", "agent_mode": "python_native"})
        self.assertTrue(self.client.get("/api/pipeline/config", headers=cookie).json()["has_api_key"])
        workspace = self.app.state.workspaces.get(user["id"])
        workspace.pipeline.current_stage = 5
        workspace.pipeline.generated_sections = [{"id": "private", "title": "私人报告", "content": "个人报告正文"}]
        workspace.pipeline.save_checkpoint()
        self.client.__exit__(None, None, None)
        self.app = create_app(self.directory.name, ["http://testserver"])
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.assertEqual(self.client.get("/api/auth/me", headers=cookie).status_code, 200)
        restored_tables = self.client.get("/api/tables", headers=cookie).json()
        self.assertGreater(restored_tables["total_cells"], 0)
        self.assertEqual(restored_tables["catalog"][0]["file_name"], "same.xlsx")
        self.assertEqual(restored_tables["catalog"][0]["sheet_name"], "概况")
        config = self.client.get("/api/pipeline/config", headers=cookie).json()
        self.assertEqual(config["model"], "my-model")
        self.assertTrue(config["has_api_key"])
        restored = self.client.get("/api/pipeline/status", headers=cookie).json()
        self.assertEqual(restored["generated_sections"][0]["content"], "个人报告正文")
        self.assertFalse(restored["is_running"])
        self.client.post("/api/pipeline/config", headers=cookie, json={"clear_api_key": True})
        self.assertFalse(self.client.get("/api/pipeline/config", headers=cookie).json()["has_api_key"])

    def test_rate_limit(self):
        for _ in range(10):
            response = self.client.post("/api/auth/login", json={"username": "missing", "password": PASSWORD})
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={"username": "missing", "password": PASSWORD}).status_code, 429)


if __name__ == "__main__":
    unittest.main()
