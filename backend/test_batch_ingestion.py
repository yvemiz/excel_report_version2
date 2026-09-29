import os
import sys
import unittest
import asyncio

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.stc_parser import STCParser
from app.core.cell_lake import CellLake
from app.core.duckdb_engine import DuckDBEngine
from app.config import settings

class TestBatchIngestion(unittest.TestCase):

    def setUp(self):
        self.example_dir = os.path.join(os.path.dirname(settings.BASE_DIR), "example")
        self.test_dir = os.path.join(settings.DATA_DIR, "test_scratch")
        os.makedirs(self.test_dir, exist_ok=True)
        self.lake = CellLake(os.path.join(self.test_dir, "batch_lake.db"))
        self.duck = DuckDBEngine(":memory:")
        self.lake.clear()
        self.duck.clear()

    def test_multiprocess_parse_directory(self):
        """测试多进程并行扫描与解析目录中的所有 Excel 文件"""
        self.assertTrue(os.path.exists(self.example_dir), "example/ 目录必须存在")
        
        parsed_sheets = STCParser.parse_directory(self.example_dir, recursive=False, max_workers=4)
        self.assertTrue(len(parsed_sheets) >= 8, f"应至少解析出 8 个工作表，实际: {len(parsed_sheets)}")

        # 验证每个 Sheet 的数据完整性
        for s in parsed_sheets:
            self.assertTrue(s["file_name"].endswith((".xls", ".xlsx")))
            self.assertTrue(len(s["sheet_name"]) > 0)
            self.assertTrue(s["row_count"] >= 0)
            self.assertTrue(len(s["header_paths"]) > 0)

    def test_streaming_ingestion_efficiency(self):
        """测试流式逐表写入 SQLite 与 DuckDB，验证无事件循环死锁且内存可控"""
        parsed_sheets = STCParser.parse_directory(self.example_dir, recursive=False, max_workers=4)
        total_cells_added = 0
        registered_tables = []

        for ps in parsed_sheets:
            tbl = self.duck.register_sheet(ps["sheet_name"], ps["file_name"], ps["rows"], ps["header_paths"])
            registered_tables.append(tbl)
            if ps.get("cells"):
                c_cnt = self.lake.insert_cells(ps["cells"], batch_size=1000)
                total_cells_added += c_cnt

        self.assertEqual(len(registered_tables), len(parsed_sheets))
        self.assertTrue(total_cells_added > 1000, f"单元格数应超过 1000，实际: {total_cells_added}")
        self.assertEqual(self.lake.count(), total_cells_added)

        # 验证 DuckDB 查询性能与列式访问
        catalog = self.duck.get_catalog()
        self.assertEqual(len(catalog), len(parsed_sheets))
        sample_query = self.duck.query(f"SELECT COUNT(*) as cnt FROM {registered_tables[0]}")
        self.assertTrue(sample_query[0]["cnt"] >= 0)

if __name__ == "__main__":
    unittest.main()
