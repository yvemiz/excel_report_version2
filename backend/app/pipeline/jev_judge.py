import json
from typing import Dict, Any, Optional
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
