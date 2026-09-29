import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

from app.api.routes_upload import router as upload_router, init_upload_routes
from app.api.routes_pipeline import router as pipeline_router, init_pipeline_routes
from app.api.routes_export import router as export_router

# 初始化核心单例
cell_lake = CellLake(settings.SQLITE_PATH)
duckdb_engine = DuckDBEngine(settings.DUCKDB_PATH)
chart_service = ChartService(settings.CHARTS_DIR)
audit_service = AuditService(cell_lake)
docx_exporter = DocxExporter(settings.EXPORTS_DIR)
excel_exporter = ExcelExporter(settings.EXPORTS_DIR)
agent_runner = PiAgentRunner(chart_service)
jev_judge = JevJudge()

# 组装 5 阶段确定性流水线
pipeline = ReportPipeline(
    cell_lake=cell_lake,
    duckdb_engine=duckdb_engine,
    chart_service=chart_service,
    audit_service=audit_service,
    docx_exporter=docx_exporter,
    excel_exporter=excel_exporter,
    agent_runner=agent_runner,
    jev_judge=jev_judge
)

# 注入路由模块
init_upload_routes(cell_lake, duckdb_engine)
init_pipeline_routes(pipeline)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="高校发展检验报告生成系统后端 (FastAPI + DuckDB + SQLite Cell Lake + Pi-Agent Runner)"
)

# 允许跨域（Vue 3 前端跨域支持）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态资源
app.mount("/static", StaticFiles(directory=os.path.join(settings.BASE_DIR, "static")), name="static")

# 挂载 API 路由
app.include_router(upload_router)
app.include_router(pipeline_router)
app.include_router(export_router)

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "cells_in_lake": cell_lake.count(),
        "tables_in_duckdb": len(duckdb_engine.get_catalog())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8008, reload=True)
