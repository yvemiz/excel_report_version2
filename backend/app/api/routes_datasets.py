"""Dataset and report-version APIs for the single-school instance."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.workspaces import Workspace, get_workspace, get_mutable_workspace

router = APIRouter(prefix="/api", tags=["Datasets & Report Versions"])


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    academic_year: str = Field(default="", max_length=40)
    kind: Literal["real", "demo"] = "real"


class DatasetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    academic_year: Optional[str] = Field(default=None, max_length=40)
    status: Optional[Literal["active", "archived"]] = None


class SchoolProfile(BaseModel):
    school_name: str = Field(min_length=1, max_length=120)
    school_code: str = Field(default="", max_length=40)


@router.get("/datasets")
def list_datasets(workspace: Workspace = Depends(get_workspace)):
    return {"datasets": workspace.list_datasets(), "default_dataset_id": workspace.default_dataset_id}


@router.post("/datasets")
def create_dataset(payload: DatasetCreate, workspace: Workspace = Depends(get_mutable_workspace)):
    row = workspace.create_dataset(payload.name, payload.academic_year, kind=payload.kind)
    return {"dataset": row, "default_dataset_id": workspace.default_dataset_id}


@router.post("/datasets/{dataset_id}/default")
def set_default_dataset(dataset_id: str, workspace: Workspace = Depends(get_mutable_workspace)):
    return {"dataset": workspace.set_default_dataset(dataset_id)}


@router.patch("/datasets/{dataset_id}")
def update_dataset(dataset_id: str, payload: DatasetUpdate, workspace: Workspace = Depends(get_mutable_workspace)):
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    row = workspace.auth.update_dataset(workspace.user_id, dataset_id, **fields)
    if row is None:
        raise HTTPException(status_code=404, detail="数据集不存在或不属于当前账号")
    return {"dataset": row}


@router.get("/datasets/{dataset_id}/status")
def dataset_status(dataset_id: str, workspace: Workspace = Depends(get_workspace)):
    return workspace.snapshot(dataset_id)


@router.get("/datasets/{dataset_id}/reports")
def dataset_reports(dataset_id: str, workspace: Workspace = Depends(get_workspace)):
    dataset = workspace.dataset(dataset_id)
    return {"dataset": dataset.dataset, "reports": dataset.report_versions()}


@router.get("/reports/{report_version_id}")
def report_snapshot(report_version_id: str, workspace: Workspace = Depends(get_workspace)):
    return workspace.report(report_version_id).snapshot()


@router.post("/reports/{report_version_id}/sections/{section_id}/retry")
def retry_report_section(
    report_version_id: str,
    section_id: str,
    workspace: Workspace = Depends(get_mutable_workspace),
):
    """Create a new report version that regenerates only one section."""
    report = workspace.report(report_version_id)
    new_report = report.retry_section(section_id)
    return {
        "dataset_id": new_report.dataset_workspace.dataset_id,
        "report_version_id": new_report.report_version_id,
        "source_report_version_id": report_version_id,
        "section_id": section_id,
    }


@router.get("/school")
def get_school(workspace: Workspace = Depends(get_workspace)):
    return {"school": workspace.school_profile, "school_name": workspace.school_name}


@router.put("/school")
def save_school(payload: SchoolProfile, workspace: Workspace = Depends(get_mutable_workspace)):
    return {"school": workspace.save_school_profile(payload.school_name, payload.school_code)}
