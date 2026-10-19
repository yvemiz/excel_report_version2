from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.auth_service import AuthStore
from app.core.auth_middleware import AuthenticationMiddleware
from app.core.workspaces import Workspace, WorkspaceManager, get_workspace
from app.api.routes_auth import router as auth_router
from app.api.routes_upload import router as upload_router
from app.api.routes_pipeline import router as pipeline_router
from app.api.routes_datasets import router as datasets_router
from app.api.routes_export import router as export_router, static_router


def create_app(data_dir=None, allowed_origins=None):
    root = str(Path(data_dir or settings.DATA_DIR).resolve())
    auth = AuthStore(root)
    workspaces = WorkspaceManager(root, auth)
    default_origins = [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:8008", "http://127.0.0.1:8008",
        "http://localhost:8080", "http://127.0.0.1:8080",
    ]
    configured_origins = [value.strip() for value in os.getenv("APP_ALLOWED_ORIGINS", "").split(",") if value.strip()]
    origins = allowed_origins if allowed_origins is not None else (configured_origins or default_origins)

    @asynccontextmanager
    async def lifespan(app):
        yield
        workspaces.close()

    app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)
    app.state.auth, app.state.workspaces = auth, workspaces

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Validation responses must not echo submitted passwords or API keys.
        return JSONResponse(
            status_code=422,
            content={"detail": "；".join(item["msg"] for item in error.errors())},
        )
    app.add_middleware(AuthenticationMiddleware, auth=auth, allowed_origins=origins)
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Content-Type"],
    )
    for router in (auth_router, datasets_router, upload_router, pipeline_router, export_router, static_router):
        app.include_router(router)

    @app.get("/healthz")
    def liveness_check():
        return {"status": "healthy"}

    @app.get("/api/health")
    def health_check(workspace: Workspace = Depends(get_workspace)):
        return {
            "status": "healthy", "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "cells_in_lake": workspace.cell_lake.count(),
            "tables_in_duckdb": len(workspace.duckdb.get_catalog()),
        }

    return app
