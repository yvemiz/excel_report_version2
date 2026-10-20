import asyncio
import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query

from app.config import settings
from app.core.stc_parser import STCParser, STCParseError
from app.core.workspaces import Workspace, get_workspace, get_mutable_workspace

router = APIRouter(prefix="/api", tags=["Upload & Data Ingestion"])


def validate_import_path(path, workspace: Workspace, dataset=None):
    resolved = Path(path).resolve()
    allowed_upload = dataset.upload_dir.resolve() if dataset is not None else workspace.upload_dir.resolve()
    if resolved.is_relative_to(allowed_upload):
        return
    if resolved.is_relative_to(workspace.data_root) or workspace.data_root.is_relative_to(resolved):
        raise HTTPException(status_code=403, detail="不能导入系统数据目录或其他账号的文件，请使用独立的报表文件夹")


def _hash_path(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _new_source_file_id() -> str:
    return f"sf_{uuid.uuid4().hex}"


def _record_for_path(
    path: Path,
    original_name: str,
    storage_mode: str,
    import_id: str,
    stored_rel_path: str = "",
) -> Dict[str, Any]:
    content_hash, size = _hash_path(path)
    return {
        "source_file_id": _new_source_file_id(),
        "original_name": original_name,
        "storage_mode": storage_mode,
        "stored_rel_path": stored_rel_path,
        "original_path": str(path.resolve()),
        "parse_path": str(path.resolve()),
        "content_hash": content_hash,
        "size_bytes": size,
        "import_id": import_id,
    }


def _sheets_response(parsed_sheets: List[Dict[str, Any]], files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from app.core.duckdb_engine import DuckDBEngine

    by_path = {Path(item["parse_path"]).resolve(): item for item in files}
    result = []
    for sheet in parsed_sheets:
        source = by_path.get(Path(sheet["file_path"]).resolve())
        source_file_id = source["source_file_id"] if source else ""
        result.append({
            "file_name": source["original_name"] if source else sheet["file_name"],
            "sheet_name": sheet["sheet_name"],
            "row_count": sheet["row_count"],
            "col_count": sheet.get("col_count", 0),
            "cells_count": len(sheet.get("cells", [])),
            "table_name": DuckDBEngine.table_name_for(source_file_id, sheet["sheet_name"]) if source_file_id else "",
            "source_file_id": source_file_id,
            "fingerprint": sheet.get("fingerprint", ""),
            "headers": sheet.get("header_paths", [])[:8],
        })
    return result


@router.post("/upload")
async def upload_excel(
    files: List[UploadFile] = File(...),
    dataset_id: Optional[str] = Query(None),
    workspace: Workspace = Depends(get_mutable_workspace),
):
    """上传 Excel 并原子导入；解析或写库失败时保持原数据和修订号不变。"""
    if not files:
        raise HTTPException(status_code=400, detail="未上传任何文件")
    dataset = workspace.dataset(dataset_id)
    dataset.assert_writable("导入数据")

    accepted: List[tuple[UploadFile, str]] = []
    seen_names = set()
    for file in files:
        filename = file.filename or ""
        if not filename or filename != Path(filename.replace("\\", "/")).name or "\x00" in filename:
            raise HTTPException(status_code=400, detail="文件名无效")
        ext = Path(filename).suffix.lower()
        if ext not in {".xls", ".xlsx"}:
            continue
        if filename in seen_names:
            raise HTTPException(status_code=409, detail=f"本次上传包含同名文件“{filename}”")
        if dataset.has_source_file(filename):
            raise HTTPException(
                status_code=409,
                detail=f"当前批次已存在同名文件“{filename}”，请先删除旧文件或改用新的批次",
            )
        seen_names.add(filename)
        accepted.append((file, filename))
    if not accepted:
        raise HTTPException(status_code=400, detail="请选择 .xls 或 .xlsx 格式的 Excel 文件")

    import_id = dataset.begin_import("upload", len(accepted))
    incoming_dir = dataset.imports_dir / import_id / "incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    parsed_sheets: List[Dict[str, Any]] = []
    records: List[Dict[str, Any]] = []
    try:
        for index, (file, filename) in enumerate(accepted):
            suffix = Path(filename).suffix.lower()
            temp_path = incoming_dir / f"{index}_{uuid.uuid4().hex}{suffix}"
            digest = hashlib.sha256()
            size = 0
            with temp_path.open("wb") as output:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                    output.write(chunk)
            if size == 0:
                raise ValueError(f"文件“{filename}”为空")
            try:
                sheets = STCParser.parse_file(str(temp_path))
            except Exception as exc:
                raise ValueError(f"文件“{filename}”解析失败：{exc}") from exc
            if not sheets:
                raise ValueError(f"文件“{filename}”没有可导入的工作表")
            for sheet in sheets:
                sheet["file_name"] = filename
            parsed_sheets.extend(sheets)
            records.append({
                "source_file_id": _new_source_file_id(),
                "original_name": filename,
                "storage_mode": "upload",
                "stored_rel_path": "",
                "original_path": str(temp_path),
                "parse_path": str(temp_path),
                "content_hash": digest.hexdigest(),
                "size_bytes": size,
                "temp_path": str(temp_path),
                "import_id": import_id,
            })
        for record in records:
            record["stored_rel_path"] = str(
                Path("uploads") / record["source_file_id"] / record["original_name"]
            )
            # 上传副本就是该来源文件的规范存储位置，不保留已删除的临时路径。
            record["original_path"] = ""
        result = dataset.commit_import(import_id, parsed_sheets, records, replace_existing=False)
        return {
            "success": True,
            "message": f"成功解析 {len(parsed_sheets)} 个工作表，录入 {result['cell_count']} 个单元格物理坐标",
            "sheets": _sheets_response(parsed_sheets, records),
            "total_cells": dataset.cell_lake.count(),
            "dataset_id": dataset.dataset_id,
            "dataset_name": dataset.dataset.get("name", ""),
            "import_id": result["import_id"],
            "current_revision": result["current_revision"],
        }
    except HTTPException:
        dataset.fail_import(import_id, "上传校验失败")
        shutil.rmtree(dataset.imports_dir / import_id, ignore_errors=True)
        raise
    except Exception as exc:
        dataset.fail_import(import_id, str(exc))
        shutil.rmtree(dataset.imports_dir / import_id, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"导入失败，原数据未改变：{exc}") from exc


@router.post("/load_example_data")
async def load_example_data(workspace: Workspace = Depends(get_mutable_workspace)):
    """在原示例批次中原子替换示例数据，不影响正式批次。"""
    example_dir = Path(settings.BASE_DIR).parent / "example"
    if not example_dir.exists():
        raise HTTPException(status_code=404, detail="example 目录不存在")
    example_files = sorted(
        path for path in example_dir.iterdir() if path.suffix.lower() in {".xls", ".xlsx"}
    )
    if not example_files:
        raise HTTPException(status_code=404, detail="example 目录中没有 Excel 报表")

    demo = workspace.ensure_demo_dataset()
    dataset = workspace.dataset(demo["id"])
    dataset.assert_writable("导入示例数据")
    import_id = dataset.begin_import("example", len(example_files))
    parsed_sheets: List[Dict[str, Any]] = []
    records: List[Dict[str, Any]] = []
    try:
        for path in example_files:
            sheets = STCParser.parse_file(str(path))
            if not sheets:
                raise ValueError(f"示例文件“{path.name}”没有可导入的工作表")
            parsed_sheets.extend(sheets)
            records.append(_record_for_path(path, path.name, "example", import_id))
        result = dataset.commit_import(import_id, parsed_sheets, records, replace_existing=True)
        return {
            "success": True,
            "message": f"成功加载 {len(records)} 份示例报表，共计 {result['cell_count']} 个单元格坐标进入 Cell Lake",
            "sheets": _sheets_response(parsed_sheets, records),
            "total_cells": dataset.cell_lake.count(),
            "dataset_id": dataset.dataset_id,
            "dataset_name": dataset.dataset.get("name", ""),
            "import_id": result["import_id"],
            "current_revision": result["current_revision"],
        }
    except Exception as exc:
        dataset.fail_import(import_id, str(exc))
        raise HTTPException(status_code=500, detail=f"示例数据导入失败，原数据未改变：{exc}") from exc


@router.get("/tables")
async def get_tables(dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_workspace)):
    """获取当前数据集的工作表目录和学校元数据。"""
    dataset = workspace.dataset(dataset_id)
    school_meta = dataset.cell_lake.detect_school_metadata()
    cell_counts = {
        (item["file_name"], item["sheet_name"], item.get("source_file_id") or ""): item["cell_count"]
        for item in dataset.cell_lake.get_tables_summary()
    }
    catalog = []
    for item in dataset.duckdb.get_catalog():
        source_file_id = item.get("source_file_id", "")
        catalog.append({
            **item,
            "cells_count": cell_counts.get(
                (item["file_name"], item["sheet_name"], source_file_id), 0
            ),
        })
    return {
        "catalog": catalog,
        "total_cells": dataset.cell_lake.count(),
        "school_metadata": school_meta,
        "school_name": school_meta.get("school_name", ""),
        "dataset_id": dataset.dataset_id,
        "dataset_name": dataset.dataset.get("name", ""),
        "dataset_kind": dataset.kind,
        "current_revision": dataset.dataset.get("current_revision", 1),
        "read_only": dataset.read_only,
        "is_demo": dataset.kind == "demo",
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
    dataset = workspace.dataset(dataset_id)
    cell = dataset.cell_lake.get_cell(cell_id)
    if not cell:
        raise HTTPException(status_code=404, detail="未找到该单元格记录")
    return {"success": True, "cell": cell}


class ScanDirectoryRequest(BaseModel):
    directory_path: str
    recursive: bool = True
    clear_existing: bool = True
    dataset_id: Optional[str] = None


@router.post("/scan_directory")
async def scan_directory_data(req: ScanDirectoryRequest, workspace: Workspace = Depends(get_mutable_workspace)):
    """严格扫描目录并原子导入；任意文件解析失败时原数据保持不变。"""
    dir_path = req.directory_path.strip()
    dataset = workspace.dataset(req.dataset_id)
    dataset.assert_writable("导入目录数据")
    if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
        raise HTTPException(status_code=400, detail=f"指定的目录不存在或不是文件夹: {dir_path}")
    validate_import_path(dir_path, workspace, dataset)

    import_id = dataset.begin_import("scan", 0)
    try:
        parsed_sheets = await asyncio.to_thread(
            STCParser.parse_directory,
            dir_path,
            recursive=req.recursive,
            file_validator=lambda path: validate_import_path(path, workspace, dataset),
            strict=True,
        )
        if not parsed_sheets:
            dataset.fail_import(import_id, "该目录下未扫描到任何可导入的 Excel 文件")
            return {"success": False, "message": "该目录下未扫描到任何可导入的 Excel 文件", "total_files": 0}

        by_path: Dict[Path, Dict[str, Any]] = {}
        records: List[Dict[str, Any]] = []
        for sheet in parsed_sheets:
            path = Path(sheet["file_path"]).resolve()
            if path in by_path:
                continue
            record = _record_for_path(path, path.name, "scan", import_id)
            by_path[path] = record
            records.append(record)
        result = dataset.commit_import(
            import_id,
            parsed_sheets,
            records,
            replace_existing=req.clear_existing,
        )
        school_meta = dataset.cell_lake.detect_school_metadata()
        try:
            from app.core.workbook_inspector import WorkbookInspector
            inspection = WorkbookInspector.inspect_directory(dir_path)
        except Exception:
            inspection = {}
        return {
            "success": True,
            "message": f"成功批量导入 {len(records)} 份报表（{len(parsed_sheets)} 个工作表），共计 {result['cell_count']} 个单元格",
            "sheets_count": len(parsed_sheets),
            "scanned_files_count": len(records),
            "total_cells": dataset.cell_lake.count(),
            "total_cells_lake": dataset.cell_lake.count(),
            "school_metadata": school_meta,
            "school_name": school_meta.get("school_name", ""),
            "dataset_id": dataset.dataset_id,
            "dataset_name": dataset.dataset.get("name", ""),
            "current_revision": result["current_revision"],
            "import_id": result["import_id"],
            "workbook_inspection": {
                "overall_health_rate": inspection.get("overall_health_rate", 100.0),
                "healthy_files": inspection.get("healthy_files", len(records)),
                "summary": inspection.get("summary", ""),
            },
        }
    except HTTPException as exc:
        dataset.fail_import(import_id, str(exc.detail))
        shutil.rmtree(dataset.imports_dir / import_id, ignore_errors=True)
        raise
    except STCParseError as exc:
        dataset.fail_import(import_id, str(exc))
        shutil.rmtree(dataset.imports_dir / import_id, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"目录导入失败，原数据未改变：{exc}") from exc
    except Exception as exc:
        dataset.fail_import(import_id, str(exc))
        shutil.rmtree(dataset.imports_dir / import_id, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"目录导入失败，原数据未改变：{exc}") from exc
