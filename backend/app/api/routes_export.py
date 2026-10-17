from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from app.core.workspaces import Workspace, get_workspace

router = APIRouter(prefix="/api", tags=["Exports & Assets"])
static_router = APIRouter(prefix="/static", tags=["Private Charts"])

@router.get("/exports/{filename}")
async def download_export_file(filename: str, workspace: Workspace = Depends(get_workspace)):
    """下载生成的 Word (.docx) 或 Excel 对账表 (.xlsx)"""
    file_path = (workspace.export_dir / filename).resolve()
    if file_path.parent != workspace.export_dir.resolve() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path, filename=filename)

@router.get("/assets/charts/{filename}")
@static_router.get("/charts/{filename}")
async def get_chart_image(filename: str, workspace: Workspace = Depends(get_workspace)):
    """获取生成的 300DPI 统计图表 PNG 图像"""
    file_path = (workspace.chart_dir / filename).resolve()
    if file_path.parent != workspace.chart_dir.resolve() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="图表文件不存在")
    return FileResponse(file_path, media_type="image/png")
