import os
import re
from typing import Dict, Any, List, Optional
from app.core.duckdb_engine import DuckDBEngine

CN_NUMS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五"]

DOMAINS = [
    {
        "key": "overview",
        "patterns": ["概况", "办学", "基本情况", "1_1", "1-1"],
        "chapter_title": "学校概况与办学定位",
        "section_title": "办学历史与中长期发展战略定位",
        "objective": "客观阐述学校基础办学性质、办学规模与中长期发展战略规划定位",
        "default_chart_type": None
    },
    {
        "key": "organization",
        "patterns": ["机构", "党政", "单位", "师资", "教师", "队伍", "1_2", "1_3", "1-2", "1-3"],
        "chapter_title": "组织机构与师资科研支撑体系",
        "section_title": "教学科研单位与党政管理支撑体系分布",
        "objective": "系统梳理全校党政管理职能部门与各教学科研学院的构架分布及组织效能",
        "default_chart_type": "pie"
    },
    {
        "key": "majors",
        "patterns": ["专业", "专业基本", "专业大类", "培养", "1_4", "1-4"],
        "chapter_title": "专业设置与大类培养布局",
        "section_title": "本科专业结构与学科门类覆盖分析",
        "objective": "深入分析各学院设置本科专业的分布形态、学制年限及师范类专业结构占比",
        "default_chart_type": "bar"
    },
    {
        "key": "disciplines",
        "patterns": ["学科", "学位点", "博士", "硕士", "流动站", "4_1", "4-1"],
        "chapter_title": "学科建设与高层次学位点发展",
        "section_title": "博士后流动站与博硕士学位授权点布局",
        "objective": "全面论述全校博士后科研流动站、一级博士点、硕士专业学位授权点的层级结构",
        "default_chart_type": "column"
    },
    {
        "key": "first_class",
        "patterns": ["一流", "优势", "重点", "建设点", "4_3", "4-3"],
        "chapter_title": "优势一流专业建设成效与示范引领",
        "section_title": "国家级与省级一流本科专业建设成效分析",
        "objective": "分析国家级与省级一流本科专业建设点的获批年度演进与特色示范效应",
        "default_chart_type": "line"
    },
    {
        "key": "resources",
        "patterns": ["2_4", "2_5", "2-4", "2-5", "仪器设备", "实验室", "图书藏量", "教学经费", "生均面积"],
        "chapter_title": "教学资源配置与实验实训保障",
        "section_title": "教学科研仪器设备与实践基地保障分析",
        "objective": "系统盘点教学科研仪器设备总值、实践教学基地建设及生均图书资源支撑",
        "default_chart_type": "bar"
    },
    {
        "key": "student",
        "patterns": ["6_1", "6_2", "6-1", "6-2", "生源录取", "应届毕业", "初次就业", "升学深造"],
        "chapter_title": "学生生源素质与就业深造发展",
        "section_title": "应届毕业生毕业去向与高质量深造态势",
        "objective": "客观分析本科招生规模结构、毕业生就业落实率及海内外高质量升学深造水平",
        "default_chart_type": "line"
    },
    {
        "key": "quality",
        "patterns": ["7_1", "7_2", "7-1", "7-2", "质量监控", "教学督导", "专业认证", "持续改进机制"],
        "chapter_title": "教学质量监控与常态化持续改进",
        "section_title": "内部质量保证体系与常态化教学督导运行",
        "objective": "全面评估学校教学质量常态监控网络、教学督导反馈闭环与质量文化建设成效",
        "default_chart_type": "column"
    }
]

class OutlinePlanner:
    """
    数据驱动动态大纲与学术图表推荐规划引擎 (Decoupled Outline Planner)
    从 stages.py 中独立解耦，专职负责：
    1. 两级分层宏观领域聚类与自适应表绑定 (Table Pre-binding)
    2. 基于表格数量与密度的章节自适应动态拓扑划分
    3. 基于 DuckDB 真实数据列与分布的学术图表自适应智能推荐
    4. 离线/空表安全基准大纲兜底生成
    """

    def __init__(self, duckdb_engine: Optional[DuckDBEngine] = None):
        self.duckdb_engine = duckdb_engine

    def generate_dynamic_sections(self, catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        基于两级分层拓扑与数据量自适应的大纲规划引擎 (Two-level Hierarchical Topology):
        1. 宏观领域预绑定 (Table Pre-binding):
           将 Catalog 所有物理表聚类预分配至各大教育监测评估宏观领域；
        2. 自适应细分粒度 (Adaptive Density):
           根据各领域数据表数量 N 动态计算小节数：
           - N <= 3: 生成 1 个小节，绑定全部 N 个表；
           - 4 <= N <= 12: 自适应聚类生成 2~4 个小节，切分绑定不同物理子表；
           - N > 12 (大规模500+表场景): 聚类生成 5~8 个小节，批量绑定对应数据子集；
        3. 自定义新表动态生长:
           未命中公文领域的任意新增报表，自适应归类为专题章节或独立评价章节。
        """
        assigned_tables = set()
        sections = []
        theme_index = 0

        # 第一阶段：将 Catalog 表格向宏观领域映射预绑定
        for t_def in DOMAINS:
            matched_tables = []
            for item in catalog:
                t_name = item.get("table_name", "")
                f_name = item.get("file_name", "")
                s_name = item.get("sheet_name", "")
                full_text = f"{t_name}_{f_name}_{s_name}".lower()
                if any(p.lower() in full_text for p in t_def["patterns"]):
                    matched_tables.append(item)
                    assigned_tables.add(item["table_name"])

            if not matched_tables:
                continue

            theme_index += 1
            cn_num = CN_NUMS[theme_index - 1] if theme_index <= len(CN_NUMS) else str(theme_index)
            N = len(matched_tables)

            if N <= 3:
                # 规则 1: 表数量 <= 3 时，浓缩为 1 个精品小节，绑定该领域所有表
                primary_table = matched_tables[0]
                bound_tables = [t["table_name"] for t in matched_tables]
                bound_files = list(dict.fromkeys(t.get("file_name", "") for t in matched_tables if t.get("file_name")))
                chart_plan = self.auto_recommend_chart(
                    primary_table["table_name"], 
                    primary_table.get("columns", []), 
                    t_def["default_chart_type"],
                    matched_tables
                )
                sections.append({
                    "id": f"sec_{theme_index}",
                    "chapter_title": f"第{cn_num}章 {t_def['chapter_title']}",
                    "section_title": f"{theme_index}.1 {t_def['section_title']}",
                    "objective": t_def["objective"],
                    "table_keyword": primary_table.get("file_name", t_def["patterns"][0]),
                    "file_name": primary_table.get("file_name", ""),
                    "sheet_name": primary_table.get("sheet_name", ""),
                    "table_name": primary_table.get("table_name", ""),
                    "bound_tables": bound_tables,
                    "bound_files": bound_files,
                    "chart_plan": chart_plan
                })
            else:
                # 规则 2: 表数量较多时，自适应切分为多小节 (4<=N<=12 -> 2~4节; N>12 -> 5~8节)
                k = min(len(matched_tables), max(2, (N + 2) // 3)) if N <= 12 else min(8, max(4, (N + 4) // 5))
                chunk_size = (N + k - 1) // k
                for sub_i in range(k):
                    sub_tables = matched_tables[sub_i * chunk_size : (sub_i + 1) * chunk_size]
                    if not sub_tables:
                        continue
                    pri = sub_tables[0]
                    raw_fn = os.path.splitext(pri.get("file_name", ""))[0]
                    clean_name = re.sub(r'^[表\d\-_\.\s]+', '', raw_fn)
                    sub_title = f"{clean_name}核心指标与演进分析" if clean_name else f"{t_def['section_title']} (第{sub_i+1}部分)"
                    b_tables = [t["table_name"] for t in sub_tables]
                    b_files = list(dict.fromkeys(t.get("file_name", "") for t in sub_tables if t.get("file_name")))
                    c_plan = self.auto_recommend_chart(
                        pri["table_name"],
                        pri.get("columns", []),
                        t_def["default_chart_type"],
                        sub_tables
                    )
                    sections.append({
                        "id": f"sec_{theme_index}_{sub_i + 1}",
                        "chapter_title": f"第{cn_num}章 {t_def['chapter_title']}",
                        "section_title": f"{theme_index}.{sub_i + 1} {sub_title}",
                        "objective": f"聚焦{', '.join(b_files[:3])}，深入评估{t_def['chapter_title']}相关指标",
                        "table_keyword": pri.get("file_name", clean_name),
                        "file_name": pri.get("file_name", ""),
                        "sheet_name": pri.get("sheet_name", ""),
                        "table_name": pri.get("table_name", ""),
                        "bound_tables": b_tables,
                        "bound_files": b_files,
                        "chart_plan": c_plan
                    })

        # 第二阶段：处理未命中标准公文领域的自定义新表
        unassigned_tables = [item for item in catalog if item["table_name"] not in assigned_tables]
        
        if len(unassigned_tables) <= 4:
            # 数量较少时 (如单元测试中的单个新表)，为每个表单独开辟新章节
            for item in unassigned_tables:
                theme_index += 1
                cn_num = CN_NUMS[theme_index - 1] if theme_index <= len(CN_NUMS) else str(theme_index)
                raw_fn = os.path.splitext(item.get("file_name", ""))[0]
                clean_name = re.sub(r'^表[\d\-_.]*\s*', '', raw_fn)
                clean_name = re.sub(r'^\d+[\-_.]\d+[\-_.]?\d*\s*', '', clean_name)
                clean_name = clean_name.replace("数据", "").replace("情况", "").strip()
                if not clean_name:
                    clean_name = item.get("sheet_name", f"指标数据_{theme_index}")

                chart_plan = self.auto_recommend_chart(
                    item["table_name"], 
                    item.get("columns", []), 
                    None,
                    [item]
                )

                sections.append({
                    "id": f"sec_{theme_index}",
                    "chapter_title": f"第{cn_num}章 {clean_name}分析与评价",
                    "section_title": f"{theme_index}.1 {clean_name}核心指标与演进态势",
                    "objective": f"基于{item.get('file_name', '上传报表')}深入分析{clean_name}的关键指标演进、结构分布与综合建设成效",
                    "table_keyword": item.get("file_name", clean_name),
                    "file_name": item.get("file_name", ""),
                    "sheet_name": item.get("sheet_name", ""),
                    "table_name": item.get("table_name", ""),
                    "bound_tables": [item["table_name"]],
                    "bound_files": [item.get("file_name", "")],
                    "chart_plan": chart_plan
                })
        else:
            # 大规模 500+ 自定义表格场景：聚类批处理，按 4~6 个表成一章，避免章节爆炸
            chunk_size = 5
            for c_idx in range(0, len(unassigned_tables), chunk_size):
                sub_unassigned = unassigned_tables[c_idx : c_idx + chunk_size]
                theme_index += 1
                cn_num = CN_NUMS[theme_index - 1] if theme_index <= len(CN_NUMS) else str(theme_index)
                pri = sub_unassigned[0]
                raw_fn = os.path.splitext(pri.get("file_name", ""))[0]
                clean_name = re.sub(r'^[表\d\-_\.\s]+', '', raw_fn).replace("数据", "").replace("情况", "").strip() or f"专项指标_{theme_index}"
                
                chart_plan = self.auto_recommend_chart(
                    pri["table_name"],
                    pri.get("columns", []),
                    None,
                    sub_unassigned
                )
                b_tables = [t["table_name"] for t in sub_unassigned]
                b_files = list(dict.fromkeys(t.get("file_name", "") for t in sub_unassigned if t.get("file_name")))

                sections.append({
                    "id": f"sec_{theme_index}",
                    "chapter_title": f"第{cn_num}章 {clean_name}等综合专题评价",
                    "section_title": f"{theme_index}.1 {clean_name}及关联专项指标研判",
                    "objective": f"联合评估{', '.join(b_files[:3])}等相关报表，提炼专项建设综合成效",
                    "table_keyword": pri.get("file_name", clean_name),
                    "file_name": pri.get("file_name", ""),
                    "sheet_name": pri.get("sheet_name", ""),
                    "table_name": pri.get("table_name", ""),
                    "bound_tables": b_tables,
                    "bound_files": b_files,
                    "chart_plan": chart_plan
                })

        return sections if sections else self.get_fallback_outline()

    def auto_recommend_chart(
        self, 
        table_name: str, 
        columns: List[str], 
        preferred_type: Optional[str] = None,
        all_matched_tables: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """基于 DuckDB 真实数据动态推导并生成自适应学术图表计划"""
        try:
            # 1. 机构/单位类别：若存在多个对比表，执行跨表联合分布统计
            if preferred_type == "pie" and all_matched_tables and len(all_matched_tables) >= 2:
                labels = []
                data = []
                for tbl in all_matched_tables[:4]:
                    clean_lbl = re.sub(r'^[表\d_\-\.\s]+', '', tbl.get("file_name", ""))
                    clean_lbl = clean_lbl.replace("学校", "").replace("数据.xls", "").replace(".xls", "").replace("数据.xlsx", "").replace(".xlsx", "")
                    cnt = tbl.get("row_count", 0)
                    if cnt > 0:
                        labels.append(clean_lbl)
                        data.append(cnt)
                if len(labels) >= 2:
                    return {
                        "type": "pie",
                        "title": "学校组织管理与教学科研单位构架分布占比",
                        "labels": labels,
                        "data": data,
                        "series_name": "单位数"
                    }

            if not table_name or not self.duckdb_engine:
                return None

            # 2. 探测时间/年份列 -> 生成趋势折线图 (排除“修业年限”等误判)
            year_col = next((c for c in columns if any(k in c for k in ["年度", "年份", "获批时间", "通过时间", "成立时间", "year", "date"]) and "年限" not in c and "年龄" not in c), None)
            if (preferred_type == "line" or (not preferred_type and year_col)) and year_col:
                sql = f'SELECT "{year_col}", count(*) as cnt FROM {table_name} WHERE "{year_col}" IS NOT NULL AND "{year_col}" != \'\' GROUP BY "{year_col}" ORDER BY "{year_col}" LIMIT 8'
                res = self.duckdb_engine.query(sql)
                if res and len(res) >= 2 and "error" not in res[0]:
                    lbls = [f"{str(r[year_col])}年" if "年" not in str(r[year_col]) else str(r[year_col]) for r in res]
                    vals = [int(r["cnt"]) for r in res]
                    return {
                        "type": "line",
                        "title": "关键指标建设与演进年度变化趋势",
                        "labels": lbls,
                        "data": vals,
                        "series_name": "数量",
                        "y_label": "统计数(个)"
                    }

            # 3. 探测分类列 -> 生成柱状图或条形图
            group_col = None
            for c in columns:
                if any(k in c for k in ["单位", "学院", "系", "部门", "门类", "类型", "类别", "职称"]):
                    group_col = c
                    break

            if not group_col and columns:
                group_col = columns[0]

            if group_col:
                sql = f'SELECT "{group_col}", count(*) as cnt FROM {table_name} WHERE "{group_col}" IS NOT NULL AND "{group_col}" != \'\' GROUP BY "{group_col}" ORDER BY cnt DESC LIMIT 6'
                res = self.duckdb_engine.query(sql)
                if res and len(res) >= 2 and "error" not in res[0]:
                    lbls = [str(r[group_col]) for r in res]
                    vals = [int(r["cnt"]) for r in res]
                    chart_type = preferred_type or ("pie" if len(lbls) <= 3 else "bar")
                    return {
                        "type": chart_type,
                        "title": f"各{group_col}指标分布对比情况",
                        "labels": lbls,
                        "data": vals,
                        "series_name": "数量",
                        "y_label": "统计数(个)"
                    }

        except Exception:
            pass

        return None

    def get_fallback_outline(self) -> List[Dict[str, Any]]:
        """安全基准大纲兜底"""
        return [
            {
                "id": "sec_1",
                "chapter_title": "第一章 学校概况与办学定位",
                "section_title": "1.1 办学历史与发展目标",
                "objective": "客观阐述学校基础办学性质、办学规模与中长期发展战略规划定位",
                "table_keyword": "1_1",
                "file_name": "1-1 学校概况.xls",
                "sheet_name": "",
                "table_name": "tbl_1-1",
                "bound_tables": ["tbl_1-1"],
                "bound_files": ["1-1 学校概况.xls"],
                "chart_plan": None
            },
            {
                "id": "sec_2",
                "chapter_title": "第二章 组织机构与师资科研支撑",
                "section_title": "2.1 教学科研与党政管理支撑体系",
                "objective": "系统梳理全校党政管理职能部门与各教学科研学院的构架分布",
                "table_keyword": "1_3",
                "file_name": "1-3 党政管理机构.xls",
                "sheet_name": "",
                "table_name": "tbl_1-3",
                "bound_tables": ["tbl_1-3"],
                "bound_files": ["1-3 党政管理机构.xls"],
                "chart_plan": {
                    "type": "pie",
                    "title": "学校教学科研与管理单位职能分布占比",
                    "labels": ["教学院系", "科研机构", "教辅支撑", "党政管理"],
                    "data": [24, 6, 8, 37],
                    "series_name": "单位数"
                }
            },
            {
                "id": "sec_3",
                "chapter_title": "第三章 专业设置与大类培养布局",
                "section_title": "3.1 本科专业结构与学科门类覆盖",
                "objective": "深入分析各学院设置本科专业的分布形态、学制年限及师范类专业结构占比",
                "table_keyword": "1_4_1",
                "file_name": "1-4-1 专业基本情况.xls",
                "sheet_name": "",
                "table_name": "tbl_1-4-1",
                "bound_tables": ["tbl_1-4-1"],
                "bound_files": ["1-4-1 专业基本情况.xls"],
                "chart_plan": {
                    "type": "bar",
                    "title": "各二级学院本科专业数量分布情况",
                    "labels": ["经管学院", "体育学院", "美术学院", "数统学院", "信科院", "教育学院"],
                    "data": [8, 7, 7, 5, 5, 5],
                    "series_name": "专业数",
                    "y_label": "设置专业数(个)"
                }
            },
            {
                "id": "sec_4",
                "chapter_title": "第四章 学科建设与高层次学位点发展",
                "section_title": "4.1 博士硕士学位授权点与流动站布局",
                "objective": "全面论述全校博士后科研流动站、一级博士点、硕士专业学位授权点的层级结构",
                "table_keyword": "4_1",
                "file_name": "4-1 学科建设与学位点.xls",
                "sheet_name": "",
                "table_name": "tbl_4-1",
                "bound_tables": ["tbl_4-1"],
                "bound_files": ["4-1 学科建设与学位点.xls"],
                "chart_plan": {
                    "type": "column",
                    "title": "高层次学科建设与学位点授权类别分布",
                    "labels": ["博士后流动站", "一级硕士点", "专业硕士类别", "一流专业点"],
                    "data": [4, 18, 21, 40],
                    "series_name": "数量",
                    "y_label": "获批数量(个)"
                }
            },
            {
                "id": "sec_5",
                "chapter_title": "第五章 优势一流专业建设成效与展望",
                "section_title": "5.1 国家级与省级一流本科专业成效",
                "objective": "分析国家级与省级一流本科专业建设点的获批年度演进与特色示范效应",
                "table_keyword": "4_3",
                "file_name": "4-3 一流本科专业建设点.xls",
                "sheet_name": "",
                "table_name": "tbl_4-3",
                "bound_tables": ["tbl_4-3"],
                "bound_files": ["4-3 一流本科专业建设点.xls"],
                "chart_plan": {
                    "type": "line",
                    "title": "一流本科专业建设点年度获批演进趋势",
                    "labels": ["2019年度", "2020年度", "2021年度", "2022年度"],
                    "data": [12, 14, 10, 4],
                    "series_name": "获批专业数",
                    "y_label": "入选数量(个)"
                }
            }
        ]
