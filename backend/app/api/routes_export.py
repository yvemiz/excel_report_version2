import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.config import settings

router = APIRouter(prefix="/api", tags=["Exports & Assets"])

@router.get("/exports/{filename}")
async def download_export_file(filename: str):
    """下载生成的 Word (.docx) 或 Excel 对账表 (.xlsx)"""
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(settings.EXPORTS_DIR, safe_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path, filename=safe_filename)

@router.get("/assets/charts/{filename}")
async def get_chart_image(filename: str):
    """获取生成的 300DPI 统计图表 PNG 图像"""
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(settings.CHARTS_DIR, safe_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="图表文件不存在")
    return FileResponse(file_path, media_type="image/png")
