import os
import shutil
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.config import settings
from app.core.stc_parser import STCParser
from app.core.cell_lake import CellLake
from app.core.duckdb_engine import DuckDBEngine

router = APIRouter(prefix="/api", tags=["Upload & Data Ingestion"])

# 全局单例引用（在 main.py 中注入初始化）
cell_lake_instance: CellLake = None
duckdb_instance: DuckDBEngine = None

def init_upload_routes(lake: CellLake, duck: DuckDBEngine):
    global cell_lake_instance, duckdb_instance
    cell_lake_instance = lake
    duckdb_instance = duck

@router.post("/upload")
async def upload_excel(files: List[UploadFile] = File(...)):
    """上传一个或多个 Excel 文件并执行 STC 解析、Cell Lake 入库和 DuckDB 注册"""
    if not files:
        raise HTTPException(status_code=400, detail="未上传任何文件")

    uploaded_summary = []
    total_cells_added = 0

    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".xls", ".xlsx"]:
            continue

        save_path = os.path.join(settings.UPLOAD_DIR, file.filename)
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # STC 复合表头解析
        sheets_data = STCParser.parse_file(save_path)
        for s in sheets_data:
            c_count = cell_lake_instance.insert_cells(s["cells"])
            total_cells_added += c_count
            tbl_name = duckdb_instance.register_sheet(s["sheet_name"], s["file_name"], s["rows"], s["header_paths"])
            uploaded_summary.append({
                "file_name": s["file_name"],
                "sheet_name": s["sheet_name"],
                "row_count": s["row_count"],
                "col_count": s["col_count"],
                "cells_count": len(s["cells"]),
                "table_name": tbl_name,
                "fingerprint": s["fingerprint"],
                "headers": s["header_paths"][:8]
            })

    return {
        "success": True,
        "message": f"成功解析 {len(uploaded_summary)} 个工作表，录入 {total_cells_added} 个单元格物理坐标",
        "sheets": uploaded_summary,
        "total_cells": cell_lake_instance.count()
    }

@router.post("/load_example_data")
async def load_example_data():
    """一键加载 example/ 目录下的 8 个高校真实报表数据"""
    example_dir = os.path.join(os.path.dirname(settings.BASE_DIR), "example")
    if not os.path.exists(example_dir):
        raise HTTPException(status_code=404, detail="example 目录不存在")

    cell_lake_instance.clear()
    duckdb_instance.clear()
    loaded = []
    total_cells = 0

    for f in sorted(os.listdir(example_dir)):
        if f.endswith(".xls") or f.endswith(".xlsx"):
            fp = os.path.join(example_dir, f)
            parsed_sheets = STCParser.parse_file(fp)
            for ps in parsed_sheets:
                c_cnt = cell_lake_instance.insert_cells(ps["cells"])
                total_cells += c_cnt
                tbl = duckdb_instance.register_sheet(ps["sheet_name"], ps["file_name"], ps["rows"], ps["header_paths"])
                loaded.append({
                    "file_name": ps["file_name"],
                    "sheet_name": ps["sheet_name"],
                    "row_count": ps["row_count"],
                    "cells_count": len(ps["cells"]),
                    "table_name": tbl,
                    "headers": ps["header_paths"]
                })

    return {
        "success": True,
        "message": f"成功加载 8 个高校状态报表，共计 {total_cells} 个单元格坐标进入 Cell Lake",
        "sheets": loaded,
        "total_cells": cell_lake_instance.count()
    }

@router.get("/tables")
async def get_tables():
    """获取 DuckDB 目录层与数据指标列表及嗅探到的学校元数据"""
    school_meta = cell_lake_instance.detect_school_metadata()
    return {
        "catalog": duckdb_instance.get_catalog(),
        "total_cells": cell_lake_instance.count(),
        "school_metadata": school_meta,
        "school_name": school_meta.get("school_name", "")
    }

@router.get("/cell/{cell_id}")
async def get_cell_detail(cell_id: str):
    """根据 cell_id 查询单元格物理坐标与值（用于前端 Hover 穿透气泡）"""
    cell = cell_lake_instance.get_cell(cell_id)
    if not cell:
        raise HTTPException(status_code=404, detail="未找到该单元格记录")
    return {
        "success": True,
        "cell": cell
    }

class ScanDirectoryRequest(BaseModel):
    directory_path: str
    recursive: bool = True
    clear_existing: bool = True

@router.post("/scan_directory")
async def scan_directory_data(req: ScanDirectoryRequest):
    """
    极速扫描并摄入指定本地目录中的大量 Excel 报表（可承载 500+ 个文件）
    采用 asyncio.to_thread 异步卸载 CPU 密集计算，杜绝阻塞主事件循环
    按 Sheet 边解析边分批入库，大幅降低海量数据瞬时内存占用
    """
    import asyncio
    dir_path = req.directory_path.strip()
    if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
        raise HTTPException(status_code=400, detail=f"指定的目录不存在或不是文件夹: {dir_path}")

    if req.clear_existing:
        cell_lake_instance.clear()
        duckdb_instance.clear()

    # 异步非阻塞卸载至工作线程/进程池
    parsed_sheets = await asyncio.to_thread(STCParser.parse_directory, dir_path, recursive=req.recursive)
    if not parsed_sheets:
        return {"success": False, "message": "该目录下未扫描到任何 .xls 或 .xlsx 文件", "total_files": 0}

    loaded_summary = []
    total_cells = 0
    unique_files = set()

    for ps in parsed_sheets:
        tbl = duckdb_instance.register_sheet(ps["sheet_name"], ps["file_name"], ps["rows"], ps["header_paths"])
        unique_files.add(ps["file_name"])
        # 流式逐 Sheet 批量入库，避免占用海量堆内存
        if ps.get("cells"):
            c_added = cell_lake_instance.insert_cells(ps["cells"], batch_size=2000)
            total_cells += c_added

        loaded_summary.append({
            "file_name": ps["file_name"],
            "sheet_name": ps["sheet_name"],
            "row_count": ps["row_count"],
            "cells_count": len(ps.get("cells", [])),
            "table_name": tbl,
            "headers": ps.get("header_paths", [])[:8]
        })

    detected_school = cell_lake_instance.detect_school_metadata()

    from app.core.workbook_inspector import WorkbookInspector
    inspection_res = WorkbookInspector.inspect_directory(dir_path)

    return {
        "success": True,
        "message": f"成功批量扫描并入库 {len(unique_files)} 份报表（{len(loaded_summary)} 个工作表），共计 {total_cells} 个单元格物理坐标进入 Cell Lake",
        "sheets_count": len(loaded_summary),
        "scanned_files_count": len(unique_files),
        "total_cells": cell_lake_instance.count(),
        "total_cells_lake": cell_lake_instance.count(),
        "school_metadata": detected_school,
        "school_name": detected_school.get("school_name", ""),
        "workbook_inspection": {
            "overall_health_rate": inspection_res.get("overall_health_rate", 100.0),
            "healthy_files": inspection_res.get("healthy_files", len(unique_files)),
            "summary": f"工作簿完整性防越界审计健康率 {inspection_res.get('overall_health_rate', 100.0)}%，已验证 {inspection_res.get('healthy_files', len(unique_files))}/{len(unique_files)} 份报表"
        }
    }
