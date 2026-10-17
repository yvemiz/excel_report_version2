"""Account-scoped services. User ids always come from an authenticated session."""
import json
import logging
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

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


class Workspace:
    def __init__(self, user_id: int, data_dir: str, auth: AuthStore):
        self.user_id = user_id
        self.auth = auth
        self.data_root = Path(data_dir).resolve()
        self.root = self.data_root / "users" / str(user_id)
        self.upload_dir = self.root / "uploads"
        self.export_dir = self.root / "exports"
        self.chart_dir = self.root / "charts"
        self.checkpoint_dir = self.root / "checkpoints"
        for directory in (self.upload_dir, self.export_dir, self.chart_dir, self.checkpoint_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.operation_lock = threading.Lock()
        self.cell_lake = CellLake(str(self.root / "cell_lake.db"))
        self.duckdb = DuckDBEngine(str(self.root / "metrics.duckdb"))
        # DuckDB's legacy discovery guesses names from sanitized SQL identifiers.
        # Recover the original names from this account's persisted cell records.
        for source in self.cell_lake.get_tables_summary():
            name = f"{Path(source['file_name']).stem}_{source['sheet_name']}"
            table = self.duckdb.registered_tables.get(self.duckdb._sanitize_table_name(name))
            if table:
                table.update(file_name=source["file_name"], sheet_name=source["sheet_name"])
        charts = ChartService(str(self.chart_dir))
        runner = PiAgentRunner(charts)
        judge = JevJudge()
        self.pipeline = ReportPipeline(
            self.cell_lake, self.duckdb, charts, AuditService(self.cell_lake),
            DocxExporter(str(self.export_dir)), ExcelExporter(str(self.export_dir)),
            runner, judge, checkpoint_dir=str(self.checkpoint_dir),
        )
        self.apply_config(auth.load_config(user_id))
        self.restore_report()

    def apply_config(self, config: dict):
        writer, judge = self.pipeline.agent_runner, self.pipeline.jev_judge
        writer.set_api_key(config["api_key"])
        writer.base_url, writer.model = config["base_url"], config["model"]
        writer.set_agent_mode(config["agent_mode"])
        judge.api_key, judge.base_url, judge.model = config["api_key"], config["base_url"], config["model"]

    def mark_data_changed(self):
        if self.pipeline.current_stage > 0 and not self.pipeline.data_changed:
            self.pipeline.data_changed = True
            self.pipeline.save_checkpoint()

    def delete_data(self, table_name: Optional[str] = None):
        """在账号操作锁内同步删除目录与来源单元格，保留已生成报告。"""
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
                # Names come from this account's database/catalog, never raw SQL input.
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

        # Keep a workbook copy while any of its sheets remain. Imported source
        # directories and the shared example directory are never modified.
        remaining_files = {item["file_name"] for item in self.cell_lake.get_tables_summary()}
        remaining_files.update(item["file_name"] for item in self.duckdb.get_catalog())
        upload_root = self.upload_dir.resolve()
        cleanup_failed = False
        try:
            for path in self.upload_dir.iterdir():
                if table is not None and path.name != table["file_name"]:
                    continue
                if path.name in remaining_files or not path.is_file():
                    continue
                if path.is_symlink() or path.resolve().parent != upload_root:
                    continue
                try:
                    path.unlink()
                except OSError:
                    cleanup_failed = True
                    logger.exception("Cannot remove unused upload for user %s", self.user_id)
        except OSError:
            cleanup_failed = True
            logger.exception("Cannot clean upload directory for user %s", self.user_id)
        return {
            "success": True,
            "deleted_tables": len(names),
            "deleted_cells": deleted_cells,
            "total_cells": self.cell_lake.count(),
            "file_cleanup_warning": cleanup_failed,
            "message": "已清空当前账号的全部入库数据" if table is None else f"已删除工作表：{table['sheet_name']}",
        }

    def snapshot(self):
        pipe = self.pipeline
        return {
            "current_stage": pipe.current_stage,
            "stages": pipe.stages_info,
            "sections_plan": pipe.sections_plan,
            "generated_sections": pipe.generated_sections,
            "export_files": pipe.export_files,
            "outline_audit": pipe.outline_jev_audit,
            "school_name": pipe.custom_school_name,
            "is_running": self.operation_lock.locked(),
            "data_changed": pipe.data_changed,
        }

    def restore_report(self):
        checkpoint = self.checkpoint_dir / "pipeline_checkpoint.json"
        if not checkpoint.exists():
            return
        try:
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
            pipe = self.pipeline
            pipe.current_stage = saved.get("current_stage", 0)
            pipe.sections_plan = saved.get("sections_plan", [])
            pipe.generated_sections = saved.get("generated_sections", [])
            pipe.export_files = saved.get("export_files", {})
            pipe.outline_jev_audit = saved.get("outline_audit", {})
            pipe.custom_school_name = saved.get("school_name", "")
            pipe.data_changed = bool(saved.get("data_changed", False))
        except (OSError, ValueError):
            logger.exception("Cannot restore report for user %s", self.user_id)


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
            workspace.duckdb.conn.close()


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
