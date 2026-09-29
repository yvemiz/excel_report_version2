import json
from typing import Dict, Any, Optional, List
import httpx
from app.config import settings

class JevJudge:
    """
    Jev 极速决策与质检模型 (Jev Classifier / Local Judge)
    专职负责对章节初稿进行快速打分 (Score: 0~1.0) 与主观臆断判定 (Clean / Unsupported)，
    提供毫秒级、免多 Agent 争执的确定性质量把关。
    """

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.base_url = base_url or settings.DEEPSEEK_BASE_URL
        self.model = model or settings.JUDGE_MODEL

    async def evaluate_section(
        self,
        section_title: str,
        retrieved_data: Dict[str, Any],
        draft_content: str
    ) -> Dict[str, Any]:
        """
        评估小节质量。若无 API KEY，执行高可靠规则判定与离散断言。
        """
        # 如果未配置 API Key，执行高保真本地断言引擎
        if not self.api_key or self.api_key.startswith("your_"):
            return self._local_rule_evaluation(section_title, retrieved_data, draft_content)

        prompt = f"""你是一名严苛的高等教育教学评估委员会质检专家（Judge）。
请严格依据以下输入，对报告章节进行质量裁定：

# 评估章节：{section_title}
# 唯一依据事实数据：
{json.dumps(retrieved_data, ensure_ascii=False)[:3000]}

# 章节初稿正文：
{draft_content[:6000]}

请仅返回标准 JSON，不要任何前言后记：
{{
  "logic_consistency": 0.95, // 0.0 - 1.0 的连续打分，分析推导是否严密自洽
  "has_unsupported_claims": false, // 是否存在缺乏数据依据的主观臆测
  "rejection_reason": "" // 若未通过给出极其精简的驳回理由，通过则为空
}}
"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一名精通教育公文的评估质检专家。严格输出 JSON。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    res = json.loads(content)
                    score = float(res.get("logic_consistency", 0.9))
                    is_clean = not bool(res.get("has_unsupported_claims", False))
                    reason = res.get("rejection_reason", "")
                    return {
                        "logic_score": score,
                        "is_clean": is_clean,
                        "approved": (score >= 0.85 and is_clean),
                        "rejection_reason": reason,
                        "provider": "deepseek-judge"
                    }
        except Exception as e:
            pass

        return self._local_rule_evaluation(section_title, retrieved_data, draft_content)

    def _local_rule_evaluation(self, section_title: str, retrieved_data: Dict[str, Any], draft_content: str) -> Dict[str, Any]:
        """本地启发式断言引擎（保障即使离线/无网络也能瞬间完成质检）"""
        score = 0.95
        is_clean = True
        reasons = []

        # 检查字数
        if len(draft_content.strip()) < 100:
            score -= 0.3
            is_clean = False
            reasons.append("正文字数过少，论述深度不足")

        # 检查是否有溯源锚点
        if "[^cell_" not in draft_content:
            score -= 0.2
            reasons.append("正文未打标数据溯源锚点 [^cell_id]")

        # 检查是否包含虚词空话
        bad_words = ["遥遥领先", "无可匹敌", "史上最强"]
        for bw in bad_words:
            if bw in draft_content:
                score -= 0.15
                is_clean = False
                reasons.append(f"包含非严谨辞令: '{bw}'")

        score = max(0.1, min(1.0, round(score, 2)))
        return {
            "logic_score": score,
            "is_clean": is_clean,
            "approved": (score >= 0.85 and is_clean),
            "rejection_reason": "；".join(reasons) if reasons else "",
            "provider": "jev-deterministic-rules"
        }

    async def evaluate_outline(
        self,
        outline: List[Dict[str, Any]],
        catalog: List[Dict[str, Any]],
        school_name: str = ""
    ) -> Dict[str, Any]:
        """
        Stage 1 Jev 大纲质量把关与合规审判
        评估维度：
        1. 覆盖度 (Coverage): 是否全面覆盖高校教育评估核心要素
        2. 绑定合理性 (Binding Rationality): 各小节绑定的表格是否精准切题
        3. 粒度合理性 (Granularity): 章节深度与数据量是否匹配
        """
        if not self.api_key or self.api_key.startswith("your_"):
            return self._local_outline_evaluation(outline, catalog, school_name)

        outline_summary = [
            {
                "id": s.get("id"),
                "chapter_title": s.get("chapter_title"),
                "section_title": s.get("section_title"),
                "bound_tables": s.get("bound_tables", [s.get("table_name")]),
                "bound_files": s.get("bound_files", [s.get("file_name")]),
                "chart": bool(s.get("chart_plan"))
            }
            for s in outline
        ]

        prompt = f"""你是一名严苛的高等教育质量常态监测评估大纲质检裁判（Jev Judge）。
请对为高校【{school_name or '普通高等学校'}】规划的报告大纲进行合规性、表绑定合理性与结构自适应粒度把关：

# 已规划大纲结构：
{json.dumps(outline_summary, ensure_ascii=False, indent=2)[:5000]}

# 数据湖表格总数：{len(catalog)} 个

请返回严格合法的 JSON 对象：
{{
  "structure_score": 0.95, // 0.0 - 1.0 的连续评分，结构严谨性与覆盖度
  "is_approved": true, // 是否批准放行进入正文撰写 (>= 0.85 且无重大缺陷为 true)
  "has_unbound_sections": false, // 是否存在脱离数据湖的空想小节
  "critique": "" // 若未通过给出具体整改建议，通过则给出精炼简评
}}"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一名精通高校评估公文体系的 Jev 质检裁判模型。严格输出 JSON。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.post(f"{self.base_url.rstrip('/')}/chat/completions", json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    res = json.loads(data["choices"][0]["message"]["content"])
                    score = float(res.get("structure_score", 0.92))
                    approved = bool(res.get("is_approved", score >= 0.85))
                    return {
                        "structure_score": score,
                        "is_approved": approved,
                        "critique": res.get("critique", "大纲架构符合教育部常态监测公文规范"),
                        "provider": "deepseek-jev-outline"
                    }
        except Exception:
            pass

        return self._local_outline_evaluation(outline, catalog, school_name)

    def _local_outline_evaluation(
        self,
        outline: List[Dict[str, Any]],
        catalog: List[Dict[str, Any]],
        school_name: str = ""
    ) -> Dict[str, Any]:
        """本地启发式大纲规则断言"""
        score = 0.96
        critiques = []

        if len(outline) < 3:
            score -= 0.3
            critiques.append("大纲章节偏少，未能充分体现办学多维发展特征")

        # 检查是否有未绑定数据表的小节
        catalog_tables = {c["table_name"] for c in catalog}
        unbound_cnt = 0
        for s in outline:
            b_tables = s.get("bound_tables") or ([s.get("table_name")] if s.get("table_name") else [])
            if not b_tables or not any(bt in catalog_tables for bt in b_tables):
                unbound_cnt += 1

        if catalog and unbound_cnt > len(outline) * 0.3:
            score -= 0.25
            critiques.append(f"存在 {unbound_cnt} 个小节未精准锚定底层物理表格")

        score = max(0.1, min(1.0, round(score, 2)))
        return {
            "structure_score": score,
            "is_approved": score >= 0.85,
            "critique": "；".join(critiques) if critiques else "大纲覆盖全面，数据表绑定清晰，分节粒度自适应良好",
            "provider": "jev-deterministic-outline"
        }
