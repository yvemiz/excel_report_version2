import os
import unittest
from app.config import settings
from app.core.cell_lake import CellLake
from app.core.duckdb_engine import DuckDBEngine
from app.core.chart_service import ChartService
from app.core.audit_service import AuditService
from app.core.docx_exporter import DocxExporter
from app.core.excel_exporter import ExcelExporter
from app.pipeline.agent_runner import PiAgentRunner
from app.pipeline.jev_judge import JevJudge
from app.pipeline.stages import ReportPipeline

class TestDynamicOutline(unittest.TestCase):
    def setUp(self):
        self.cell_lake = CellLake(settings.SQLITE_PATH)
        self.duckdb_engine = DuckDBEngine(settings.DUCKDB_PATH)
        self.chart_service = ChartService(settings.CHARTS_DIR)
        self.pipeline = ReportPipeline(
            cell_lake=self.cell_lake,
            duckdb_engine=self.duckdb_engine,
            chart_service=self.chart_service,
            audit_service=AuditService(self.cell_lake),
            docx_exporter=DocxExporter(settings.EXPORTS_DIR),
            excel_exporter=ExcelExporter(settings.EXPORTS_DIR),
            agent_runner=PiAgentRunner(self.chart_service),
            jev_judge=JevJudge()
        )

    def test_dynamic_outline_adaptation(self):
        # 1. 验证基础 8 张表的动态大纲生成
        outline = self.pipeline.plan_outline()
        self.assertGreaterEqual(len(outline), 5)
        print(f"[✓] 基础表格生成了 {len(outline)} 个章节")

        # 2. 模拟用户新上传了《2024年科研创新与经费统计.xlsx》
        custom_catalog = self.duckdb_engine.get_catalog() + [
            {
                "table_name": "tbl_2024年科研创新与经费统计",
                "file_name": "2024年科研创新与经费统计.xlsx",
                "sheet_name": "经费明细",
                "row_count": 28,
                "columns": ["所属学科门类", "立项课题数", "国家级重大专项", "到账经费万元"]
            }
        ]
        
        dynamic_sections = self.pipeline._generate_dynamic_sections(custom_catalog)
        self.assertEqual(len(dynamic_sections), len(outline) + 1)
        
        new_sec = dynamic_sections[-1]
        print(f"[✓] 动态追加全新自定义章节: {new_sec['chapter_title']}")
        print(f"    - 小节标题: {new_sec['section_title']}")
        print(f"    - 绑定文件: {new_sec['file_name']}")
        
        self.assertIn("科研创新与经费", new_sec['chapter_title'])
        self.assertEqual(new_sec['file_name'], "2024年科研创新与经费统计.xlsx")

if __name__ == "__main__":
    unittest.main()
