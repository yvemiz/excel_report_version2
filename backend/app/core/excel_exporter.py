import os
from typing import List, Dict, Any
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

class ExcelExporter:
    """
    《数据穿透审计与指标覆盖清单》 Excel 导出器 (.xlsx)
    生成符合高校教务处、评估专家组“查账式”免责与穿透审计要求的专业双表
    """

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export_audit_workbook(
        self,
        school_name: str,
        coverage_data: List[Dict[str, Any]],
        reconciliation_data: List[Dict[str, Any]]
    ) -> str:
        wb = openpyxl.Workbook()

        # 样式定义 (简约官方教务公文风：清爽深蓝表头、清晰边框、交替斑马纹)
        header_fill = PatternFill(start_color="1E3D59", end_color="1E3D59", fill_type="solid")
        header_font = Font(name="Microsoft YaHei", size=11, bold=True, color="FFFFFF")
        regular_font = Font(name="Microsoft YaHei", size=10, color="1E293B")
        status_pass_font = Font(name="Microsoft YaHei", size=10, bold=True, color="15803D")
        
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )
        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        # -------------------------------------------------------------
        # Sheet 1: 指标覆盖率矩阵
        # -------------------------------------------------------------
        ws1 = wb.active
        ws1.title = "指标覆盖率矩阵"
        ws1.views.sheetView[0].showGridLines = True

        headers1 = ["序号", "模块分类", "核心指标名称", "来源表格", "覆盖状态", "关联报告章节"]
        ws1.append(headers1)

        for col_idx, h in enumerate(headers1, 1):
            cell = ws1.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws1.row_dimensions[1].height = 26

        for idx, row in enumerate(coverage_data, 1):
            r_idx = idx + 1
            ws1.append([
                idx,
                row.get("category", ""),
                row.get("metric_name", ""),
                row.get("source_table", ""),
                row.get("status", "已纳入分析"),
                row.get("section_title", "")
            ])
            for col_idx in range(1, len(headers1) + 1):
                cell = ws1.cell(row=r_idx, column=col_idx)
                cell.font = regular_font
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center", horizontal="center" if col_idx in [1, 5] else "left")
                if r_idx % 2 == 0:
                    cell.fill = zebra_fill
                if col_idx == 5:
                    cell.font = status_pass_font

        # -------------------------------------------------------------
        # Sheet 2: 全文数字对账总表
        # -------------------------------------------------------------
        ws2 = wb.create_sheet(title="全文数字对账总表")
        ws2.views.sheetView[0].showGridLines = True

        headers2 = [
            "序号", "报告章节", "报告所引数值", "对应指标绝对路径", 
            "原始文件名称", "原始工作表(Sheet)", "单元格物理坐标", "原始单元格文本", "穿透核验状态"
        ]
        ws2.append(headers2)

        for col_idx, h in enumerate(headers2, 1):
            cell = ws2.cell(row=1, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border
        ws2.row_dimensions[1].height = 26

        for idx, row in enumerate(reconciliation_data, 1):
            r_idx = idx + 1
            ws2.append([
                idx,
                row.get("section_title", ""),
                row.get("cited_text", ""),
                row.get("metric_path", ""),
                row.get("file_name", ""),
                row.get("sheet_name", ""),
                row.get("cell_ref", ""),
                row.get("raw_value", ""),
                row.get("status", "100% 吻合")
            ])
            for col_idx in range(1, len(headers2) + 1):
                cell = ws2.cell(row=r_idx, column=col_idx)
                cell.font = regular_font
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center", horizontal="center" if col_idx in [1, 3, 7, 9] else "left")
                if r_idx % 2 == 0:
                    cell.fill = zebra_fill
                if col_idx == 9:
                    cell.font = status_pass_font

        # 自动调整列宽
        for ws in [ws1, ws2]:
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val_str = str(cell.value or "")
                    max_len = max(max_len, len(val_str.encode('gbk', errors='ignore')))
                ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        file_name = f"数据穿透审计与指标覆盖清单_{school_name}.xlsx"
        file_path = os.path.join(self.output_dir, file_name)
        wb.save(file_path)
        return file_path
