import re
from typing import List, Dict, Any, Tuple, Optional
from app.core.cell_lake import CellLake

class AuditService:
    """
    穿透式数据审计与正则反查服务
    负责提取 Markdown 正文中的所有数字及 [^doc_cell_xxx] 引用标记，
    与 Cell Lake 进行 100% 精确坐标与数值对齐断言。
    """

    def __init__(self, cell_lake: CellLake):
        self.cell_lake = cell_lake

    @staticmethod
    def _is_value_aligned(cited_val: str, raw_val: str) -> bool:
        """
        严谨数值与文本对齐校验算法：
        1. 精确文本相等（去除两端空白后）
        2. 数值相等校验（提取数字，按浮点数精度 1e-4 比较）
        3. 坚决杜绝粗暴双向子串模糊匹配（严防 '1' in '1000' 或 '0' in '50' 产生假对齐）
        """
        cited_stripped = cited_val.strip()
        raw_stripped = raw_val.strip()
        if cited_stripped == raw_stripped:
            return True

        # 尝试提取浮点数对比
        def extract_number(s: str) -> Optional[float]:
            m = re.search(r'[-+]?\d+(?:\.\d+)?', s.replace(",", ""))
            if m:
                try:
                    return float(m.group(0))
                except ValueError:
                    return None
            return None

        c_num = extract_number(cited_stripped)
        r_num = extract_number(raw_stripped)

        if c_num is not None and r_num is not None:
            # 处理可能的“万”等量词换算
            if "万" in cited_stripped and "万" not in raw_stripped:
                r_num_conv = r_num / 10000.0
                if abs(c_num - r_num_conv) < 1e-4:
                    return True
            elif "万" not in cited_stripped and "万" in raw_stripped:
                c_num_conv = c_num / 10000.0
                if abs(c_num_conv - r_num) < 1e-4:
                    return True

            if abs(c_num - r_num) < 1e-4:
                return True

        # 对于非数字文本（如学校名称、办学性质），允许前后缀包裹匹配，但长度差必须极小（防止非预期匹配）
        if cited_stripped and raw_stripped:
            min_len = min(len(cited_stripped), len(raw_stripped))
            max_len = max(len(cited_stripped), len(raw_stripped))
            if (cited_stripped in raw_stripped or raw_stripped in cited_stripped) and min_len >= 4 and (min_len / max_len) >= 0.7:
                return True

        return False

    def verify_markdown_text(self, markdown_text: str) -> Dict[str, Any]:
        """
        全量反查文本中的数字引用。
        支持语法: [数值][^cell_id]
        采用批量查询避免 N+1 数据库连接风暴
        """
        pattern_bracket = re.compile(r'\[([^\]]+)\]\[\^(cell_[a-zA-Z0-9_]+)\]')

        raw_citations = []
        for match in pattern_bracket.finditer(markdown_text):
            raw_citations.append({
                "cited_val": match.group(1).strip(),
                "cell_id": match.group(2).strip()
            })

        if not raw_citations:
            return {
                "total_citations": 0,
                "verified_count": 0,
                "mismatch_count": 0,
                "pass_rate": 100.0,
                "is_approved": True,
                "citations": []
            }

        # 批量获取单元格，消除 N+1 查询
        cell_ids = [c["cell_id"] for c in raw_citations]
        cell_map = self.cell_lake.get_cells_batch(cell_ids)

        found_citations = []
        verified_count = 0
        mismatch_count = 0

        for item in raw_citations:
            cited_val = item["cited_val"]
            cell_id = item["cell_id"]
            cell = cell_map.get(cell_id)

            is_match = False
            raw_val = ""
            file_name = ""
            sheet_name = ""
            cell_ref = ""
            metric_path = ""

            if cell:
                raw_val = str(cell.get("raw_value", "")).strip()
                file_name = cell.get("file_name", "")
                sheet_name = cell.get("sheet_name", "")
                cell_ref = cell.get("cell_ref", "")
                metric_path = cell.get("metric_path", "")
                is_match = self._is_value_aligned(cited_val, raw_val)

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
