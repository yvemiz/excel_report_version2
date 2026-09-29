"""
Comprehensive Test Suite for Integrated Pi Plugin Modules (Categories 1 - 5)
1. WorkbookInspector (@firstpick/pi-extension-workbook)
2. ContextCompressor (billion-context / context-mode)
3. SubagentRouter (pi-subagents / @quintinshaw/pi-dynamic-workflows)
4. JevPromptEnhancer & StructuredOutputEnforcer (@hikae/pi-prompt-enhancer / @zhushanwen/pi-structured-output)
5. TelemetryService & DeepSeekBalanceMonitor (pi-deepseek-balance / local telemetry)
6. DocxExporter Enhanced Typography
"""

import os
import sys
import unittest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.core.workbook_inspector import WorkbookInspector
from app.core.context_compressor import ContextCompressor
from app.pipeline.domain_subagents import SubagentRouter
from app.pipeline.prompt_enhancer import JevPromptEnhancer, StructuredOutputEnforcer
from app.core.telemetry_service import TelemetryService, DeepSeekBalanceMonitor
from app.core.docx_exporter import DocxExporter

class TestPiPluginsIntegration(unittest.TestCase):

    def setUp(self):
        self.example_dir = os.path.join(os.path.dirname(__file__), "example")

    def test_01_workbook_inspector(self):
        """测试 Category 1: WorkbookInspector 完整性审计与防越界预检"""
        print("\n--- Test 01: WorkbookInspector ---")
        if os.path.exists(self.example_dir):
            rep = WorkbookInspector.inspect_directory(self.example_dir)
            self.assertGreater(rep["total_files"], 0)
            self.assertGreaterEqual(rep["overall_health_rate"], 80.0)
            print(f"[✓] 扫描到 {rep['total_files']} 份报表，健康合规率: {rep['overall_health_rate']}%")

        # 测试不存在文件时的安全兜底
        fake_rep = WorkbookInspector.inspect_file("non_existent_table.xlsx")
        self.assertFalse(fake_rep["is_valid"])
        self.assertEqual(fake_rep["risk_level"], "critical")
        print("[✓] 越界与缺失文件安全防御校验通过")

    def test_02_context_compressor(self):
        """测试 Category 2: ContextCompressor 意图检索与 5x Token 压缩"""
        print("\n--- Test 02: ContextCompressor ---")
        fake_catalog = [
            {"table_name": f"tbl_{i}", "file_name": f"表_{i}_师资队伍.xlsx", "sheet_name": "Sheet1", "row_count": 50, "col_count": 10, "headers": ["职称", "博士", "硕士"]}
            for i in range(1, 30)
        ]
        res = ContextCompressor.compress_catalog(
            fake_catalog,
            section_title="师资队伍与高层次人才",
            section_objective="全面分析学校专任教师结构与高层次人才队伍建设"
        )
        self.assertIn("核心支撑报表", res["compressed_text"])
        self.assertEqual(res["selected_tables_count"], 8)
        self.assertIn("%", res["compression_ratio"])
        print(f"[✓] 30 张报表压缩率: {res['compression_ratio']}，提取核心表: {res['selected_tables_count']}")

        # 单元格去重与压缩
        cells = [
            {"cell_id": f"c_{i}", "metric_path": "师资 > 专任教师总数", "raw_value": "1200人"}
            for i in range(10)
        ] + [
            {"cell_id": "c_unique", "metric_path": "师资 > 教授人数", "raw_value": "260人"}
        ]
        compact = ContextCompressor.compress_cell_mappings(cells, max_cells=5)
        self.assertEqual(len(compact), 2)  # 重复的 metric_path + raw_value 被有效去重
        print(f"[✓] 单元格冗余去重与压缩成功，保留精炼指标: {len(compact)} 条")

    def test_03_subagent_router(self):
        """测试 Category 3: SubagentRouter 领域专家角色智能路由"""
        print("\n--- Test 03: SubagentRouter ---")
        cases = [
            ({"section_title": "学校办学历史与战略定位", "objective": "分析办学概况"}, "OverviewSpecialist"),
            ({"section_title": "专任教师结构与职称发展", "objective": "分析生师比与高层次人才"}, "FacultySpecialist"),
            ({"section_title": "博士后流动站与学位点布局", "objective": "梳理一级学科博士点"}, "DisciplineSpecialist"),
            ({"section_title": "国家级一流本科专业建设成效", "objective": "分析双万计划"}, "UndergraduateSpecialist"),
            ({"section_title": "年度科研经费与省部级重点实验室", "objective": "科研创新成果"}, "ResearchSpecialist"),
        ]
        for meta, expected_role in cases:
            subagent = SubagentRouter.route(meta)
            self.assertEqual(subagent.role_name, expected_role)
            print(f"[✓] 章节【{meta['section_title']}】精准路由至 -> {subagent.title} ({subagent.role_name})")

    def test_04_prompt_enhancer_and_structured_output(self):
        """测试 Category 4: JevPromptEnhancer 评分增强与 StructuredOutputEnforcer 结构化自愈"""
        print("\n--- Test 04: JevPromptEnhancer & StructuredOutputEnforcer ---")
        base_prompt = "请简单写一下师资队伍的情况。"
        enh = JevPromptEnhancer.enhance(base_prompt, "重点关注高层次人才。")
        self.assertLess(enh["jev_prompt_score"], 90)  # 原始提示词缺少公文约束，得分低
        self.assertIn("Jev 决策模型自动化注入的公文质量补丁", enh["enhanced_prompt"])
        self.assertGreater(enh["injected_patches_count"], 0)
        print(f"[✓] Jev 提示词增强成功: 注入 {enh['injected_patches_count']} 项质量补丁")

        # 结构化输出自愈与非标语法修复
        malformed_draft = "学校专任教师[1200人](cell_101)，其中正高级教师260人[^cell_102]。"
        repaired = StructuredOutputEnforcer.validate_and_repair(
            malformed_draft,
            expected_title="师资队伍现状",
            valid_cell_ids=["cell_101", "cell_102"]
        )
        self.assertIn("### 师资队伍现状", repaired["repaired_text"])
        self.assertIn("[1200人][^cell_101]", repaired["repaired_text"])
        self.assertIn("[260人][^cell_102]", repaired["repaired_text"])
        self.assertEqual(repaired["total_citations"], 2)
        print(f"[✓] 结构化自愈通过: 自动修复非标链接语法与括号，验证锚点: {repaired['verified_citations']}")

    def test_05_telemetry_service(self):
        """测试 Category 5: TelemetryService 本地跟踪与 DeepSeekBalanceMonitor"""
        print("\n--- Test 05: TelemetryService & DeepSeekBalanceMonitor ---")
        trace = TelemetryService.record_section_trace(
            section_id="sec_test_1",
            section_title="师资队伍现状测试",
            subagent_role="FacultySpecialist",
            duration_ms=450.5,
            prompt_tokens=1500,
            completion_tokens=400,
            jev_score=96.5,
            citations_count=6,
            audit_passed=True
        )
        self.assertEqual(trace["subagent_role"], "FacultySpecialist")
        self.assertGreater(trace["est_cost_cny"], 0.0)

        summary = TelemetryService.get_summary()
        self.assertGreaterEqual(summary["total_sections_traced"], 1)
        print(f"[✓] 本地可观测跟踪成功写入: 累计分析章节 {summary['total_sections_traced']} 个，预估开销 ¥{summary['total_cost_cny']}")

        # 余额监测安全兜底测试
        async def run_balance():
            return await DeepSeekBalanceMonitor.fetch_balance("invalid_or_mock_key")
        
        bal = asyncio.run(run_balance())
        self.assertIn("status", bal)
        print(f"[✓] 余额监视器运行正常: {bal['status']}")

    def test_06_docx_enhanced_export(self):
        """测试 Category 1 强化版 Word 导出：首行缩进、学术角标与三线表附录"""
        print("\n--- Test 06: DocxExporter Enhanced Typography ---")
        test_out_dir = os.path.join(os.path.dirname(__file__), "data", "test_scratch")
        os.makedirs(test_out_dir, exist_ok=True)
        exporter = DocxExporter(test_out_dir)

        test_sections = [
            {
                "title": "第1章 师资队伍与高层次人才",
                "level": 1,
                "content": "学校现有专任教师 [1200人][^cell_101]，正高级职称占比达 [21.6%][^cell_102]。"
            }
        ]
        out_path = exporter.export_report("高校质量评估报告", "测试大学", test_sections, test_out_dir)
        self.assertTrue(os.path.exists(out_path))
        self.assertGreater(os.path.getsize(out_path), 5000)
        print(f"[✓] 学术级高保真 .docx 生成成功: {out_path} ({os.path.getsize(out_path)} 字节)")

if __name__ == "__main__":
    unittest.main()
