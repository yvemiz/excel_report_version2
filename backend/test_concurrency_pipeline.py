import asyncio
import os
import sys
import unittest
import threading
import json

# 加入搜索路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.cell_lake import CellLake
from app.core.audit_service import AuditService
from app.core.chart_service import ChartService
from app.core.duckdb_engine import DuckDBEngine
from app.core.docx_exporter import DocxExporter
from app.core.excel_exporter import ExcelExporter
from app.pipeline.agent_runner import PiAgentRunner
from app.pipeline.jev_judge import JevJudge
from app.pipeline.stages import ReportPipeline
from app.config import settings

class TestConcurrencyAndAuditFixes(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.test_dir = os.path.join(settings.DATA_DIR, "test_scratch")
        os.makedirs(self.test_dir, exist_ok=True)
        self.lake_db = os.path.join(self.test_dir, "test_cell_lake.db")
        self.duck_db = ":memory:"
        self.charts_dir = os.path.join(self.test_dir, "charts")
        self.exports_dir = os.path.join(self.test_dir, "exports")

        self.cell_lake = CellLake(self.lake_db)
        self.duckdb_engine = DuckDBEngine(self.duck_db)
        self.chart_service = ChartService(self.charts_dir)
        self.audit_service = AuditService(self.cell_lake)
        self.docx_exporter = DocxExporter(self.exports_dir)
        self.excel_exporter = ExcelExporter(self.exports_dir)
        self.agent_runner = PiAgentRunner(self.chart_service)
        self.jev_judge = JevJudge()

        # 录入基准测试单元格
        self.cell_lake.clear()
        self.cell_lake.insert_cells([
            {
                "cell_id": "cell_num_1",
                "file_name": "test1.xlsx",
                "sheet_name": "Sheet1",
                "row_idx": 1,
                "col_idx": 1,
                "cell_ref": "A1",
                "metric_path": "学校规模 > 教师人数",
                "raw_value": "1",
                "numeric_value": 1.0
            },
            {
                "cell_id": "cell_num_0",
                "file_name": "test1.xlsx",
                "sheet_name": "Sheet1",
                "row_idx": 2,
                "col_idx": 1,
                "cell_ref": "A2",
                "metric_path": "学校规模 > 违规通报",
                "raw_value": "0",
                "numeric_value": 0.0
            },
            {
                "cell_id": "cell_faculty",
                "file_name": "test1.xlsx",
                "sheet_name": "Sheet1",
                "row_idx": 3,
                "col_idx": 1,
                "cell_ref": "A3",
                "metric_path": "师资队伍 > 专任教师",
                "raw_value": "1200",
                "numeric_value": 1200.0
            },
            {
                "cell_id": "cell_text_school",
                "file_name": "test1.xlsx",
                "sheet_name": "Sheet1",
                "row_idx": 4,
                "col_idx": 1,
                "cell_ref": "A4",
                "metric_path": "学校概况 > 学校名称",
                "raw_value": "海南师范大学",
                "numeric_value": None
            }
        ])

    def test_audit_false_positive_elimination(self):
        """验证严格数值与文本对齐算法，确保'1'与'1000'、'0'与'50'被严格拒绝"""
        # 1. 曾经的严重漏洞：大模型幻觉出 1000，但单元格只有 1 -> 必须拒绝
        hallucinated_text = "学校专任教师达到 [1000人][^cell_num_1]，表现极其优越。"
        res = self.audit_service.verify_markdown_text(hallucinated_text)
        self.assertFalse(res["is_approved"], "幻觉数值 1000 与实际 1 必须判定为未对齐！")
        self.assertEqual(res["mismatch_count"], 1)

        # 2. 曾经的严重漏洞：大模型幻觉出 50，但单元格只有 0 -> 必须拒绝
        hallucinated_zero = "违规事件为 [50起][^cell_num_0]。"
        res_zero = self.audit_service.verify_markdown_text(hallucinated_zero)
        self.assertFalse(res_zero["is_approved"], "幻觉数值 50 与实际 0 必须判定为未对齐！")

        # 3. 正常带单位文本 -> 必须支持且正确对齐
        valid_text = "学校现有专任教师 [1200人][^cell_faculty]，坐落于 [海南师范大学][^cell_text_school]。"
        res_valid = self.audit_service.verify_markdown_text(valid_text)
        self.assertTrue(res_valid["is_approved"], "真实对齐文本必须 100% 吻合！")
        self.assertEqual(res_valid["verified_count"], 2)

    def test_cell_lake_batch_retrieval(self):
        """验证批量反查接口 get_cells_batch 能单次批处理返回"""
        ids = ["cell_num_1", "cell_faculty", "cell_non_existent"]
        cells_map = self.cell_lake.get_cells_batch(ids)
        self.assertEqual(len(cells_map), 2)
        self.assertIn("cell_num_1", cells_map)
        self.assertIn("cell_faculty", cells_map)
        self.assertEqual(cells_map["cell_faculty"]["raw_value"], "1200")

    def test_chart_service_thread_safety(self):
        """验证多线程并发生成学术图表时互斥锁生效，无冲突崩溃"""
        errors = []
        def worker(thread_idx):
            try:
                for i in range(3):
                    self.chart_service.generate_chart(
                        chart_type="bar" if i % 2 == 0 else "pie",
                        title=f"线程_{thread_idx}_测试图表_{i}",
                        labels=["类别A", "类别B", "类别C"],
                        data=[10 + i, 20 + thread_idx, 30]
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"并发生成图表出现异常: {errors}")

    async def test_concurrency_pipeline_and_checkpoint_resume(self):
        """验证流水线异步并发信号量池、检查点完整持久化与断点续生"""
        pipe = ReportPipeline(
            cell_lake=self.cell_lake,
            duckdb_engine=self.duckdb_engine,
            chart_service=self.chart_service,
            audit_service=self.audit_service,
            docx_exporter=self.docx_exporter,
            excel_exporter=self.excel_exporter,
            agent_runner=self.agent_runner,
            jev_judge=self.jev_judge
        )
        pipe.agent_runner.set_agent_mode("python_native")

        # 1. 运行流水线 (并发度 3)
        events = []
        async for ev in pipe.execute_pipeline(school_name="海南师范大学", resume=False, max_concurrency=3):
            events.append(ev)

        self.assertTrue(len(pipe.generated_sections) > 0, "流水线必须成功生成章节")
        first_sec = pipe.generated_sections[0]
        self.assertTrue(len(first_sec["content"]) > 50, "必须生成完整正文内容")

        # 检查检查点文件是否已写入完整 content
        cp_file = os.path.join(settings.DATA_DIR, "checkpoints", "pipeline_checkpoint.json")
        self.assertTrue(os.path.exists(cp_file), "检查点文件必须存在！")
        with open(cp_file, "r", encoding="utf-8") as f:
            cp_json = json.load(f)
            self.assertTrue(len(cp_json["sections"]) > 0)
            self.assertTrue("content" in cp_json["sections"][0])
            self.assertTrue(len(cp_json["sections"][0]["content"]) > 0, "检查点必须保存完整 content！")

        # 2. 模拟断点续生 (resume=True)
        resumed_events = []
        async for ev in pipe.execute_pipeline(school_name="海南师范大学", resume=True, max_concurrency=3):
            resumed_events.append(ev)

        # 确认产生了从检查点恢复的事件
        resumed_chunks = [e for e in resumed_events if e.get("type") == "section_stage" and "断点续生" in e.get("text", "")]
        self.assertTrue(len(resumed_chunks) > 0, "必须成功触发断点续存恢复！")

if __name__ == "__main__":
    unittest.main()
