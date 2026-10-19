"""Account-scoped services for a single-school instance with isolated datasets."""
import copy
import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from starlette.requests import HTTPConnection

from app.core.auth_service import AuthStore
from app.core.cell_lake import CellLake
from app.core.duckdb_engine import DuckDBEngine
from app.core.chart_service import ChartService
from app.core.audit_service import AuditService
from app.core.docx_exporter import DocxExporter
from app.core.excel_exporter import ExcelExporter
from app.pipeline.agent_runner import PiAgentRunner
from app.pipeline.jev_judge import JevJudge
from app.pipeline.stages import ReportPipeline

logger = logging.getLogger(__name__)


def _int_time() -> int:
    return int(time.time())




def _quality_summary(pipeline: ReportPipeline) -> Dict[str, Any]:
    return pipeline.quality_summary()


class ReportWorkspace:
    """One immutable report version inside a dataset."""

    def __init__(self, dataset_workspace: "DatasetWorkspace", version: Dict[str, Any]):
        self.dataset_workspace = dataset_workspace
        self.owner = dataset_workspace.owner
        self.version = version
        self.report_version_id = version["id"]
        self.checkpoint_dir = (dataset_workspace.root / version["checkpoint_dir"]).resolve()
        self.export_dir = (dataset_workspace.root / version["export_dir"]).resolve()
        self.chart_dir = self.owner.chart_dir
        for directory in (self.checkpoint_dir, self.export_dir, self.chart_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self.chart_service = ChartService(str(self.chart_dir))
        self.agent_runner = PiAgentRunner(self.chart_service)
        self.judge = JevJudge()
        prefix = "/api/exports" if dataset_workspace.is_legacy and version.get("status") == "completed" else f"/api/reports/{self.report_version_id}/exports"
        self.pipeline = ReportPipeline(
            dataset_workspace.cell_lake,
            dataset_workspace.duckdb,
            self.chart_service,
            AuditService(dataset_workspace.cell_lake),
            DocxExporter(str(self.export_dir)),
            ExcelExporter(str(self.export_dir)),
            self.agent_runner,
            self.judge,
            checkpoint_dir=str(self.checkpoint_dir),
            export_url_prefix=prefix,
        )
        self.apply_config(self.owner.config)
        self.restore()

    def apply_config(self, config: dict):
        writer, judge = self.pipeline.agent_runner, self.pipeline.jev_judge
        writer.set_api_key(config["api_key"])
        writer.base_url, writer.model = config["base_url"], config["model"]
        writer.set_agent_mode(config["agent_mode"])
        judge.api_key, judge.base_url, judge.model = config["api_key"], config["base_url"], config["model"]

    def restore(self):
        checkpoint = self.checkpoint_dir / "pipeline_checkpoint.json"
        if not checkpoint.exists():
            self.pipeline.custom_school_name = self.version.get("school_name") or self.owner.school_name
            return
        try:
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            pipe = self.pipeline
            pipe.current_stage = saved.get("current_stage", 0)
            pipe.sections_plan = saved.get("sections_plan", [])
            pipe.generated_sections = saved.get("generated_sections", [])
            pipe.export_files = saved.get("export_files", {})
            pipe.outline_jev_audit = saved.get("outline_audit", {})
            pipe.custom_school_name = saved.get("school_name", self.version.get("school_name", ""))
            pipe.data_changed = bool(saved.get("data_changed", False))
            if self.report_version_id.startswith("rv_legacy_"):
                for kind in ("docx", "xlsx"):
                    path = pipe.export_files.get(kind)
                    if path:
                        pipe.export_files[f"{kind}_url"] = (
                            f"/api/reports/{self.report_version_id}/exports/{quote(Path(path).name)}"
                        )
        except (OSError, ValueError):
            logger.exception("Cannot restore report %s", self.report_version_id)

    def snapshot(self) -> Dict[str, Any]:
        pipe = self.pipeline
        dataset = self.dataset_workspace.dataset
        data_changed = bool(
            pipe.data_changed
            or int(self.version.get("revision_no") or 0) != int(dataset.get("current_revision") or 0)
        )
        return {
            "current_stage": pipe.current_stage,
            "stages": pipe.stages_info,
            "sections_plan": pipe.sections_plan,
            "generated_sections": pipe.generated_sections,
            "export_files": pipe.export_files,
            "outline_audit": pipe.outline_jev_audit,
            "school_name": pipe.custom_school_name or self.owner.school_name,
            "is_running": self.owner.operation_lock.locked(),
            "data_changed": data_changed,
            "dataset_id": self.dataset_workspace.dataset_id,
            "dataset_name": dataset.get("name", ""),
            "dataset_kind": dataset.get("kind", "real"),
            "dataset_academic_year": dataset.get("academic_year", ""),
            "current_revision": dataset.get("current_revision", 1),
            "report_version_id": self.report_version_id,
            "report_version_status": self.version.get("status", "pending"),
            "revision_no": self.version.get("revision_no", 1),
            "report_created_at": self.version.get("created_at"),
            "report_completed_at": self.version.get("completed_at"),
            "quality_summary": _quality_summary(pipe),
        }

    def mark_status(self, status: str, error: str = ""):
        fields = {"status": status}
        if status in {"completed", "failed", "interrupted"}:
            fields["completed_at"] = _int_time()
        if error:
            fields["error"] = error
        updated = self.owner.auth.update_report_version(self.report_version_id, **fields)
        if updated:
            self.version = updated
        return updated

    def retry_section(self, section_id: str) -> "ReportWorkspace":
        """Create a new report version that regenerates one section and reuses the rest."""
        plan_ids = {item.get("id") for item in (self.pipeline.sections_plan or [])}
        if section_id not in plan_ids:
            raise HTTPException(status_code=404, detail="章节不存在于当前报告大纲")
        dataset = self.dataset_workspace.dataset
        if int(self.version.get("revision_no") or 0) != int(dataset.get("current_revision") or 0):
            raise HTTPException(status_code=409, detail="数据已变化，请先重新生成报告，不能直接重试旧章节")
        new_report = self.dataset_workspace.create_report(
            school_name=self.pipeline.custom_school_name or self.owner.school_name,
            status="running",
        )
        pipe = new_report.pipeline
        pipe.sections_plan = copy.deepcopy(self.pipeline.sections_plan)
        pipe.outline_jev_audit = copy.deepcopy(self.pipeline.outline_jev_audit)
        pipe.generated_sections = [
            copy.deepcopy(section)
            for section in self.pipeline.generated_sections
            if section.get("id") != section_id
        ]
        pipe.custom_school_name = self.pipeline.custom_school_name
        pipe.current_stage = 1
        pipe.data_changed = False
        pipe.save_checkpoint()
        return new_report

    def artifact_path(self, filename: str) -> Path:
        target = (self.export_dir / filename).resolve()
        if target.parent != self.export_dir.resolve() or not target.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        return target


class DatasetWorkspace:
    """A dataset owns its source files and its own SQLite/DuckDB data stores."""

    def __init__(self, owner: "Workspace", dataset: Dict[str, Any]):
        self.owner = owner
        self.dataset = dict(dataset)
        self.dataset_id = dataset["id"]
        self.kind = dataset.get("kind", "real")
        self.is_legacy = dataset.get("storage_key") == "legacy" or self.kind == "legacy"
        if self.is_legacy:
            self.root = owner.root
            self.upload_dir = owner.root / "uploads"
            self.reports_dir = owner.root
        else:
            self.root = (owner.root / dataset["storage_key"]).resolve()
            if owner.root.resolve() not in self.root.parents:
                raise HTTPException(status_code=500, detail="数据集存储路径无效")
            self.upload_dir = self.root / "uploads"
            self.reports_dir = self.root / "reports"
        for directory in (self.root, self.upload_dir, self.reports_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self.cell_lake = CellLake(str(self.root / "cell_lake.db"))
        self.duckdb = DuckDBEngine(str(self.root / "metrics.duckdb"))
        self._sync_table_metadata()
        self._reports: Dict[str, ReportWorkspace] = {}

    def _sync_table_metadata(self):
        for source in self.cell_lake.get_tables_summary():
            name = f"{Path(source['file_name']).stem}_{source['sheet_name']}"
            table = self.duckdb.registered_tables.get(self.duckdb._sanitize_table_name(name))
            if table:
                table.update(file_name=source["file_name"], sheet_name=source["sheet_name"])

    def refresh(self):
        row = self.owner.auth.get_dataset(self.owner.user_id, self.dataset_id)
        if row:
            self.dataset = row
        return self.dataset

    def report_versions(self) -> List[Dict[str, Any]]:
        return self.owner.auth.list_report_versions(self.dataset_id)

    def get_report(self, report_version_id: str) -> ReportWorkspace:
        if report_version_id in self._reports:
            return self._reports[report_version_id]
        version = self.owner.auth.get_report_version(report_version_id)
        if not version or version.get("dataset_id") != self.dataset_id:
            raise HTTPException(status_code=404, detail="报告版本不存在或不属于当前数据集")
        report = ReportWorkspace(self, version)
        self._reports[report_version_id] = report
        return report

    def latest_report(self) -> Optional[ReportWorkspace]:
        versions = self.report_versions()
        if not versions:
            return None
        return self.get_report(versions[0]["id"])

    def ensure_legacy_report(self):
        """Register the legacy checkpoint as a report version, even when empty."""
        if not self.is_legacy or self.report_versions():
            return
        checkpoint = self.root / "checkpoints" / "pipeline_checkpoint.json"
        report_id = f"rv_legacy_{self.owner.user_id}"
        if self.owner.auth.get_report_version(report_id):
            return
        self.owner.auth.create_report_version(
            dataset_id=self.dataset_id,
            revision_no=int(self.dataset.get("current_revision", 1)),
            checkpoint_dir="checkpoints",
            export_dir="exports",
            chart_dir="",
            school_name=self.owner.school_name,
            model=self.owner.config.get("model", ""),
            agent_mode=self.owner.config.get("agent_mode", ""),
            status="completed" if checkpoint.exists() else "pending",
            report_version_id=report_id,
        )
        self._reports.clear()

    def create_report(self, school_name: str = "", status: str = "running") -> ReportWorkspace:
        report_id = f"rv_{uuid.uuid4().hex}"
        relative = f"reports/{report_id}"
        checkpoint_dir = f"{relative}/checkpoint"
        export_dir = f"{relative}/exports"
        (self.root / checkpoint_dir).mkdir(parents=True, exist_ok=True)
        (self.root / export_dir).mkdir(parents=True, exist_ok=True)
        self.owner.auth.create_report_version(
            dataset_id=self.dataset_id,
            revision_no=int(self.dataset.get("current_revision", 1)),
            checkpoint_dir=checkpoint_dir,
            export_dir=export_dir,
            chart_dir="",
            school_name=school_name or self.owner.school_name,
            model=self.owner.config.get("model", ""),
            agent_mode=self.owner.config.get("agent_mode", ""),
            status=status,
            report_version_id=report_id,
        )
        self.refresh()
        return self.get_report(report_id)

    def mark_data_changed(self):
        revision = self.owner.auth.increment_dataset_revision(self.owner.user_id, self.dataset_id)
        self.dataset["current_revision"] = revision
        latest = self.latest_report()
        if latest:
            latest.pipeline.data_changed = True
            latest.pipeline.save_checkpoint()
        return revision

    def snapshot(self) -> Dict[str, Any]:
        report = self.latest_report()
        if report:
            return report.snapshot()
        return {
            "current_stage": 0,
            "stages": [],
            "sections_plan": [],
            "generated_sections": [],
            "export_files": {},
            "outline_audit": {},
            "school_name": self.owner.school_name,
            "is_running": self.owner.operation_lock.locked(),
            "data_changed": False,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset.get("name", ""),
            "dataset_kind": self.dataset.get("kind", "real"),
            "dataset_academic_year": self.dataset.get("academic_year", ""),
            "current_revision": self.dataset.get("current_revision", 1),
            "report_version_id": "",
            "report_version_status": "empty",
            "revision_no": 0,
            "report_created_at": None,
            "report_completed_at": None,
        }

    def remove_data(self, table_name: Optional[str] = None):
        table = self.duckdb.registered_tables.get(table_name) if table_name is not None else None
        if table_name is not None and table is None:
            raise HTTPException(status_code=404, detail="工作表不存在或已被删除，请刷新数据目录")
        names = [table_name] if table is not None else [
            row[0] for row in self.duckdb.conn.execute("SHOW TABLES").fetchall()
        ]
        deleted_cells = self.cell_lake.count() if table is None else 0
        self.duckdb.conn.execute("BEGIN TRANSACTION")
        try:
            for name in names:
                quoted_name = '"' + name.replace('"', '""') + '"'
                self.duckdb.conn.execute(f"DROP TABLE IF EXISTS {quoted_name}")
            if table is None:
                self.cell_lake.clear()
            else:
                deleted_cells = self.cell_lake.delete_sheet(table["file_name"], table["sheet_name"])
            self.duckdb.conn.execute("COMMIT")
        except Exception:
            self.duckdb.conn.execute("ROLLBACK")
            raise
        if table is None:
            self.duckdb.registered_tables.clear()
        else:
            self.duckdb.registered_tables.pop(table_name, None)
        self.mark_data_changed()

        remaining_files = {item["file_name"] for item in self.cell_lake.get_tables_summary()}
        remaining_files.update(item["file_name"] for item in self.duckdb.get_catalog())
        cleanup_failed = False
        try:
            for path in self.upload_dir.iterdir():
                if table is not None and path.name != table["file_name"]:
                    continue
                if path.name in remaining_files or not path.is_file():
                    continue
                if path.is_symlink() or path.resolve().parent != self.upload_dir.resolve():
                    continue
                try:
                    path.unlink()
                except OSError:
                    cleanup_failed = True
                    logger.exception("Cannot remove unused upload for user %s", self.owner.user_id)
        except OSError:
            cleanup_failed = True
            logger.exception("Cannot clean upload directory for user %s", self.owner.user_id)
        return {
            "success": True,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset.get("name", ""),
            "deleted_tables": len(names),
            "deleted_cells": deleted_cells,
            "total_cells": self.cell_lake.count(),
            "file_cleanup_warning": cleanup_failed,
            "message": f"已清空数据集“{self.dataset.get('name', '')}”的全部入库数据"
            if table is None else f"已删除工作表：{table['sheet_name']}",
        }

    def apply_config(self, config: dict):
        for report in self._reports.values():
            report.apply_config(config)

    def close(self):
        try:
            self.duckdb.close()
        except Exception:
            logger.exception("Cannot close DuckDB for dataset %s", self.dataset_id)


class Workspace:
    """Account manager plus the single-school dataset registry."""

    def __init__(self, user_id: int, data_dir: str, auth: AuthStore):
        self.user_id = user_id
        self.auth = auth
        self.data_root = Path(data_dir).resolve()
        self.root = self.data_root / "users" / str(user_id)
        self.root.mkdir(parents=True, exist_ok=True)
        self.chart_dir = self.root / "charts"
        self.chart_dir.mkdir(parents=True, exist_ok=True)
        self.operation_lock = threading.Lock()
        self.config = auth.load_config(user_id)
        self.school_profile = auth.get_school_profile(user_id)
        self._datasets: Dict[str, DatasetWorkspace] = {}
        self._dataset_rows: Dict[str, Dict[str, Any]] = {}
        self._default_dataset_id = ""
        self._legacy_dataset_id = ""
        self._ensure_initial_dataset()
        self.apply_config(self.config)

    def _ensure_initial_dataset(self):
        rows = self.auth.list_datasets(self.user_id)
        legacy = next((row for row in rows if row.get("kind") == "legacy" or row.get("storage_key") == "legacy"), None)
        if legacy is None:
            legacy = self.auth.create_dataset(
                self.user_id,
                name="默认批次",
                kind="legacy",
                storage_key="legacy",
                is_default=not rows,
            )
            self._dataset_rows[legacy["id"]] = legacy
        self._legacy_dataset_id = legacy["id"]
        default = self.auth.get_default_dataset(self.user_id)
        if default is None:
            default = self.auth.set_default_dataset(self.user_id, legacy["id"]) or legacy
        self._default_dataset_id = default["id"]
        self._dataset_rows[default["id"]] = default
        legacy_ws = self.dataset(legacy["id"])
        if not self.school_profile.get("school_name"):
            metadata = legacy_ws.cell_lake.detect_school_metadata()
            detected = (metadata.get("school_name") or "").strip()
            code = (metadata.get("school_code") or "").strip()
            if detected:
                self.school_profile = self.auth.save_school_profile(self.user_id, detected, code)
                if legacy.get("name") == "默认批次":
                    updated = self.auth.update_dataset(self.user_id, legacy["id"], name=f"历史数据（{detected}）")
                    if updated:
                        self._dataset_rows[legacy["id"]] = updated
                        legacy_ws.dataset = updated
        legacy_ws.ensure_legacy_report()

    @property
    def school_name(self) -> str:
        return (self.school_profile.get("school_name") or "").strip()

    def save_school_profile(self, school_name: str, school_code: str = ""):
        self.school_profile = self.auth.save_school_profile(self.user_id, school_name, school_code)
        return self.school_profile

    def dataset(self, dataset_id: Optional[str] = None) -> DatasetWorkspace:
        target = dataset_id or self._default_dataset_id
        if not target:
            raise HTTPException(status_code=500, detail="当前账号没有可用数据集")
        row = self._dataset_rows.get(target)
        if row is None:
            row = self.auth.get_dataset(self.user_id, target)
            if row is None:
                raise HTTPException(status_code=404, detail="数据集不存在或不属于当前账号")
            self._dataset_rows[target] = row
        if target not in self._datasets:
            self._datasets[target] = DatasetWorkspace(self, row)
        return self._datasets[target]

    @property
    def default_dataset_id(self) -> str:
        return self._default_dataset_id

    @property
    def legacy_dataset_id(self) -> str:
        return self._legacy_dataset_id

    def list_datasets(self) -> List[Dict[str, Any]]:
        result = []
        for row in self.auth.list_datasets(self.user_id):
            self._dataset_rows[row["id"]] = row
            ds = self.dataset(row["id"])
            reports = self.auth.list_report_versions(row["id"])
            latest = reports[0] if reports else None
            metadata = ds.cell_lake.detect_school_metadata()
            result.append({
                **row,
                "dataset_id": row["id"],
                "cell_count": ds.cell_lake.count(),
                "table_count": len(ds.duckdb.get_catalog()),
                "report_count": len(reports),
                "latest_report_id": latest["id"] if latest else "",
                "latest_report_status": latest["status"] if latest else "",
                "detected_school_name": metadata.get("school_name", ""),
            })
        return result

    def create_dataset(self, name: str, academic_year: str = "", kind: str = "real"):
        row = self.auth.create_dataset(self.user_id, name, academic_year, kind=kind, is_default=False)
        self._dataset_rows[row["id"]] = row
        return row

    def ensure_demo_dataset(self):
        for row in self.auth.list_datasets(self.user_id):
            if row.get("kind") == "demo":
                self._dataset_rows[row["id"]] = row
                return row
        row = self.auth.create_dataset(
            self.user_id, name="示例数据", academic_year="", kind="demo", is_default=False
        )
        self._dataset_rows[row["id"]] = row
        return row

    def set_default_dataset(self, dataset_id: str):
        row = self.auth.set_default_dataset(self.user_id, dataset_id)
        if not row:
            raise HTTPException(status_code=404, detail="数据集不存在或不属于当前账号")
        self._dataset_rows[dataset_id] = row
        self._default_dataset_id = dataset_id
        return row

    def report(self, report_version_id: str) -> ReportWorkspace:
        version = self.auth.get_report_version(report_version_id)
        if not version:
            raise HTTPException(status_code=404, detail="报告版本不存在")
        dataset = self.dataset(version["dataset_id"])
        return dataset.get_report(report_version_id)

    @property
    def cell_lake(self) -> CellLake:
        return self.dataset().cell_lake

    @property
    def duckdb(self) -> DuckDBEngine:
        return self.dataset().duckdb

    @property
    def upload_dir(self) -> Path:
        return self.dataset().upload_dir

    @property
    def export_dir(self) -> Path:
        report = self.dataset().latest_report()
        return report.export_dir if report else (self.dataset().root / "exports")

    @property
    def checkpoint_dir(self) -> Path:
        report = self.dataset().latest_report()
        return report.checkpoint_dir if report else (self.dataset().root / "checkpoints")

    @property
    def pipeline(self) -> ReportPipeline:
        report = self.dataset().latest_report()
        if report is None:
            raise RuntimeError("当前数据集还没有报告版本，请先开始生成")
        return report.pipeline

    def apply_config(self, config: dict):
        self.config = config
        for ds in self._datasets.values():
            ds.apply_config(config)

    def mark_data_changed(self, dataset_id: Optional[str] = None):
        return self.dataset(dataset_id).mark_data_changed()

    def delete_data(self, table_name: Optional[str] = None, dataset_id: Optional[str] = None):
        return self.dataset(dataset_id).remove_data(table_name)

    def snapshot(self, dataset_id: Optional[str] = None) -> Dict[str, Any]:
        return self.dataset(dataset_id).snapshot()

    def restore_report(self):
        # Compatibility hook: report restoration is now lazy per report version.
        return self.snapshot()

    def close(self):
        for ds in self._datasets.values():
            ds.close()


class WorkspaceManager:
    def __init__(self, data_dir: str, auth: AuthStore):
        self.data_dir, self.auth = data_dir, auth
        self._items = {}
        self._lock = threading.Lock()

    def get(self, user_id: int) -> Workspace:
        with self._lock:
            if user_id not in self._items:
                self._items[user_id] = Workspace(user_id, self.data_dir, self.auth)
            return self._items[user_id]

    def close(self):
        for workspace in self._items.values():
            workspace.close()


def get_workspace(connection: HTTPConnection) -> Workspace:
    return connection.app.state.workspaces.get(connection.state.user["id"])


def get_mutable_workspace(connection: HTTPConnection):
    workspace = get_workspace(connection)
    with workspace_operation(workspace):
        yield workspace


def begin_operation(workspace: Workspace):
    if not workspace.operation_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="当前账号有任务正在执行，请等待结束后再操作")


@contextmanager
def workspace_operation(workspace: Workspace):
    begin_operation(workspace)
    try:
        yield
    finally:
        workspace.operation_lock.release()
