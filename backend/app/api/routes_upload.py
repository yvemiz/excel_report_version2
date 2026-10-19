import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from app.config import settings
from app.core.stc_parser import STCParser
from app.core.workspaces import Workspace, get_workspace, get_mutable_workspace

router = APIRouter(prefix="/api", tags=["Upload & Data Ingestion"])

def validate_import_path(path, workspace: Workspace, dataset=None):
    resolved = Path(path).resolve()
    allowed_upload = dataset.upload_dir.resolve() if dataset is not None else workspace.upload_dir.resolve()
    if resolved.is_relative_to(allowed_upload):
        return
    if resolved.is_relative_to(workspace.data_root) or workspace.data_root.is_relative_to(resolved):
        raise HTTPException(status_code=403, detail="不能导入系统数据目录或其他账号的文件，请使用独立的报表文件夹")


@router.post("/upload")
async def upload_excel(files: List[UploadFile] = File(...), dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_mutable_workspace)):
    """上传一个或多个 Excel 文件并执行 STC 解析、Cell Lake 入库和 DuckDB 注册"""
    if not files:
        raise HTTPException(status_code=400, detail="未上传任何文件")
    dataset = workspace.dataset(dataset_id)
    cell_lake_instance, duckdb_instance = dataset.cell_lake, dataset.duckdb

    uploaded_summary = []
    total_cells_added = 0

    for file in files:
        filename = file.filename or ""
        if not filename or filename != Path(filename.replace("\\", "/")).name or "\x00" in filename:
            raise HTTPException(status_code=400, detail="文件名无效")
        ext = os.path.splitext(filename)[1].lower()
        if ext not in [".xls", ".xlsx"]:
            continue

        save_path = dataset.upload_dir / filename
        if save_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"当前数据集已存在同名文件“{filename}”，请先删除旧文件或改用新的批次数据集",
            )
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # STC 复合表头解析
        sheets_data = STCParser.parse_file(save_path)
        if sheets_data:
            dataset.mark_data_changed()
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
        "total_cells": cell_lake_instance.count(),
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.dataset.get("name", ""),
    }

@router.post("/load_example_data")
async def load_example_data(workspace: Workspace = Depends(get_mutable_workspace)):
    """一键加载 example/ 目录下的 8 个高校真实报表数据"""
    example_dir = os.path.join(os.path.dirname(settings.BASE_DIR), "example")
    demo = workspace.ensure_demo_dataset()
    dataset = workspace.dataset(demo["id"])
    cell_lake_instance, duckdb_instance = dataset.cell_lake, dataset.duckdb
    if not os.path.exists(example_dir):
        raise HTTPException(status_code=404, detail="example 目录不存在")

    dataset.mark_data_changed()
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
        "total_cells": cell_lake_instance.count(),
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.dataset.get("name", ""),
    }

@router.get("/tables")
async def get_tables(dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_workspace)):
    """获取 DuckDB 目录层与数据指标列表及嗅探到的学校元数据"""
    dataset = workspace.dataset(dataset_id)
    cell_lake_instance, duckdb_instance = dataset.cell_lake, dataset.duckdb
    school_meta = cell_lake_instance.detect_school_metadata()
    cell_counts = {
        (item["file_name"], item["sheet_name"]): item["cell_count"]
        for item in cell_lake_instance.get_tables_summary()
    }
    return {
        "catalog": [
            {**item, "cells_count": cell_counts.get((item["file_name"], item["sheet_name"]), 0)}
            for item in duckdb_instance.get_catalog()
        ],
        "total_cells": cell_lake_instance.count(),
        "school_metadata": school_meta,
        "school_name": school_meta.get("school_name", ""),
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.dataset.get("name", ""),
        "current_revision": dataset.dataset.get("current_revision", 1),
    }

@router.delete("/tables")
def clear_tables(dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_mutable_workspace)):
    """清空当前数据集入库数据，不删除账号、模型配置或已生成报告。"""
    return workspace.delete_data(dataset_id=dataset_id)


@router.delete("/tables/{table_name}")
def delete_table(table_name: str, dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_mutable_workspace)):
    """删除当前数据集中的单个工作表及其来源单元格。"""
    return workspace.delete_data(table_name, dataset_id=dataset_id)

@router.get("/cell/{cell_id}")
async def get_cell_detail(cell_id: str, dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_workspace)):
    """根据 cell_id 查询单元格物理坐标与值（用于前端 Hover 穿透气泡）"""
    dataset = workspace.dataset(dataset_id)
    cell = dataset.cell_lake.get_cell(cell_id)
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
    dataset_id: Optional[str] = None

@router.post("/scan_directory")
async def scan_directory_data(req: ScanDirectoryRequest, workspace: Workspace = Depends(get_mutable_workspace)):
    """
    极速扫描并摄入指定本地目录中的大量 Excel 报表（可承载 500+ 个文件）
    采用 asyncio.to_thread 异步卸载 CPU 密集计算，杜绝阻塞主事件循环
    按 Sheet 边解析边分批入库，大幅降低海量数据瞬时内存占用
    """
    import asyncio
    dir_path = req.directory_path.strip()
    dataset = workspace.dataset(req.dataset_id)
    cell_lake_instance, duckdb_instance = dataset.cell_lake, dataset.duckdb
    if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
        raise HTTPException(status_code=400, detail=f"指定的目录不存在或不是文件夹: {dir_path}")

    validate_import_path(dir_path, workspace, dataset)
    parsed_sheets = await asyncio.to_thread(
        STCParser.parse_directory, dir_path, recursive=req.recursive,
        file_validator=lambda path: validate_import_path(path, workspace, dataset),
    )
    if parsed_sheets and not req.clear_existing:
        existing = {(item["file_name"], item["sheet_name"]) for item in cell_lake_instance.get_tables_summary()}
        conflicts = [
            f"{item['file_name']} / {item['sheet_name']}"
            for item in parsed_sheets if (item["file_name"], item["sheet_name"]) in existing
        ]
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail="当前数据集已存在同名工作表，请先清空数据或改用新的批次数据集：" + "、".join(conflicts[:5]),
            )
    if not parsed_sheets:
        return {"success": False, "message": "该目录下未扫描到任何 .xls 或 .xlsx 文件", "total_files": 0}
    dataset.mark_data_changed()
    if req.clear_existing:
        cell_lake_instance.clear()
        duckdb_instance.clear()

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
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.dataset.get("name", ""),
        "current_revision": dataset.dataset.get("current_revision", 1),
        "workbook_inspection": {
            "overall_health_rate": inspection_res.get("overall_health_rate", 100.0),
            "healthy_files": inspection_res.get("healthy_files", len(unique_files)),
            "summary": f"工作簿完整性防越界审计健康率 {inspection_res.get('overall_health_rate', 100.0)}%，已验证 {inspection_res.get('healthy_files', len(unique_files))}/{len(unique_files)} 份报表"
        }
    }
