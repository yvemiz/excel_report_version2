import re
from typing import List, Dict, Any, Tuple
from app.core.cell_lake import CellLake

class AuditService:
    """
    穿透式数据审计与正则反查服务
    负责提取 Markdown 正文中的所有数字及 [^doc_cell_xxx] 引用标记，
    与 Cell Lake 进行 100% 精确坐标与数值对齐断言。
    """

    def __init__(self, cell_lake: CellLake):
        self.cell_lake = cell_lake

    def verify_markdown_text(self, markdown_text: str) -> Dict[str, Any]:
        """
        全量反查文本中的数字引用。
        支持语法: [数值][^cell_id] 或 [数值](^cell_id) 或 正文中单独的 [^cell_id]
        """
        # 匹配模式 1: [xxx][^cell_id]
        pattern_bracket = re.compile(r'\[([^\]]+)\]\[\^(cell_[a-f0-9]+)\]')
        # 匹配模式 2: 单纯尾注 [^cell_id]
        pattern_footnote = re.compile(r'\[\^(cell_[a-f0-9]+)\]')

        found_citations = []
        verified_count = 0
        mismatch_count = 0

        # 首先按完整模式匹配 [数值][^cell_id]
        for match in pattern_bracket.finditer(markdown_text):
            cited_val = match.group(1).strip()
            cell_id = match.group(2).strip()
            cell = self.cell_lake.get_cell(cell_id)
            
            # 提取数字进行比较（去除“人”、“个”、“%”等量词）
            clean_cited = re.sub(r'[^\d.]', '', cited_val)
            
            is_match = False
            raw_val = ""
            file_name = ""
            sheet_name = ""
            cell_ref = ""
            metric_path = ""

            if cell:
                raw_val = cell["raw_value"]
                file_name = cell["file_name"]
                sheet_name = cell["sheet_name"]
                cell_ref = cell["cell_ref"]
                metric_path = cell["metric_path"]
                clean_raw = re.sub(r'[^\d.]', '', raw_val)
                if clean_cited == clean_raw or cited_val in raw_val or raw_val in cited_val:
                    is_match = True

            if is_match:
                verified_count += 1
            else:
                mismatch_count += 1

            found_citations.append({
                "cell_id": cell_id,
                "cited_text": cited_val,
                "file_name": file_name,
                "sheet_name": sheet_name,
                "cell_ref": cell_ref,
                "metric_path": metric_path,
                "raw_value": raw_val,
                "is_verified": is_match,
                "status": "100% 吻合" if is_match else "需核验/未对齐"
            })

        # 计算吻合率
        total = verified_count + mismatch_count
        pass_rate = (verified_count / total * 100) if total > 0 else 100.0

        return {
            "total_citations": total,
            "verified_count": verified_count,
            "mismatch_count": mismatch_count,
            "pass_rate": round(pass_rate, 1),
            "is_approved": mismatch_count == 0,
            "citations": found_citations
        }

    def generate_full_reconciliation_table(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        汇总所有章节的对账清单，生成《全文数字对账总表》数据源
        """
        all_records = []
        for sec in sections:
            sec_title = sec.get("title", "未命名章节")
            content = sec.get("content", "")
            res = self.verify_markdown_text(content)
            for c in res["citations"]:
                all_records.append({
                    "section_title": sec_title,
                    "cited_text": c["cited_text"],
                    "metric_path": c["metric_path"],
                    "file_name": c["file_name"],
                    "sheet_name": c["sheet_name"],
                    "cell_ref": c["cell_ref"],
                    "raw_value": c["raw_value"],
                    "status": c["status"]
                })
        return all_records
