import sqlite3
import os
import re
import shutil
import time
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

class CellLake:
    """
    单元格溯源湖 (Cell Lake - SQLite 底座)
    存储所有原始单元格的真实物理坐标与指标归属，提供 100% 精确的穿透审计反查能力
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_schema()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA cache_size = -64000;")
        except Exception:
            pass
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS cell_lake (
                cell_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                sheet_name TEXT NOT NULL,
                row_idx INTEGER NOT NULL,
                col_idx INTEGER NOT NULL,
                cell_ref TEXT NOT NULL,
                metric_path TEXT NOT NULL,
                raw_value TEXT NOT NULL,
                numeric_value REAL,
                source_file_id TEXT,
                import_id TEXT
            );
            """)
            existing_columns = {
                row[1] for row in cursor.execute("PRAGMA table_info(cell_lake)").fetchall()
            }
            for column, ddl in (
                ("source_file_id", "ALTER TABLE cell_lake ADD COLUMN source_file_id TEXT"),
                ("import_id", "ALTER TABLE cell_lake ADD COLUMN import_id TEXT"),
            ):
                if column not in existing_columns:
                    cursor.execute(ddl)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cell_ref ON cell_lake(file_name, sheet_name, cell_ref);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric ON cell_lake(metric_path);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_value ON cell_lake(raw_value);")
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cell_source_file "
                "ON cell_lake(source_file_id, sheet_name);"
            )
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS source_files (
                source_file_id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                storage_mode TEXT NOT NULL DEFAULT 'upload',
                stored_rel_path TEXT NOT NULL DEFAULT '',
                original_path TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT '',
                size_bytes INTEGER NOT NULL DEFAULT 0,
                import_id TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            """)
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_source_files_name "
                "ON source_files(original_name);"
            )
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS import_batches (
                import_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                file_count INTEGER NOT NULL DEFAULT 0,
                sheet_count INTEGER NOT NULL DEFAULT 0,
                cell_count INTEGER NOT NULL DEFAULT 0,
                revision_before INTEGER NOT NULL DEFAULT 0,
                revision_after INTEGER,
                error TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                completed_at INTEGER
            );
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_import_batches_created "
                "ON import_batches(created_at DESC);"
            )
            conn.commit()

    def clear(self, clear_sources: bool = True):
        """清空数据湖；导入历史保留，便于追溯失败和成功记录。"""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM cell_lake;")
            if clear_sources:
                conn.execute("DELETE FROM source_files;")
            conn.commit()

    def delete_sheet(
        self,
        file_name: str,
        sheet_name: str,
        source_file_id: str = "",
    ) -> int:
        """只删除指定来源文件中的一个工作表，避免同名工作表相互影响。"""
        with self._get_conn() as conn:
            if source_file_id:
                cursor = conn.execute(
                    "DELETE FROM cell_lake WHERE source_file_id = ? AND sheet_name = ?",
                    (source_file_id, sheet_name),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM cell_lake WHERE file_name = ? AND sheet_name = ?",
                    (file_name, sheet_name),
                )
            return cursor.rowcount

    def checkpoint(self):
        with self._get_conn() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

    def snapshot_to(self, destination: str):
        """把当前 SQLite 数据湖完整复制为导入暂存副本。"""
        target = os.path.abspath(destination)
        if os.path.abspath(self.db_path) == target:
            raise ValueError("暂存数据库不能覆盖当前数据库")
        self.checkpoint()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target):
            os.remove(target)
        shutil.copy2(self.db_path, target)

    def insert_cells(self, cells: List[Dict[str, Any]], batch_size: int = 5000) -> int:
        """批量写入单元格记录（支持海量数据极速分块事务提交）"""
        if not cells:
            return 0
        for cell in cells:
            cell.setdefault("source_file_id", "")
            cell.setdefault("import_id", "")
        total_inserted = 0
        with self._get_conn() as conn:
            cursor = conn.cursor()
            for i in range(0, len(cells), batch_size):
                chunk = cells[i:i + batch_size]
                cursor.executemany("""
                INSERT OR REPLACE INTO cell_lake (
                    cell_id, file_name, sheet_name, row_idx, col_idx, cell_ref, metric_path,
                    raw_value, numeric_value, source_file_id, import_id
                ) VALUES (
                    :cell_id, :file_name, :sheet_name, :row_idx, :col_idx, :cell_ref, :metric_path,
                    :raw_value, :numeric_value, :source_file_id, :import_id
                );
                """, chunk)
                total_inserted += len(chunk)
            conn.commit()
        return total_inserted

    def get_cell(self, cell_id: str) -> Optional[Dict[str, Any]]:
        """根据 cell_id 查询单个单元格明细"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cell_lake WHERE cell_id = ?", (cell_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def get_cells_batch(self, cell_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量根据 cell_id 列表查询单元格明细，避免 N+1 连接开销"""
        if not cell_ids:
            return {}
        result = {}
        unique_ids = list(dict.fromkeys(cell_ids))
        with self._get_conn() as conn:
            cursor = conn.cursor()
            chunk_size = 800
            for i in range(0, len(unique_ids), chunk_size):
                chunk = unique_ids[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                cursor.execute(f"SELECT * FROM cell_lake WHERE cell_id IN ({placeholders})", chunk)
                for row in cursor.fetchall():
                    d = dict(row)
                    result[d["cell_id"]] = d
        return result

    def search_cells_by_keyword(self, keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
        """按指标名称或数值进行模糊检索"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM cell_lake 
            WHERE metric_path LIKE ? OR raw_value LIKE ?
            LIMIT ?
            """, (f"%{keyword}%", f"%{keyword}%", limit))
            return [dict(r) for r in cursor.fetchall()]

    def find_cell_by_value(self, value_str: str) -> Optional[Dict[str, Any]]:
        """根据精确数值/文本查找首个单元格（用于反查溯源）"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cell_lake WHERE raw_value = ? LIMIT 1", (value_str.strip(),))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def get_all_cells(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """获取所有单元格（分页/限额）"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cell_lake LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def get_cells_by_file_or_sheet(self, file_name: str, sheet_name: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        """按来源文件名与工作表名精确提取单元格"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if sheet_name:
                cursor.execute("""
                SELECT * FROM cell_lake 
                WHERE (file_name = ? OR file_name LIKE ?) AND sheet_name = ?
                LIMIT ?
                """, (file_name, f"%{file_name}%", sheet_name, limit))
            else:
                cursor.execute("""
                SELECT * FROM cell_lake 
                WHERE file_name = ? OR file_name LIKE ?
                LIMIT ?
                """, (file_name, f"%{file_name}%", limit))
            return [dict(r) for r in cursor.fetchall()]

    def get_tables_summary(self) -> List[Dict[str, Any]]:
        """获取所有入湖表格与工作表的汇总清单及单元格统计"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT COALESCE(source_file_id, '') AS source_file_id,
                   file_name, sheet_name, COUNT(*) as cell_count
            FROM cell_lake
            GROUP BY COALESCE(source_file_id, ''), file_name, sheet_name
            ORDER BY file_name, sheet_name
            """)
            return [dict(r) for r in cursor.fetchall()]

    def begin_import(
        self,
        kind: str,
        file_count: int = 0,
        revision_before: int = 0,
        import_id: str = "",
    ) -> str:
        import_id = import_id or f"imp_{os.urandom(8).hex()}"
        now = int(time.time())
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO import_batches(import_id,kind,status,file_count,revision_before,created_at) "
                "VALUES(?,?,'running',?,?,?)",
                (import_id, kind, file_count, revision_before, now),
            )
        return import_id

    def finish_import(
        self,
        import_id: str,
        status: str,
        file_count: int = 0,
        sheet_count: int = 0,
        cell_count: int = 0,
        error: str = "",
        revision_after: Optional[int] = None,
        completed: bool = True,
    ):
        now = int(time.time()) if completed else None
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE import_batches SET status=?,file_count=?,sheet_count=?,cell_count=?,"
                "error=?,revision_after=?,completed_at=? WHERE import_id=?",
                (status, file_count, sheet_count, cell_count, error[:4000],
                 revision_after, now, import_id),
            )

    def list_imports(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM import_batches ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (max(1, min(int(limit), 100)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_source_file(self, record: Dict[str, Any]):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO source_files(source_file_id,original_name,storage_mode,stored_rel_path,"
                "original_path,content_hash,size_bytes,import_id,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    record["source_file_id"], record["original_name"], record["storage_mode"],
                    record.get("stored_rel_path", ""), record.get("original_path", ""),
                    record.get("content_hash", ""), int(record.get("size_bytes", 0)),
                    record.get("import_id", ""), int(record.get("created_at") or time.time()),
                ),
            )

    def list_source_files(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM source_files ORDER BY created_at, original_name"
            ).fetchall()
            return [dict(row) for row in rows]

    def find_source_file_by_name(self, original_name: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM source_files WHERE original_name=?", (original_name,)
            ).fetchone()
            return dict(row) if row else None

    def delete_source_file(self, source_file_id: str):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM source_files WHERE source_file_id=?", (source_file_id,))

    def detect_school_metadata(self) -> Dict[str, str]:
        """从已入湖单元格的指标表头识别学校信息，无需调用大模型。"""
        field_aliases = {
            "school_name": ("学校名称", "高校名称", "校名"),
            "school_code": ("学校代码", "院校代码", "学校标识码"),
            "school_type": ("办学类型", "学校类型"),
            "school_nature": ("学校性质", "办学性质"),
        }
        metadata = {field: "" for field in field_aliases}
        aliases = [alias for names in field_aliases.values() for alias in names]
        conditions = " OR ".join("metric_path LIKE ?" for _ in aliases)

        with self._get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT metric_path, raw_value FROM cell_lake
                WHERE ({conditions}) AND TRIM(raw_value) <> ''
                ORDER BY CASE
                    WHEN file_name LIKE '%学校概况%' OR sheet_name LIKE '%学校概况%'
                        OR file_name LIKE '%基本情况%' OR sheet_name LIKE '%基本情况%'
                    THEN 0 ELSE 1 END,
                    file_name, sheet_name, row_idx, col_idx
                """,
                [f"%{alias}%" for alias in aliases],
            )
            for row in rows:
                # 只匹配末级指标，避免把“学校名称变更说明”等字段当成校名。
                metric = row["metric_path"].split(">")[-1].strip()
                metric = re.sub(r"[（(].*?[）)]", "", metric)
                metric = re.sub(r"\s+", "", metric).rstrip(":：")
                value = row["raw_value"].strip()
                if not value or value in {"-", "--", "—", "无", "未填"}:
                    continue
                for field, names in field_aliases.items():
                    if not metadata[field] and metric in names:
                        metadata[field] = value
                if all(metadata.values()):
                    break
        return metadata

    def count(self) -> int:
        """统计入湖单元格总量"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM cell_lake")
            return cursor.fetchone()[0]
