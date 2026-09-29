import sqlite3
import os
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

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

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

    def insert_cells(self, cells: List[Dict[str, Any]]) -> int:
        """批量写入单元格记录"""
        if not cells:
            return 0
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
            INSERT OR REPLACE INTO cell_lake (
                cell_id, file_name, sheet_name, row_idx, col_idx, cell_ref, metric_path, raw_value, numeric_value
            ) VALUES (
                :cell_id, :file_name, :sheet_name, :row_idx, :col_idx, :cell_ref, :metric_path, :raw_value, :numeric_value
            );
            """, cells)
            conn.commit()
        return len(cells)

    def get_cell(self, cell_id: str) -> Optional[Dict[str, Any]]:
        """根据 cell_id 查询单个单元格明细"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cell_lake WHERE cell_id = ?", (cell_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

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

    def count(self) -> int:
        """统计入湖单元格总量"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM cell_lake")
            return cursor.fetchone()[0]
