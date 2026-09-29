"""
Jev Prompt Enhancer & Structured Output Enforcer
Inspired by @hikae/pi-prompt-enhancer and @zhushanwen/pi-structured-output official standards.
1. Evaluates raw prompts using Jev decision rules, reports gap score, and auto-injects patches
2. Strictly enforces structured Markdown output and auto-repairs malformed citation anchors
"""

import re
from typing import Dict, Any, List, Tuple

class JevPromptEnhancer:
    """
    基于 TypeSafe Jev 决策准则的工程化 Prompt 增强器
    在向大模型发送请求前前置执行质检预检，自动补齐防幻觉与公文规范约束
    """

    CRITERIA = [
        {
            "id": "citation_anchor_rule",
            "name": "单元格精准溯源打标约束",
            "pattern": r"\[\^?cell_[a-zA-Z0-9_]+\]",
            "weight": 30,
            "patch": "\n【质检强制约束 - 严苛数据溯源】：正文中出现的每一个量化指标、统计数值或特定单位名称，必须紧随物理单元格溯源锚点：`[具体数值或名称][^cell_id]`。严禁出现无锚点的孤立数据！"
        },
        {
            "id": "tripartite_structure_rule",
            "name": "公文三段论论述结构约束",
            "pattern": r"现状|特征|建议|结构",
            "weight": 25,
            "patch": "\n【质检强制约束 - 结构范式】：本小节必须遵循高校评估公文标准三段论逻辑推进：第一阶段‘基础现状量化陈述’；第二阶段‘建设成效与核心特征提炼’；第三阶段‘潜在短板与后续优化建议’。"
        },
        {
            "id": "anti_hallucination_rule",
            "name": "负向防编造与事实对齐约束",
            "pattern": r"严禁编造|客观真实|据实论述",
            "weight": 20,
            "patch": "\n【质检强制约束 - 严禁臆造】：严禁编造、擅自外推或估计任何统计数字！如未在数据湖中查到某个具体指标，请客观陈述‘暂未纳入常态监测’，绝对不可虚构数据。"
        },
        {
            "id": "word_count_and_format_rule",
            "name": "标题层级与字数底线约束",
            "pattern": r"###|字数不少于|Markdown",
            "weight": 15,
            "patch": "\n【质检强制约束 - 标题与篇幅】：输出必须以标准 Markdown 三级标题（`### 小节标题`）开头，段落之间空一行，正文饱满厚重，有效分析字数不少于 280 字。"
        },
        {
            "id": "academic_tone_rule",
            "name": "严肃学术与行政公文语体风格",
            "pattern": r"严肃|公文|严密自洽|学术",
            "weight": 10,
            "patch": "\n【质检强制约束 - 语体风格】：采用严谨、客观、典雅的高等教育教学评估公文风格，避免口语化、第一人称代词或文学抒情修辞。"
        }
    ]

    @classmethod
    def enhance(cls, base_prompt: str, domain_subagent_instruction: str = "") -> Dict[str, Any]:
        """
        评判 Prompt 完整度，计算 Jev 质量分并自动补充缺失条款
        """
        score = 0
        passed_rules = []
        missing_patches = []

        for rule in cls.CRITERIA:
            if re.search(rule["pattern"], base_prompt):
                score += rule["weight"]
                passed_rules.append(rule["name"])
            else:
                missing_patches.append(rule["patch"])

        enhanced_text = base_prompt
        if domain_subagent_instruction:
            enhanced_text += f"\n{domain_subagent_instruction}\n"

        if missing_patches:
            enhanced_text += "\n\n# 【Jev 决策模型自动化注入的公文质量补丁】：\n" + "\n".join(missing_patches)

        return {
            "original_prompt": base_prompt,
            "enhanced_prompt": enhanced_text,
            "jev_prompt_score": score,
            "passed_rules": passed_rules,
            "injected_patches_count": len(missing_patches),
            "is_fully_compliant": score >= 90
        }


class StructuredOutputEnforcer:
    """
    结构化输出强校验与自愈拦截器
    校验正文格式、修补非标准引用语法，并确保 Markdown 标题与段落规范
    """

    @classmethod
    def validate_and_repair(
        cls,
        raw_text: str,
        expected_title: str,
        valid_cell_ids: List[str] = None
    ) -> Dict[str, Any]:
        """
        校验并自愈模型输出的草稿文本
        """
        if not raw_text or not raw_text.strip():
            return {
                "is_valid": False,
                "repaired_text": f"### {expected_title}\n\n该章节数据正在进一步穿透检索中。",
                "citations_count": 0,
                "repairs_applied": ["空文本兜底补全"]
            }

        text = raw_text.strip()
        repairs = []

        # 1. 确保以 Markdown H3 开头
        if not text.startswith("### "):
            text = f"### {expected_title}\n\n" + text
            repairs.append("自动补全 H3 Markdown 章节主标题")

        # 2. 语法自愈：将非标准的 [数值](cell_xxx) 修复为标准 [数值][^cell_xxx]
        def fix_markdown_link(match):
            val, cid = match.group(1), match.group(2)
            if "cell_" in cid:
                clean_cid = cid.replace("^", "").strip()
                repairs.append(f"修补非标链接语法 [{val}]({cid}) -> [{val}][^{clean_cid}]")
                return f"[{val}][^{clean_cid}]"
            return match.group(0)

        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", fix_markdown_link, text)

        # 3. 语法自愈：将非标准的 数值[^cell_xxx]（漏了数值括号）修复为 [数值][^cell_xxx]
        def fix_missing_brackets(match):
            val, cid = match.group(1), match.group(2)
            repairs.append(f"修补数值外括号 {val}[^{cid}] -> [{val}][^{cid}]")
            return f"[{val}][^{cid}]"

        text = re.sub(r"(?<!\])([0-9]+(?:\.[0-9]+)?[\u4e00-\u9fa5%a-zA-Z]{0,4})\[\^([a-zA-Z0-9_]+)\]", fix_missing_brackets, text)

        # 4. 统计标准引用数量
        citations = re.findall(r"\[([^\]]+)\]\[\^([a-zA-Z0-9_]+)\]", text)
        valid_set = set(valid_cell_ids or [])
        verified_count = 0
        if valid_set:
            for val, cid in citations:
                if cid in valid_set:
                    verified_count += 1
        else:
            verified_count = len(citations)

        return {
            "is_valid": len(citations) > 0 and len(text) >= 150,
            "repaired_text": text,
            "total_citations": len(citations),
            "verified_citations": verified_count,
            "repairs_applied": repairs,
            "word_count": len(text)
        }
