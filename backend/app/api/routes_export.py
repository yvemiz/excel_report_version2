from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from typing import Optional
from app.core.workspaces import Workspace, get_workspace

router = APIRouter(prefix="/api", tags=["Exports & Assets"])
static_router = APIRouter(prefix="/static", tags=["Private Charts"])

@router.get("/exports/{filename}")
async def download_export_file(filename: str, dataset_id: Optional[str] = Query(None), workspace: Workspace = Depends(get_workspace)):
    """下载当前数据集最新报告版本的 Word (.docx) 或 Excel 对账表 (.xlsx)"""
    report = workspace.dataset(dataset_id).latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="当前数据集还没有报告版本")
    return FileResponse(report.artifact_path(filename), filename=filename)

@router.get("/reports/{report_version_id}/exports/{filename}")
async def download_report_artifact(report_version_id: str, filename: str, workspace: Workspace = Depends(get_workspace)):
    """下载指定报告版本的 Word 或 Excel 产物，不依赖当前数据集选择。"""
    report = workspace.report(report_version_id)
    return FileResponse(report.artifact_path(filename), filename=filename)

@router.get("/assets/charts/{filename}")
@static_router.get("/charts/{filename}")
async def get_chart_image(filename: str, workspace: Workspace = Depends(get_workspace)):
    """获取生成的 300DPI 统计图表 PNG 图像"""
    file_path = (workspace.chart_dir / filename).resolve()
    if file_path.parent != workspace.chart_dir.resolve() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="图表文件不存在")
    return FileResponse(file_path, media_type="image/png")
