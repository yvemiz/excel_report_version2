import os
from app.config import settings
from app.core.stc_parser import STCParser
from app.core.cell_lake import CellLake
from app.core.duckdb_engine import DuckDBEngine
from app.core.chart_service import ChartService
from app.core.audit_service import AuditService

def test_core_pipeline():
    print("=== Testing Core Data Engine ===")
    example_dir = r"d:\vs_project\excel_report\example"
    
    cell_lake = CellLake(settings.SQLITE_PATH)
    cell_lake.clear()
    duckdb_engine = DuckDBEngine()
    chart_service = ChartService(settings.CHARTS_DIR)
    
    total_cells = 0
    total_sheets = 0
    
    for f in sorted(os.listdir(example_dir)):
        if f.endswith(".xls") or f.endswith(".xlsx"):
            fp = os.path.join(example_dir, f)
            parsed_sheets = STCParser.parse_file(fp)
            for ps in parsed_sheets:
                total_sheets += 1
                c_count = cell_lake.insert_cells(ps["cells"])
                total_cells += c_count
                tbl = duckdb_engine.register_sheet(ps["sheet_name"], ps["file_name"], ps["rows"], ps["header_paths"])
                print(f"Loaded {f} -> Sheet [{ps['sheet_name']}] | Cells: {len(ps['cells'])} | Table: {tbl}")
                
    print(f"\nTotal Sheets Loaded: {total_sheets}, Total Cells in Lake: {cell_lake.count()}")
    
    # 测试 DuckDB 聚合查询 (比如表 1-4-1 专业门类统计)
    catalog = duckdb_engine.get_catalog()
    print(f"Catalog Tables: {[t['table_name'] for t in catalog]}")
    
    majors_tbl = [t['table_name'] for t in catalog if "1_4_1" in t['table_name']]
    if majors_tbl:
        tbl_name = majors_tbl[0]
        # 查询各学院专业数分布
        res = duckdb_engine.query(f"SELECT 所属单位名称, count(*) as cnt FROM {tbl_name} GROUP BY 所属单位名称 ORDER BY cnt DESC LIMIT 6")
        print(f"\nMajors per Dept Query Result:\n{res}")
        
        # 测试 ChartService 生成图表
        labels = [r["所属单位名称"] for r in res]
        data = [float(r["cnt"]) for r in res]
        chart_res = chart_service.generate_chart("bar", "各学院设置本科专业数量分布", labels, data, series_name="专业数", y_label="数量(个)")
        print(f"Generated Chart: {chart_res['url']}")
        
    print("\n=== Phase 1 Core Test Finished Successfully! ===")

if __name__ == "__main__":
    test_core_pipeline()
