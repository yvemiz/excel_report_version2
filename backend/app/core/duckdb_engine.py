import duckdb
import os
import re
from typing import List, Dict, Any
import pandas as pd

class DuckDBEngine:
    """
    DuckDB 列式指标分析引擎
    将结构化后的二维表注册为 DuckDB 表，提供毫秒级、0 Token 消耗的 Python 参数化查询与聚合统计
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        try:
            self.conn = duckdb.connect(self.db_path)
        except Exception:
            try:
                self.conn = duckdb.connect(self.db_path, read_only=True)
            except Exception:
                self.conn = duckdb.connect(":memory:")
        self.registered_tables: Dict[str, Dict[str, Any]] = {}
        self._sync_existing_tables()

    def _sync_existing_tables(self):
        """若使用持久化数据库，自动同步已存在的表元数据"""
        try:
            tables = [r[0] for r in self.conn.execute("SHOW TABLES").fetchall()]
            for tbl in tables:
                if tbl not in self.registered_tables:
                    desc = self.conn.execute(f"DESCRIBE {tbl}").fetchall()
                    cols = [d[0] for d in desc]
                    row_cnt = self.conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    # 从表名还原粗略的文件与工作表信息
                    clean_name = tbl.replace("tbl_", "")
                    self.registered_tables[tbl] = {
                        "table_name": tbl,
                        "sheet_name": clean_name,
                        "file_name": clean_name,
                        "row_count": row_cnt,
                        "columns": cols
                    }
        except Exception:
            pass

    def _sanitize_table_name(self, name: str) -> str:
        """格式化表名，移除非法字符"""
        clean = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5]', '_', name)
        clean = re.sub(r'_+', '_', clean).strip('_')
        return f"tbl_{clean}"

    def register_sheet(self, sheet_name: str, file_name: str, rows: List[Dict[str, Any]], headers: List[str]) -> str:
        """将单个 Sheet 的数据注册为 DuckDB 表"""
        if not rows:
            return ""

        table_name = self._sanitize_table_name(f"{os.path.splitext(file_name)[0]}_{sheet_name}")
        df = pd.DataFrame(rows)
        
        # 将 DataFrame 注册为 DuckDB 表
        self.conn.register("df_temp", df)
        self.conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM df_temp")
        self.conn.unregister("df_temp")

        self.registered_tables[table_name] = {
            "table_name": table_name,
            "sheet_name": sheet_name,
            "file_name": file_name,
            "row_count": len(rows),
            "columns": headers
        }
        return table_name

    def query(self, sql: str) -> List[Dict[str, Any]]:
        """执行通用 SQL 查询并返回字典列表"""
        try:
            rel = self.conn.execute(sql)
            df = rel.df()
            return df.to_dict(orient="records")
        except Exception as e:
            return [{"error": str(e), "sql": sql}]

    def get_catalog(self) -> List[Dict[str, Any]]:
        """获取所有已加载表的粗索引目录 (Catalog Layer)"""
        return list(self.registered_tables.values())

    def get_table_summary(self, table_name: str) -> Dict[str, Any]:
        """获取特定表的结构与样本数据"""
        if table_name not in self.registered_tables:
            return {}
        info = self.registered_tables[table_name]
        sample = self.query(f"SELECT * FROM {table_name} LIMIT 5")
        return {
            **info,
            "sample_rows": sample
        }

    def clear(self):
        """清空所有注册的表与元数据"""
        try:
            tables = [r[0] for r in self.conn.execute("SHOW TABLES").fetchall()]
            for tbl in tables:
                self.conn.execute(f"DROP TABLE IF EXISTS {tbl}")
        except Exception:
            pass
        self.registered_tables.clear()

    def close(self):
        self.conn.close()
