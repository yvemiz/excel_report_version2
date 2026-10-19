import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.application import create_app
from app.core.auth_service import AuthStore
from app.core.workspaces import Workspace
from app.pipeline.stages import ReportPipeline

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_XLS = PROJECT_ROOT / "example" / "表1-1学校概况数据.xls"


class DatasetWorkspaceTests(unittest.TestCase):
    def test_create_switch_and_isolate_datasets(self):
        with tempfile.TemporaryDirectory(prefix="dataset_ws_") as root:
            auth = AuthStore(root)
            user = auth.register("tester", "T", "longpassword123")
            ws = Workspace(user["id"], root, auth)
            legacy = ws.dataset(ws.legacy_dataset_id)
            self.assertEqual(legacy.cell_lake.count(), 0)
            a = ws.create_dataset("批次A", "2026")
            b = ws.create_dataset("批次B", "2025")
            a_ws, b_ws = ws.dataset(a["id"]), ws.dataset(b["id"])
            a_ws.cell_lake.insert_cells([{
                "cell_id": "cell_a_only", "file_name": "A.xlsx", "sheet_name": "Sheet1",
                "row_idx": 1, "col_idx": 1, "cell_ref": "A1",
                "metric_path": "学校 > 名称", "raw_value": "A", "numeric_value": None,
            }])
            self.assertEqual(a_ws.cell_lake.count(), 1)
            self.assertEqual(b_ws.cell_lake.count(), 0)
            self.assertEqual(legacy.cell_lake.count(), 0)
            report_a = a_ws.create_report("A大学")
            report_b = b_ws.create_report("B大学")
            self.assertNotEqual(report_a.report_version_id, report_b.report_version_id)
            self.assertEqual(report_a.snapshot()["dataset_id"], a["id"])
            self.assertEqual(report_b.snapshot()["dataset_id"], b["id"])
            ws.close()

    def test_retry_section_reuses_other_sections(self):
        with tempfile.TemporaryDirectory(prefix="retry_section_") as root:
            auth = AuthStore(root)
            user = auth.register("tester", "T", "longpassword123")
            ws = Workspace(user["id"], root, auth)
            dataset = ws.create_dataset("2026 评估", "2026")
            report = ws.dataset(dataset["id"]).create_report("海南师范大学")
            report.pipeline.custom_school_name = "海南师范大学"
            report.pipeline.sections_plan = [
                {"id": "s1", "title": "1.1 通过", "section_title": "1.1 通过"},
                {"id": "s2", "title": "2.1 异常", "section_title": "2.1 异常"},
                {"id": "s3", "title": "3.1 另一个异常", "section_title": "3.1 另一个异常"},
            ]
            report.pipeline.generated_sections = [
                {"id": "s1", "title": "1.1 通过", "passed": True, "content": "ok"},
                {"id": "s2", "title": "2.1 异常", "passed": False, "content": "bad"},
                {"id": "s3", "title": "3.1 另一个异常", "passed": False, "content": "also bad"},
            ]
            report.pipeline.save_checkpoint()
            retried = report.retry_section("s2")
            self.assertNotEqual(retried.report_version_id, report.report_version_id)
            self.assertEqual([item["id"] for item in retried.pipeline.sections_plan], ["s1", "s2", "s3"])
            self.assertEqual([item["id"] for item in retried.pipeline.generated_sections], ["s1", "s3"])
            self.assertEqual(retried.version["status"], "running")
            ws.close()

    def test_quality_summary_flags_outline_and_failed_sections(self):
        with tempfile.TemporaryDirectory(prefix="quality_ws_") as root:
            auth = AuthStore(root)
            user = auth.register("tester", "T", "longpassword123")
            ws = Workspace(user["id"], root, auth)
            dataset = ws.create_dataset("2026 评估", "2026")
            report = ws.dataset(dataset["id"]).create_report("海南师范大学")
            report.pipeline.outline_jev_audit = {
                "is_approved": False, "structure_score": 0.82, "critique": "章节错位",
            }
            report.pipeline.generated_sections = [
                {"id": "s1", "title": "1.1 通过", "passed": True,
                 "audit": {"is_approved": True, "mismatch_count": 0}, "jev": {"approved": True}},
                {"id": "s2", "title": "2.1 异常", "passed": False,
                 "audit": {"is_approved": False, "mismatch_count": 2}, "jev": {"approved": False, "rejection_reason": "逻辑质量分偏低"}},
            ]
            quality = report.snapshot()["quality_summary"]
            self.assertTrue(quality["needs_attention"])
            self.assertFalse(quality["can_deliver"])
            self.assertEqual(quality["sections_total"], 2)
            self.assertEqual(quality["sections_failed"], 1)
            self.assertEqual(quality["failed_sections"][0]["title"], "2.1 异常")
            report.pipeline.outline_jev_audit = {"is_approved": True, "structure_score": 0.95}
            report.pipeline.generated_sections = [
                {"id": "s1", "title": "1.1 通过", "passed": True,
                 "audit": {"is_approved": True, "mismatch_count": 0}, "jev": {"approved": True}},
            ]
            clean = report.snapshot()["quality_summary"]
            self.assertFalse(clean["needs_attention"])
            self.assertTrue(clean["can_deliver"])
            ws.close()

    def test_legacy_checkpoint_becomes_readable_report_version(self):
        with tempfile.TemporaryDirectory(prefix="legacy_ws_") as root:
            auth = AuthStore(root)
            user = auth.register("tester", "T", "longpassword123")
            checkpoint_dir = Path(root) / "users" / str(user["id"]) / "checkpoints"
            checkpoint_dir.mkdir(parents=True)
            (checkpoint_dir / "pipeline_checkpoint.json").write_text(json.dumps({
                "current_stage": 5,
                "school_name": "历史学校",
                "sections_plan": [],
                "generated_sections": [],
                "export_files": {},
                "outline_audit": {},
                "data_changed": False,
            }, ensure_ascii=False), encoding="utf-8")
            ws = Workspace(user["id"], root, auth)
            snapshot = ws.snapshot()
            self.assertEqual(snapshot["report_version_id"], f"rv_legacy_{user['id']}")
            self.assertEqual(snapshot["report_version_status"], "completed")
            self.assertEqual(snapshot["dataset_kind"], "legacy")
            ws.close()


class DatasetApiTests(unittest.TestCase):
    def test_same_named_files_are_isolated_across_datasets(self):
        with tempfile.TemporaryDirectory(prefix="dataset_api_") as root:
            app = create_app(data_dir=root, allowed_origins=["http://testserver"])
            with TestClient(app) as client:
                response = client.post("/api/auth/register", json={
                    "username": "tester", "password": "longpassword123", "display_name": "T",
                })
                self.assertEqual(response.status_code, 201)
                a = client.post("/api/datasets", json={"name": "A", "academic_year": "2026"}).json()["dataset"]["id"]
                b = client.post("/api/datasets", json={"name": "B", "academic_year": "2025"}).json()["dataset"]["id"]
                for dataset_id in (a, b):
                    with EXAMPLE_XLS.open("rb") as file:
                        response = client.post(
                            f"/api/upload?dataset_id={dataset_id}",
                            files={"files": (EXAMPLE_XLS.name, file, "application/vnd.ms-excel")},
                        )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["dataset_id"], dataset_id)
                self.assertEqual(client.get(f"/api/tables?dataset_id={a}").json()["total_cells"], 15)
                self.assertEqual(client.get(f"/api/tables?dataset_id={b}").json()["total_cells"], 15)
                with EXAMPLE_XLS.open("rb") as file:
                    duplicate = client.post(
                        f"/api/upload?dataset_id={a}",
                        files={"files": (EXAMPLE_XLS.name, file, "application/vnd.ms-excel")},
                    )
                self.assertEqual(duplicate.status_code, 409)
                datasets = client.get("/api/datasets").json()["datasets"]
                by_id = {item["id"]: item for item in datasets}
                self.assertEqual(by_id[a]["cell_count"], 15)
                self.assertEqual(by_id[b]["cell_count"], 15)
                status = client.get(f"/api/datasets/{a}/status").json()
                self.assertEqual(status["dataset_id"], a)
                self.assertEqual(status["report_version_status"], "empty")

    def test_sse_creates_separate_report_versions_without_model_call(self):
        with tempfile.TemporaryDirectory(prefix="dataset_versions_") as root:
            app = create_app(data_dir=root, allowed_origins=["http://testserver"])
            with TestClient(app) as client:
                client.post("/api/auth/register", json={
                    "username": "tester", "password": "longpassword123", "display_name": "T",
                })
                client.put("/api/school", json={"school_name": "海南师范大学", "school_code": "11658"})
                dataset = client.post("/api/datasets", json={"name": "2026 评估", "academic_year": "2026"}).json()["dataset"]["id"]
                with EXAMPLE_XLS.open("rb") as file:
                    client.post(
                        f"/api/upload?dataset_id={dataset}",
                        files={"files": (EXAMPLE_XLS.name, file, "application/vnd.ms-excel")},
                    )

                async def fake_execute(self, school_name=None, resume=False, max_concurrency=3, use_existing_outline=False):
                    self.current_stage = 5
                    yield {"type": "stage_update", "stage_id": 5, "status": "completed", "data": {}}

                with patch.object(ReportPipeline, "execute_pipeline", fake_execute):
                    first = client.get(f"/api/pipeline/stream?dataset_id={dataset}&school_name=海南师范大学")
                    second = client.get(f"/api/pipeline/stream?dataset_id={dataset}&school_name=海南师范大学")
                self.assertEqual(first.status_code, 200, first.text)
                self.assertEqual(second.status_code, 200, second.text)
                ids = re.findall(r'"report_version_id": "(rv_[0-9a-f]+)"', first.text + second.text)
                self.assertEqual(len(ids), 2, first.text + second.text)
                self.assertNotEqual(ids[0], ids[1])
                reports = client.get(f"/api/datasets/{dataset}/reports").json()["reports"]
                self.assertEqual(len(reports), 2)
                self.assertTrue(all(item["status"] == "completed" for item in reports))

    def test_outline_confirmation_flow(self):
        with tempfile.TemporaryDirectory(prefix="outline_flow_") as root:
            app = create_app(data_dir=root, allowed_origins=["http://testserver"])
            with TestClient(app) as client:
                client.post("/api/auth/register", json={
                    "username": "tester", "password": "longpassword123", "display_name": "T",
                })
                client.put("/api/school", json={"school_name": "海南师范大学", "school_code": "11658"})
                dataset = client.post("/api/datasets", json={"name": "2026 评估", "academic_year": "2026"}).json()["dataset"]["id"]
                with EXAMPLE_XLS.open("rb") as file:
                    client.post(
                        f"/api/upload?dataset_id={dataset}",
                        files={"files": (EXAMPLE_XLS.name, file, "application/vnd.ms-excel")},
                    )

                outline = [{
                    "id": "s1", "chapter_title": "第一章 测试", "section_title": "1.1 测试小节",
                    "objective": "测试", "file_name": EXAMPLE_XLS.name,
                    "sheet_name": "1-1.学校概况", "table_name": "tbl_test",
                }]

                async def fake_plan(self, school_name=""):
                    self.sections_plan = outline
                    self.outline_jev_audit = {"is_approved": False, "structure_score": 0.82, "critique": "需复核"}
                    return outline

                async def fake_execute(self, school_name=None, resume=False, max_concurrency=3, use_existing_outline=False):
                    self.current_stage = 5
                    yield {"type": "stage_update", "stage_id": 5, "status": "completed", "data": {}}

                with patch.object(ReportPipeline, "async_plan_outline", fake_plan):
                    planned = client.post(f"/api/pipeline/outline?dataset_id={dataset}&school_name=海南师范大学")
                self.assertEqual(planned.status_code, 200, planned.text)
                report_id = planned.json()["report_version_id"]
                self.assertEqual(len(planned.json()["outline"]), 1)
                status = client.get(f"/api/datasets/{dataset}/status").json()
                self.assertEqual(status["report_version_id"], report_id)
                self.assertEqual(status["report_version_status"], "outline_ready")
                self.assertEqual(len(status["sections_plan"]), 1)

                with patch.object(ReportPipeline, "execute_pipeline", fake_execute):
                    confirmed = client.get(
                        f"/api/pipeline/stream?dataset_id={dataset}&report_version_id={report_id}&skip_outline=true&school_name=海南师范大学"
                    )
                self.assertEqual(confirmed.status_code, 200, confirmed.text)
                reports = client.get(f"/api/datasets/{dataset}/reports").json()["reports"]
                matched = next(item for item in reports if item["id"] == report_id)
                self.assertEqual(matched["status"], "completed")

    def test_load_example_creates_separate_demo_dataset(self):
        with tempfile.TemporaryDirectory(prefix="dataset_demo_") as root:
            app = create_app(data_dir=root, allowed_origins=["http://testserver"])
            with TestClient(app) as client:
                client.post("/api/auth/register", json={
                    "username": "tester", "password": "longpassword123", "display_name": "T",
                })
                active = client.post("/api/datasets", json={"name": "正式批次", "academic_year": "2026"}).json()["dataset"]["id"]
                with EXAMPLE_XLS.open("rb") as file:
                    client.post(
                        f"/api/upload?dataset_id={active}",
                        files={"files": (EXAMPLE_XLS.name, file, "application/vnd.ms-excel")},
                    )
                response = client.post("/api/load_example_data")
                self.assertEqual(response.status_code, 200)
                demo = response.json()["dataset_id"]
                self.assertNotEqual(demo, active)
                self.assertEqual(client.get(f"/api/tables?dataset_id={active}").json()["total_cells"], 15)
                demo_tables = client.get(f"/api/tables?dataset_id={demo}").json()
                self.assertEqual(demo_tables["total_cells"], 2221)
                self.assertEqual(len(demo_tables["catalog"]), 8)

    def test_pipeline_rejects_school_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="dataset_mismatch_") as root:
            app = create_app(data_dir=root, allowed_origins=["http://testserver"])
            with TestClient(app) as client:
                client.post("/api/auth/register", json={
                    "username": "tester", "password": "longpassword123", "display_name": "T",
                })
                dataset = client.post("/api/datasets", json={"name": "A", "academic_year": "2026"}).json()["dataset"]["id"]
                with EXAMPLE_XLS.open("rb") as file:
                    client.post(
                        f"/api/upload?dataset_id={dataset}",
                        files={"files": (EXAMPLE_XLS.name, file, "application/vnd.ms-excel")},
                    )
                client.put("/api/school", json={"school_name": "另一所大学", "school_code": "00000"})
                response = client.get(f"/api/pipeline/stream?dataset_id={dataset}")
                self.assertEqual(response.status_code, 409)
                self.assertIn("不一致", response.json()["detail"])

    def test_old_api_uses_default_dataset(self):
        with tempfile.TemporaryDirectory(prefix="dataset_default_") as root:
            app = create_app(data_dir=root, allowed_origins=["http://testserver"])
            with TestClient(app) as client:
                client.post("/api/auth/register", json={
                    "username": "tester", "password": "longpassword123", "display_name": "T",
                })
                dataset = client.post("/api/datasets", json={"name": "默认批次", "academic_year": "2026"}).json()["dataset"]["id"]
                client.post(f"/api/datasets/{dataset}/default")
                with EXAMPLE_XLS.open("rb") as file:
                    response = client.post(
                        f"/api/upload?dataset_id={dataset}",
                        files={"files": (EXAMPLE_XLS.name, file, "application/vnd.ms-excel")},
                    )
                self.assertEqual(response.status_code, 200)
                old_api = client.get("/api/tables").json()
                self.assertEqual(old_api["dataset_id"], dataset)
                self.assertEqual(old_api["total_cells"], 15)


if __name__ == "__main__":
    unittest.main()
