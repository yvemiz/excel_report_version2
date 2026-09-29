import os
import hashlib
from typing import List, Dict, Any, Tuple
import xlrd
import openpyxl

class STCParser:
    """
    STC 复合表头结构感知解析器 (Structure-Aware Table Header Parser)
    支持 .xls 与 .xlsx 格式：
    1. 自动解析跨行、跨列合并单元格 (Merged Cells) 并执行前向填充 (Forward Fill)
    2. 展开多级复合表头，拼接唯一指标绝对路径 (例: 师资队伍 > 职称结构 > 正高级)
    3. 提取单元格精确定位物理坐标 (file, sheet, row, col, cell_ref, value)
    4. 计算模板指纹 (Template Fingerprint) 实现同构报表归一化
    """

    @staticmethod
    def col_idx_to_name(col_idx: int) -> str:
        """将 0-indexed 列号转换为 Excel 字母列名 (0 -> A, 27 -> AB)"""
        col_str = ""
        col_idx += 1
        while col_idx > 0:
            col_idx, remainder = divmod(col_idx - 1, 26)
            col_str = chr(65 + remainder) + col_str
        return col_str

    @classmethod
    def parse_file(cls, file_path: str) -> List[Dict[str, Any]]:
        """解析 Excel 文件（支持多 Sheet），返回每个 Sheet 的解析结果"""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".xls":
            return cls._parse_xls(file_path)
        elif ext == ".xlsx":
            return cls._parse_xlsx(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}，仅支持 .xls 与 .xlsx")

    @classmethod
    def _parse_xls(cls, file_path: str) -> List[Dict[str, Any]]:
        results = []
        book = xlrd.open_workbook(file_path, formatting_info=True)
        file_name = os.path.basename(file_path)

        for sheet_idx in range(book.nsheets):
            sheet = book.sheet_by_index(sheet_idx)
            if sheet.nrows == 0 or sheet.ncols == 0:
                continue

            # 检测表头行数（高校报表通常第0行为表头，或者前1~2行复合表头）
            # 简单启发式：检测前3行是否有合并单元格或字符占比
            header_row_count = cls._detect_header_row_count_xls(sheet)
            
            # 解析表头矩阵并合并绝对路径
            header_paths = cls._resolve_headers_xls(sheet, header_row_count)
            
            # 计算模板指纹
            fingerprint = cls._compute_fingerprint(sheet.name, header_paths)
            
            # 解析所有数据单元格与数据行
            rows_data = []
            cells_data = []

            for r in range(header_row_count, sheet.nrows):
                row_dict = {}
                for c in range(sheet.ncols):
                    val = sheet.cell_value(r, c)
                    # 格式化数字与文本
                    if isinstance(val, float) and val.is_integer():
                        val = int(val)
                    val_str = str(val).strip() if val is not None else ""
                    
                    metric_path = header_paths[c] if c < len(header_paths) else f"Col_{c}"
                    col_name = cls.col_idx_to_name(c)
                    cell_ref = f"{col_name}{r + 1}"
                    cell_id = f"cell_{hashlib.md5(f'{file_name}_{sheet.name}_{cell_ref}'.encode()).hexdigest()[:12]}"
                    
                    row_dict[metric_path] = val
                    
                    cells_data.append({
                        "cell_id": cell_id,
                        "file_name": file_name,
                        "sheet_name": sheet.name,
                        "row_idx": r + 1,
                        "col_idx": c + 1,
                        "cell_ref": cell_ref,
                        "metric_path": metric_path,
                        "raw_value": val_str,
                        "numeric_value": float(val) if isinstance(val, (int, float)) else None
                    })
                rows_data.append(row_dict)

            results.append({
                "file_name": file_name,
                "file_path": file_path,
                "sheet_name": sheet.name,
                "fingerprint": fingerprint,
                "header_paths": header_paths,
                "row_count": len(rows_data),
                "col_count": sheet.ncols,
                "rows": rows_data,
                "cells": cells_data
            })

        return results

    @classmethod
    def _parse_xlsx(cls, file_path: str) -> List[Dict[str, Any]]:
        results = []
        wb = openpyxl.load_workbook(file_path, data_only=True)
        file_name = os.path.basename(file_path)

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            if ws.max_row is None or ws.max_row == 0 or ws.max_column is None or ws.max_column == 0:
                continue

            # 检测表头行数（支持跨行跨列复合多行表头）
            header_row_count = cls._detect_header_row_count_xlsx(ws)

            # 解析表头矩阵并合并绝对路径
            header_paths = cls._resolve_headers_xlsx(ws, header_row_count)

            # 计算模板指纹
            fingerprint = cls._compute_fingerprint(sheet_name, header_paths)
            rows_data = []
            cells_data = []

            # 建立合并单元格查找表，以支持跨行跨列单元格取值
            merged_lookup: Dict[Tuple[int, int], Any] = {}
            for rng in ws.merged_cells.ranges:
                top_left_val = ws.cell(row=rng.min_row, column=rng.min_col).value
                for r in range(rng.min_row, rng.max_row + 1):
                    for c in range(rng.min_col, rng.max_col + 1):
                        merged_lookup[(r, c)] = top_left_val

            for r in range(header_row_count + 1, ws.max_row + 1):
                row_dict = {}
                for c in range(1, ws.max_column + 1):
                    val = merged_lookup.get((r, c), ws.cell(row=r, column=c).value)
                    if isinstance(val, float) and val.is_integer():
                        val = int(val)
                    val_str = str(val).strip() if val is not None else ""
                    metric_path = header_paths[c - 1] if c - 1 < len(header_paths) else f"Col_{c}"
                    col_name = cls.col_idx_to_name(c - 1)
                    cell_ref = f"{col_name}{r}"
                    cell_id = f"cell_{hashlib.md5(f'{file_name}_{sheet_name}_{cell_ref}'.encode()).hexdigest()[:12]}"

                    row_dict[metric_path] = val
                    cells_data.append({
                        "cell_id": cell_id,
                        "file_name": file_name,
                        "sheet_name": sheet_name,
                        "row_idx": r,
                        "col_idx": c,
                        "cell_ref": cell_ref,
                        "metric_path": metric_path,
                        "raw_value": val_str,
                        "numeric_value": float(val) if isinstance(val, (int, float)) else None
                    })
                rows_data.append(row_dict)

            results.append({
                "file_name": file_name,
                "file_path": file_path,
                "sheet_name": sheet_name,
                "fingerprint": fingerprint,
                "header_paths": header_paths,
                "row_count": len(rows_data),
                "col_count": ws.max_column,
                "rows": rows_data,
                "cells": cells_data
            })

        return results

    @classmethod
    def _detect_header_row_count_xlsx(cls, ws) -> int:
        """根据 openpyxl 合并单元格感知表头行数，支持跨行复合表头"""
        if ws.max_row is None or ws.max_row <= 1:
            return 1
        max_h = 1
        for rng in ws.merged_cells.ranges:
            if rng.min_row == 1 and rng.max_row > 1:
                max_h = max(max_h, rng.max_row)
        return min(max_h, 4)

    @classmethod
    def _resolve_headers_xlsx(cls, ws, header_row_count: int) -> List[str]:
        """合并 xlsx 跨行跨列表头为唯一绝对指标路径 (A > B > C)"""
        ncols = ws.max_column or 1
        if header_row_count == 1:
            headers = []
            for c in range(1, ncols + 1):
                val = ws.cell(row=1, column=c).value
                headers.append(str(val).strip() if val is not None else f"Col_{c}")
            return headers

        grid = [["" for _ in range(ncols)] for _ in range(header_row_count)]
        for r in range(1, header_row_count + 1):
            for c in range(1, ncols + 1):
                v = ws.cell(row=r, column=c).value
                grid[r - 1][c - 1] = str(v).strip() if v is not None else ""

        # 填充合并区域前向值
        for rng in ws.merged_cells.ranges:
            if rng.min_row <= header_row_count:
                top_left_val = str(ws.cell(row=rng.min_row, column=rng.min_col).value or "").strip()
                r_start = rng.min_row - 1
                r_end = min(rng.max_row, header_row_count)
                c_start = rng.min_col - 1
                c_end = min(rng.max_col, ncols)
                for r in range(r_start, r_end):
                    for c in range(c_start, c_end):
                        grid[r][c] = top_left_val

        # 拼接绝对路径 (A > B > C)
        combined_headers = []
        for c in range(ncols):
            path_parts = []
            for r in range(header_row_count):
                part = grid[r][c]
                if part and (not path_parts or path_parts[-1] != part):
                    path_parts.append(part)
            combined_headers.append(" > ".join(path_parts) if path_parts else f"Col_{c+1}")

        return combined_headers

    @classmethod
    def _detect_header_row_count_xls(cls, sheet) -> int:
        """根据合并单元格和数据行判断表头行数，默认通常为 1 行"""
        if sheet.nrows <= 1:
            return 1
        # 检查前两行是否有跨行合并
        for crange in sheet.merged_cells:
            rlo, rhi, clo, chi = crange
            if rlo == 0 and rhi > 1:
                return rhi
        return 1

    @classmethod
    def _resolve_headers_xls(cls, sheet, header_row_count: int) -> List[str]:
        """合并跨行跨列表头为单层绝对路径"""
        if header_row_count == 1:
            headers = []
            for c in range(sheet.ncols):
                val = sheet.cell_value(0, c)
                headers.append(str(val).strip() if val is not None else f"Col_{c+1}")
            return headers

        # 多行表头展开与填充
        grid = [["" for _ in range(sheet.ncols)] for _ in range(header_row_count)]
        for r in range(header_row_count):
            for c in range(sheet.ncols):
                grid[r][c] = str(sheet.cell_value(r, c)).strip()

        # 填充合并区域
        for crange in sheet.merged_cells:
            rlo, rhi, clo, chi = crange
            if rlo < header_row_count:
                fill_val = str(sheet.cell_value(rlo, clo)).strip()
                for r in range(rlo, min(rhi, header_row_count)):
                    for c in range(clo, chi):
                        grid[r][c] = fill_val

        # 拼接绝对路径 (A > B > C)
        combined_headers = []
        for c in range(sheet.ncols):
            path_parts = []
            for r in range(header_row_count):
                part = grid[r][c]
                if part and (not path_parts or path_parts[-1] != part):
                    path_parts.append(part)
            combined_headers.append(" > ".join(path_parts) if path_parts else f"Col_{c+1}")

        return combined_headers

    @staticmethod
    def _compute_fingerprint(sheet_name: str, headers: List[str]) -> str:
        """根据 Sheet 名和表头生成 16 位哈希指纹"""
        sig = f"{sheet_name}::" + "||".join(headers)
        return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def parse_directory(cls, dir_path: str, recursive: bool = True, max_workers: int = 8) -> List[Dict[str, Any]]:
        """
        批量并发扫描并解析指定本地目录中的所有 Excel 报表 (.xls / .xlsx)
        支持多达 500+ 个文件的并行解析，耗时大幅压缩
        """
        if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            raise FileNotFoundError(f"指定的目录不存在: {dir_path}")

        matched_files = []
        if recursive:
            for root, _, files in os.walk(dir_path):
                for f in files:
                    if f.lower().endswith((".xls", ".xlsx")) and not f.startswith("~$"):
                        matched_files.append(os.path.join(root, f))
        else:
            for f in os.listdir(dir_path):
                if f.lower().endswith((".xls", ".xlsx")) and not f.startswith("~$"):
                    matched_files.append(os.path.join(dir_path, f))

        if not matched_files:
            return []

        all_parsed_tables = []
        from concurrent.futures import ThreadPoolExecutor
        workers = min(max_workers, len(matched_files), os.cpu_count() or 4)
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_file = {executor.submit(cls.parse_file, fp): fp for fp in matched_files}
            for future in future_to_file:
                fp = future_to_file[future]
                try:
                    tables = future.result()
                    all_parsed_tables.extend(tables)
                except Exception as e:
                    print(f"[!] 批量解析文件失败: {fp}, 错误: {e}")

        return all_parsed_tables
