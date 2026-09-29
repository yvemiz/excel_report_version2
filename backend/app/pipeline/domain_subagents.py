"""
Domain Specialist Subagents Architecture
Inspired by pi-subagents and @quintinshaw/pi-dynamic-workflows official paradigms.
Partitions the 100+ pages of academic evaluation reports into 5 specialized Subagent Roles:
1. OverviewSpecialist (办学定位与综合概况专员)
2. FacultySpecialist (师资队伍与人力资源专员)
3. DisciplineSpecialist (学科建设与研究生教育专员)
4. UndergraduateSpecialist (本科教学与一流专业专员)
5. ResearchSpecialist (科研创新与综合保障专员)
"""

from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class DomainSubagent:
    role_id: str
    role_name: str
    title: str
    preferred_chart: str
    domain_keywords: List[str]
    system_instruction: str

class SubagentRouter:
    """
    Subagent 角色智能路由器与工作流分发器
    根据章节元数据与指标意图，将任务精准派发给五大专属领域专家智能体
    """

    SUBAGENTS: Dict[str, DomainSubagent] = {
        "overview": DomainSubagent(
            role_id="overview",
            role_name="OverviewSpecialist",
            title="办学定位与综合概况专家",
            preferred_chart="bar",
            domain_keywords=["概况", "定位", "历史", "办学", "基本情况", "校区", "性质", "代码", "1_1", "1-1"],
            system_instruction="""
【专业领域约束 - 办学定位与综合概况】
你专精于高等教育宏观发展规划与综合办学概况分析。
写作基调：宏观稳健、定调高远、提纲挈领。
重点论述：学校办学历史沿革、教育部院校代码、办学性质与归属层次、多校区物理布局以及中长期发展规划愿景。
严禁空洞套话，所有高校代码、占地面积、在校生体量等核心指标必须严格溯源打标 [数值][^cell_id]。
"""
        ),
        "faculty": DomainSubagent(
            role_id="faculty",
            role_name="FacultySpecialist",
            title="师资队伍与人力资源专家",
            preferred_chart="pie",
            domain_keywords=["师资", "教师", "队伍", "职称", "学历", "博士", "生师比", "人员", "机构", "1_2", "1_3", "1-2", "1-3"],
            system_instruction="""
【专业领域约束 - 师资队伍与人力资源】
你专精于高校师资队伍建设、引育结构与教师专业发展评估。
写作基调：人才强校、梯队合理、内涵深厚。
重点论述：专任教师总量、高职称（教授/副教授）分布、博士硕士学位占比、具有海外研修经历比例以及本科生师比演进。
善于通过横向结构（职称比率）与纵向动态分析师资质量，数据指标严谨打标 [数值][^cell_id]。
"""
        ),
        "discipline": DomainSubagent(
            role_id="discipline",
            role_name="DisciplineSpecialist",
            title="学科建设与研究生教育专家",
            preferred_chart="column",
            domain_keywords=["学科", "学位点", "博士后", "硕士点", "一级学科", "流动站", "研究生", "4_1", "4-1"],
            system_instruction="""
【专业领域约束 - 学科建设与研究生教育】
你专精于高校高峰高原学科建设与高层次学位授权体系评价。
写作基调：学科攀登、交叉融合、梯次明晰。
重点论述：博士后科研流动站、一级学科博士硕士学位授权点、专业学位类别以及重点学科在教育部评估中的表现。
鼓励在正文中内嵌 Mermaid 流程图展现学科授权演进脉络，每个学位点数量均附带 [数值][^cell_id]。
"""
        ),
        "undergraduate": DomainSubagent(
            role_id="undergraduate",
            role_name="UndergraduateSpecialist",
            title="本科教学与一流专业专家",
            preferred_chart="bar",
            domain_keywords=["专业", "大类", "培养", "一流专业", "双万", "课程", "教学", "认证", "1_4", "4_3", "1-4", "4-3"],
            system_instruction="""
【专业领域约束 - 本科教学与一流专业】
你专精于本科专业动态调整机制、“双万计划”一流本科专业建设点及拔尖人才培养模式。
写作基调：立德树人、质量保障、内涵提升。
重点论述：本科专业总数、大类招生比例、国家级与省级一流专业立项进度、工程/师范专业认证通过率。
必须具体点名代表性一流专业建设成效，并为每个专业指标打上真实坐标 [专业名][^cell_id]。
"""
        ),
        "research": DomainSubagent(
            role_id="research",
            role_name="ResearchSpecialist",
            title="科研创新与综合保障专家",
            preferred_chart="line",
            domain_keywords=["科研", "经费", "平台", "实验室", "仪器", "资产", "图书", "课题", "成果", "经费"],
            system_instruction="""
【专业领域约束 - 科研创新与综合保障】
你专精于高校科研成果转化、科研平台基地与教学科研基础设施综合保障评估。
写作基调：创新驱动、产教融合、支撑坚实。
重点论述：年度到账科研经费总额与人均值、国家级与省部级重点实验室、教学科研仪器设备总值、生均图书资产。
精准梳理各项办学支撑硬件与创新成果，全量标注 [数值][^cell_id]。
"""
        )
    }

    @classmethod
    def route(cls, section_meta: Dict[str, Any]) -> DomainSubagent:
        """
        根据小节标题、研究目标与绑定表名，自动选定最优 Domain Subagent
        """
        title = section_meta.get("section_title", "")
        chapter = section_meta.get("chapter_title", "")
        objective = section_meta.get("objective", "")
        table_kw = section_meta.get("table_keyword", "")
        full_text = f"{title} {chapter} {objective} {table_kw}".lower()

        best_subagent = cls.SUBAGENTS["overview"]
        best_score = -1

        for role_id, agent in cls.SUBAGENTS.items():
            score = 0
            for kw in agent.domain_keywords:
                if kw.lower() in full_text:
                    score += 2
            if score > best_score:
                best_score = score
                best_subagent = agent

        return best_subagent
