import sqlite3
import os
import re
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
                numeric_value REAL
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_cell_ref ON cell_lake(file_name, sheet_name, cell_ref);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_metric ON cell_lake(metric_path);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_value ON cell_lake(raw_value);")
            conn.commit()

    def clear(self):
        """清空数据湖"""
        with self._get_conn() as conn:
            conn.cursor().execute("DELETE FROM cell_lake;")
            conn.commit()

    def delete_sheet(self, file_name: str, sheet_name: str) -> int:
        """只删除指定来源文件中的一个工作表，避免同名工作表相互影响。"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM cell_lake WHERE file_name = ? AND sheet_name = ?",
                (file_name, sheet_name),
            )
            return cursor.rowcount

    def insert_cells(self, cells: List[Dict[str, Any]], batch_size: int = 5000) -> int:
        """批量写入单元格记录（支持海量数据极速分块事务提交）"""
        if not cells:
            return 0
        total_inserted = 0
        with self._get_conn() as conn:
            cursor = conn.cursor()
            for i in range(0, len(cells), batch_size):
                chunk = cells[i:i + batch_size]
                cursor.executemany("""
                INSERT OR REPLACE INTO cell_lake (
                    cell_id, file_name, sheet_name, row_idx, col_idx, cell_ref, metric_path, raw_value, numeric_value
                ) VALUES (
                    :cell_id, :file_name, :sheet_name, :row_idx, :col_idx, :cell_ref, :metric_path, :raw_value, :numeric_value
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
            SELECT file_name, sheet_name, COUNT(*) as cell_count 
            FROM cell_lake 
            GROUP BY file_name, sheet_name
            ORDER BY file_name
            """)
            return [dict(r) for r in cursor.fetchall()]

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



