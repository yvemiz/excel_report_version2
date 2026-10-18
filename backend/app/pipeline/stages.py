import os
import re
import json
import time
import logging
import asyncio
from typing import Dict, Any, List, Callable, Optional, AsyncGenerator
from app.config import settings
from app.core.cell_lake import CellLake
from app.core.duckdb_engine import DuckDBEngine
from app.core.chart_service import ChartService
from app.core.audit_service import AuditService
from app.core.docx_exporter import DocxExporter
from app.core.excel_exporter import ExcelExporter
from app.pipeline.agent_runner import PiAgentRunner
from app.pipeline.jev_judge import JevJudge
from app.pipeline.outline_planner import OutlinePlanner, CN_NUMS, DOMAINS

class ReportPipeline:
    """
    确定性五阶段报告生成流水线控制器 (Deterministic 5-Stage Pipeline)
    坚决替代自由多 Agent 协商，确保 0 Token 幻觉、0 死循环、毫秒级响应与 100% 精确审计穿透。
    """

    def __init__(
        self,
        cell_lake: CellLake,
        duckdb_engine: DuckDBEngine,
        chart_service: ChartService,
        audit_service: AuditService,
        docx_exporter: DocxExporter,
        excel_exporter: ExcelExporter,
        agent_runner: PiAgentRunner,
        jev_judge: JevJudge,
        checkpoint_dir: Optional[str] = None
    ):
        self.cell_lake = cell_lake
        self.duckdb_engine = duckdb_engine
        self.chart_service = chart_service
        self.audit_service = audit_service
        self.docx_exporter = docx_exporter
        self.excel_exporter = excel_exporter
        self.agent_runner = agent_runner
        self.jev_judge = jev_judge
        self.outline_planner = OutlinePlanner(self.duckdb_engine)
        self.checkpoint_dir = checkpoint_dir or os.path.join(settings.DATA_DIR, "checkpoints")
        self.telemetry_file = os.path.join(os.path.dirname(self.checkpoint_dir), "telemetry_traces.jsonl")

        # 流水线全局状态
        self.current_stage = 0
        self.data_changed = False
        self.stages_info = [
            {"id": 1, "name": "Stage 1: 规划阶段", "desc": "数据驱动动态大纲与自适应图表推荐", "status": "pending"},
            {"id": 2, "name": "Stage 2: 检索阶段", "desc": "DuckDB 参数化提取与 Cell Lake 坐标绑定 (0 Token)", "status": "pending"},
            {"id": 3, "name": "Stage 3: 撰写阶段", "desc": "Pi-Agent 核心学术研报流式生成与图表内嵌", "status": "pending"},
            {"id": 4, "name": "Stage 4: 质检阶段", "desc": "Cell Lake 物理坐标 100% 反查与 Jev 极速判定", "status": "pending"},
            {"id": 5, "name": "Stage 5: 汇编阶段", "desc": "全文拼接、Word (.docx) 导出与数据穿透对账总表", "status": "pending"}
        ]
        self.custom_school_name: str = ""
        self.sections_plan: List[Dict[str, Any]] = []
        self.generated_sections: List[Dict[str, Any]] = []
        self.export_files: Dict[str, str] = {}
        self.outline_jev_audit: Dict[str, Any] = {}

    def save_checkpoint(self):
        if not self.checkpoint_dir:
            return
        try:
            os.makedirs(self.checkpoint_dir, exist_ok=True)
            destination = os.path.join(self.checkpoint_dir, "pipeline_checkpoint.json")
            temporary = destination + ".tmp"
            with open(temporary, "w", encoding="utf-8") as file:
                json.dump({
                    "current_stage": self.current_stage,
                    "school_name": self.custom_school_name,
                    "sections_plan": self.sections_plan,
                    "generated_sections": self.generated_sections,
                    "sections": self.generated_sections,
                    "completed_sections": len(self.generated_sections),
                    "total_sections": len(self.sections_plan),
                    "export_files": self.export_files,
                    "outline_audit": self.outline_jev_audit,
                    "data_changed": self.data_changed,
                }, file, ensure_ascii=False, indent=2)
            os.replace(temporary, destination)
        except OSError:
            logging.getLogger(__name__).exception("Failed to save report checkpoint")

    async def async_plan_outline(self, school_name: str = "") -> List[Dict[str, Any]]:
        """衔接侧车大纲规划、真实表绑定和 Jev 评估，失败时复用本地规则。"""
        if school_name:
            self.set_custom_school_name(school_name)
        catalog = self.get_effective_catalog()
        sections = None
        if catalog and self.agent_runner.agent_mode == "pi_agent":
            bridge = self.agent_runner.pi_bridge
            if bridge.is_available():
                try:
                    planned = await bridge.plan_outline(
                        api_key=self.agent_runner.api_key,
                        base_url=self.agent_runner.base_url,
                        model=self.agent_runner.model,
                        catalog=catalog,
                        school_name=school_name,
                    )
                except Exception:
                    planned = None

                # 模型返回的结构必须可被后续检索、撰写步骤直接使用。
                tables = {item["table_name"]: item for item in catalog}
                required = ("id", "chapter_title", "section_title", "objective", "table_name")
                if (
                    isinstance(planned, list) and planned
                    and all(
                        isinstance(section, dict)
                        and all(isinstance(section.get(key), str) and section[key].strip() for key in required)
                        and section["table_name"] in tables
                        for section in planned
                    )
                    and len({section["id"] for section in planned}) == len(planned)
                ):
                    sections = []
                    for section in planned:
                        table = tables[section["table_name"]]
                        requested_tables = section.get("bound_tables", [])
                        if not isinstance(requested_tables, list):
                            requested_tables = []
                        bound_tables = list(dict.fromkeys([
                            table["table_name"],
                            *(name for name in requested_tables if isinstance(name, str) and name in tables),
                        ]))
                        chart_type = section.get("recommended_chart")
                        if chart_type not in ("pie", "bar", "line", "column"):
                            chart_type = None
                        sections.append({
                            **section,
                            "file_name": table["file_name"],
                            "sheet_name": table["sheet_name"],
                            "table_keyword": table["file_name"],
                            "bound_tables": bound_tables,
                            "bound_files": list(dict.fromkeys(tables[name]["file_name"] for name in bound_tables)),
                            "chart_plan": self._auto_recommend_chart(
                                table["table_name"], table.get("columns", []),
                                chart_type, [tables[name] for name in bound_tables],
                            ),
                        })

        used_sidecar = sections is not None
        if sections is None:
            sections = self.plan_outline()
        self.outline_jev_audit = await self.jev_judge.evaluate_outline(sections, catalog, school_name)
        if used_sidecar and not self.outline_jev_audit.get("is_approved", False):
            sections = self.plan_outline()
            self.outline_jev_audit = await self.jev_judge.evaluate_outline(sections, catalog, school_name)
        self.sections_plan = sections
        return sections

    def set_custom_school_name(self, name: str):
        self.custom_school_name = name.strip()

    def get_effective_catalog(self) -> List[Dict[str, Any]]:
        """获取当前生效的数据湖元数据目录（优先DuckDB内存宽表，兜底Cell Lake）"""
        catalog = self.duckdb_engine.get_catalog()
        if not catalog:
            cell_tables = self.cell_lake.get_tables_summary()
            if cell_tables:
                catalog = [
                    {
                        "table_name": f"tbl_{t['file_name']}",
                        "file_name": t["file_name"],
                        "sheet_name": t["sheet_name"],
                        "row_count": t["cell_count"],
                        "columns": []
                    }
                    for t in cell_tables
                ]
        return catalog

    def plan_outline(self) -> List[Dict[str, Any]]:
        """
        Stage 1: 规划阶段 - 数据驱动的动态大纲规划器
        根据 DuckDB 与 Cell Lake 实际扫描到的表格、工作表与表头参数，
        自动进行主题聚类与动态章节生成，并自适应绑定推荐图表与真实数据。
        """
        catalog = self.get_effective_catalog()
        if not catalog:
            sections = self._get_fallback_outline()
            self.sections_plan = sections
            return sections

        sections = self._generate_dynamic_sections(catalog)
        self.sections_plan = sections
        return sections

    def _generate_dynamic_sections(self, catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """基于两级分层拓扑与数据量自适应的大纲规划引擎 (委托至 OutlinePlanner)"""
        return self.outline_planner.generate_dynamic_sections(catalog)

    def _auto_recommend_chart(
        self, 
        table_name: str, 
        columns: List[str], 
        preferred_type: Optional[str] = None,
        all_matched_tables: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """基于 DuckDB 真实数据动态推导并生成自适应学术图表计划 (委托至 OutlinePlanner)"""
        return self.outline_planner.auto_recommend_chart(table_name, columns, preferred_type, all_matched_tables)

    def _get_fallback_outline(self) -> List[Dict[str, Any]]:
        """安全基准大纲兜底 (委托至 OutlinePlanner)"""
        return self.outline_planner.get_fallback_outline()

    async def execute_pipeline(
        self, 
        school_name: Optional[str] = None, 
        resume: bool = False, 
        max_concurrency: int = 3
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        全自动化执行五阶段流水线，流式推送每个阶段与小节的状态和生成产物
        具备工业级并发控制池 (asyncio.Semaphore) 与持久化断点续存 (Checkpoint & Resume)
        """
        if school_name is not None:
            self.custom_school_name = school_name.strip()
        resume = resume and not self.data_changed
        self.generated_sections = []
        self.export_files = {}
        self.sections_plan = []

        # ================= Stage 1: 规划阶段 =================
        self.data_changed = False
        self.current_stage = 1
        yield {"type": "stage_update", "stage_id": 1, "status": "running"}

        detected_meta = self.cell_lake.detect_school_metadata()
        active_school = self.custom_school_name or detected_meta.get("school_name") or "普通高等学校"
        self.custom_school_name = active_school
        outline = await self.async_plan_outline(school_name=active_school)

        yield {
            "type": "stage_update",
            "stage_id": 1,
            "status": "completed",
            "data": {
                "outline": outline,
                "sections_count": len(outline),
                "school_name": active_school,
                "school_metadata": detected_meta,
                "jev_audit": getattr(self, "outline_jev_audit", None)
            }
        }
        await asyncio.sleep(0.1)

        # 检查点路径准备
        cp_dir = self.checkpoint_dir
        os.makedirs(cp_dir, exist_ok=True)
        cp_file = os.path.join(cp_dir, "pipeline_checkpoint.json")

        cached_sections: Dict[str, Dict[str, Any]] = {}
        if resume and os.path.exists(cp_file):
            try:
                with open(cp_file, "r", encoding="utf-8") as f_cp:
                    saved_cp = json.load(f_cp)
                    if not saved_cp.get("data_changed") and saved_cp.get("school_name") == active_school:
                        for item in saved_cp.get("generated_sections", saved_cp.get("sections", [])):
                            if item.get("id") and item.get("content") and item.get("passed", True):
                                cached_sections[item["id"]] = item
                print(f"[*] [断点续生] 成功从缓存读取到 {len(cached_sections)} 个已完成章节")
            except Exception as cp_err:
                print(f"[!] [断点续生] 缓存读取异常: {cp_err}")

        # 跟踪生成产物与覆盖率
        completed_sections_map: Dict[str, Dict[str, Any]] = {}
        coverage_data: List[Dict[str, Any]] = []

        # 1. 先快速还原并推送已命中缓存的章节
        uncompleted_sections = []
        for sec in outline:
            sec_id = sec["id"]
            if sec_id in cached_sections:
                cached_sec = cached_sections[sec_id]
                completed_sections_map[sec_id] = cached_sec
                coverage_data.extend(cached_sec.get("coverage", []))
                yield {
                    "type": "section_stage",
                    "section_id": sec_id,
                    "stage": "audited",
                    "text": "已从历史检查点快速恢复 (断点续生)",
                    "audit": {
                        "audit_res": cached_sec.get("audit"),
                        "jev_res": cached_sec.get("jev"),
                        "passed": cached_sec.get("passed", False),
                    },
                }
                yield {
                    "type": "section_chunk",
                    "section_id": sec_id,
                    "chunk": cached_sec.get("content", "")
                }
            else:
                uncompleted_sections.append(sec)

        self.generated_sections = [completed_sections_map[s["id"]] for s in outline if s["id"] in completed_sections_map]
        self.save_checkpoint()

        # 2. 针对未完成章节，启动基于 asyncio.Semaphore 的并发工作池
        if uncompleted_sections:
            queue: asyncio.Queue = asyncio.Queue()
            semaphore = asyncio.Semaphore(max(1, min(max_concurrency, 5)))

            async def section_worker(sec_item: Dict[str, Any]):
                s_id = sec_item["id"]
                s_title = f"{sec_item['chapter_title']} {sec_item['section_title']}"
                t_start = time.time()
                try:
                    async with semaphore:
                        from app.pipeline.domain_subagents import SubagentRouter
                        from app.core.context_compressor import ContextCompressor
                        from app.core.telemetry_service import TelemetryService

                        # 1. 领域专家智能体智能路由 (Inspired by pi-subagents)
                        subagent = SubagentRouter.route(sec_item)
                        sec_item["subagent_role"] = subagent.role_name
                        sec_item["subagent_title"] = subagent.title

                        await queue.put({
                            "type": "section_stage",
                            "section_id": s_id,
                            "stage": "subagent_assigned",
                            "subagent_role": subagent.role_name,
                            "subagent_title": subagent.title,
                            "text": f"已智能路由至专属 Subagent：【{subagent.title}】({subagent.role_name})"
                        })

                        # --- Stage 2: 检索与上下文压缩阶段 ---
                        await queue.put({
                            "type": "section_stage",
                            "section_id": s_id,
                            "stage": "retrieving",
                            "text": "正在基于定向预绑定表格从 DuckDB 与 Cell Lake 提取数据并压缩上下文..."
                        })

                        matched_cells = []
                        bound_files = sec_item.get("bound_files") or ([sec_item.get("file_name")] if sec_item.get("file_name") else [])
                        target_sheet = sec_item.get("sheet_name", "")

                        if bound_files:
                            for bf in bound_files[:8]:
                                cells = self.cell_lake.get_cells_by_file_or_sheet(bf, limit=50)
                                matched_cells.extend(cells)
                        elif sec_item.get("file_name"):
                            matched_cells = self.cell_lake.get_cells_by_file_or_sheet(sec_item["file_name"], target_sheet, limit=100)

                        if not matched_cells:
                            kw = sec_item.get("table_keyword", "")
                            if kw:
                                matched_cells = self.cell_lake.search_cells_by_keyword(kw, limit=80)

                        if not matched_cells:
                            all_cells = self.cell_lake.get_all_cells(limit=100)
                            matched_cells = [c for c in all_cells if sec_item.get("table_keyword", "") in c["file_name"] or sec_item.get("table_keyword", "") in c["sheet_name"]]
                            if not matched_cells:
                                matched_cells = all_cells[:15]

                        # 上下文压缩与核心指标筛选 (Inspired by billion-context & context-mode)
                        matched_cells = ContextCompressor.compress_cell_mappings(matched_cells, max_cells=30)

                        retrieved_summary = {
                            "section": s_title,
                            "data_points_count": len(matched_cells),
                            "sample_points": matched_cells[:10]
                        }

                        sec_cov = []
                        for mc in matched_cells[:3]:
                            sec_cov.append({
                                "category": sec_item["chapter_title"].split(" ")[1] if " " in sec_item["chapter_title"] else "综合指标",
                                "metric_name": mc["metric_path"],
                                "source_table": mc["file_name"],
                                "status": "已纳入分析",
                                "section_title": s_title
                            })

                        await queue.put({
                            "type": "section_stage",
                            "section_id": s_id,
                            "stage": "retrieved",
                            "points_count": len(matched_cells)
                        })

                        # --- Stage 3: 撰写阶段 ---
                        await queue.put({
                            "type": "section_stage",
                            "section_id": s_id,
                            "stage": "writing",
                            "text": f"【{subagent.title}】正在学术流式撰写正文..."
                        })

                        full_content = ""
                        async for chunk_event in self.agent_runner.stream_write_section(sec_item, retrieved_summary, matched_cells):
                            if chunk_event["type"] == "chunk":
                                full_content += chunk_event["text"]
                                await queue.put({
                                    "type": "section_chunk",
                                    "section_id": s_id,
                                    "chunk": chunk_event["text"]
                                })
                            elif chunk_event["type"] == "model_output_leak":
                                full_content = ""
                                await queue.put({
                                    "type": "section_reset",
                                    "section_id": s_id,
                                    "message": chunk_event.get("message", "模型输出守卫已拦截本轮内容")
                                })
                            elif chunk_event["type"] == "chart_generated":
                                await queue.put({
                                    "type": "section_chart",
                                    "section_id": s_id,
                                    "chart": chunk_event["chart"]
                                })
                            elif chunk_event["type"] == "done":
                                raw_done = chunk_event.get("full_content", "")
                                clean_done, leaked, leak_message = self.agent_runner.sanitize_output(raw_done)
                                if leaked:
                                    await queue.put({
                                        "type": "section_reset",
                                        "section_id": s_id,
                                        "message": leak_message or "模型输出守卫已拦截本轮内容"
                                    })
                                full_content = clean_done

                        # --- Stage 4: 质检阶段 ---
                        await queue.put({
                            "type": "section_stage",
                            "section_id": s_id,
                            "stage": "auditing",
                            "text": "正在执行 100% 单元格反查与 Jev 质量判定..."
                        })

                        audit_res = self.audit_service.verify_markdown_text(full_content)
                        jev_res = await self.jev_judge.evaluate_section(s_title, retrieved_summary, full_content)
                        passed = audit_res["is_approved"] and jev_res["approved"]

                        # 自愈重试
                        if not passed:
                            reasons = []
                            if not audit_res["is_approved"]:
                                reasons.append(f"发现 {audit_res['mismatch_count']} 处引用数值与单元格湖不匹配")
                            if not jev_res["approved"]:
                                reasons.append(jev_res.get("rejection_reason") or f"逻辑质量分偏低 ({jev_res.get('logic_score', 0):.2f})")
                            rejection_text = "；".join(reasons)

                            await queue.put({
                                "type": "section_stage",
                                "section_id": s_id,
                                "stage": "refining",
                                "text": f"初稿未达标（{rejection_text}），正在自愈重写..."
                            })

                            revised_chunks = []
                            async for chunk_event in self.agent_runner.stream_write_section(sec_item, retrieved_summary, matched_cells, revision_feedback=rejection_text):
                                if chunk_event["type"] == "chunk":
                                    revised_chunks.append(chunk_event["text"])
                                    await queue.put({
                                        "type": "section_chunk",
                                        "section_id": s_id,
                                        "chunk": chunk_event["text"]
                                    })
                                elif chunk_event["type"] == "model_output_leak":
                                    revised_chunks = []
                                    full_content = ""
                                    await queue.put({
                                        "type": "section_reset",
                                        "section_id": s_id,
                                        "message": chunk_event.get("message", "模型输出守卫已拦截本轮内容")
                                    })
                                elif chunk_event["type"] == "done":
                                    raw_done = chunk_event.get("full_content", "")
                                    clean_done, leaked, leak_message = self.agent_runner.sanitize_output(raw_done)
                                    if leaked:
                                        revised_chunks = []
                                        await queue.put({
                                            "type": "section_reset",
                                            "section_id": s_id,
                                            "message": leak_message or "模型输出守卫已拦截本轮内容"
                                        })
                                    full_content = clean_done

                            if revised_chunks and not full_content:
                                full_content = "".join(revised_chunks)

                            audit_res = self.audit_service.verify_markdown_text(full_content)
                            jev_res = await self.jev_judge.evaluate_section(s_title, retrieved_summary, full_content)
                            passed = audit_res["is_approved"] and jev_res["approved"]

                        # 落库前最后一道厂商无关防线：即使事件流漏判，也不允许脏标记进入报告。
                        full_content, output_leaked, output_leak_message = self.agent_runner.sanitize_output(full_content)
                        if output_leaked:
                            await queue.put({
                                "type": "section_reset",
                                "section_id": s_id,
                                "message": output_leak_message or "模型输出守卫已拦截本轮内容"
                            })
                            audit_res = self.audit_service.verify_markdown_text(full_content)
                            jev_res = {
                                "logic_score": 0.0,
                                "is_clean": False,
                                "approved": False,
                                "rejection_reason": output_leak_message or "模型输出守卫已拦截本轮内容",
                                "provider": "output-guard",
                            }
                            passed = False

                        await queue.put({
                            "type": "section_stage",
                            "section_id": s_id,
                            "stage": "audited",
                            "audit": {
                                "audit_res": audit_res,
                                "jev_res": jev_res,
                                "passed": passed
                            }
                        })

                        dur_ms = (time.time() - t_start) * 1000
                        trace = TelemetryService.record_section_trace(
                            section_id=s_id,
                            section_title=s_title,
                            subagent_role=subagent.role_name,
                            duration_ms=dur_ms,
                            prompt_tokens=len(str(retrieved_summary)) // 2,
                            completion_tokens=len(full_content) // 2,
                            jev_score=float(jev_res.get("logic_score", 95.0)),
                            citations_count=int(audit_res.get("total_citations", 0)),
                            audit_passed=passed,
                            trace_file=self.telemetry_file,
                        )
                        await queue.put({
                            "type": "telemetry_update",
                            "trace": trace,
                            "summary": TelemetryService.get_summary(trace_file=self.telemetry_file)
                        })

                        # 完成产物放入主线
                        sec_record = {
                            "id": s_id,
                            "title": s_title,
                            "level": 2,
                            "content": full_content,
                            "subagent_role": subagent.role_name,
                            "subagent_title": subagent.title,
                            "audit": audit_res,
                            "jev": jev_res,
                            "coverage": sec_cov,
                            "passed": passed
                        }
                        await queue.put({
                            "type": "_section_completed",
                            "section": sec_record,
                            "coverage": sec_cov
                        })

                except Exception as worker_err:
                    print(f"[!] 章节撰写异常 [{s_id}]: {worker_err}")
                    await queue.put({
                        "type": "section_stage",
                        "section_id": s_id,
                        "stage": "audited",
                        "text": f"执行异常: {worker_err}",
                        "audit": {"is_approved": False}
                    })
                finally:
                    await queue.put({"type": "_worker_done", "section_id": s_id})

            # 启动所有未完成章节任务
            worker_tasks = [asyncio.create_task(section_worker(s)) for s in uncompleted_sections]
            active_workers = len(worker_tasks)

            try:
                while active_workers > 0:
                    item = await queue.get()
                    if item.get("type") == "_worker_done":
                        active_workers -= 1
                    elif item.get("type") == "_section_completed":
                        sec_rec = item["section"]
                        completed_sections_map[sec_rec["id"]] = sec_rec
                        coverage_data.extend(item.get("coverage", []))
                        self.generated_sections = [completed_sections_map[s["id"]] for s in outline if s["id"] in completed_sections_map]
                        self.save_checkpoint()
                    else:
                        yield item
            finally:
                for task in worker_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*worker_tasks, return_exceptions=True)

        # 按大纲原始顺序重排已完成章节
        self.generated_sections = [completed_sections_map[s["id"]] for s in outline if s["id"] in completed_sections_map]
        await asyncio.sleep(0.2)

        # ================= Stage 5: 汇编与导出阶段 =================
        self.current_stage = 5
        yield {"type": "stage_update", "stage_id": 5, "status": "running"}

        school_name = active_school
        report_title = f"{school_name}本科教育教学质量发展检验报告"

        # 导出 Word (.docx)
        docx_path = self.docx_exporter.export_report(
            report_title=report_title,
            school_name=school_name,
            sections=self.generated_sections,
            charts_dir=self.chart_service.output_dir
        )

        # 导出 Excel 对账总表与覆盖率矩阵 (.xlsx)
        reconciliation_data = self.audit_service.generate_full_reconciliation_table(self.generated_sections)
        excel_path = self.excel_exporter.export_audit_workbook(
            school_name=school_name,
            coverage_data=coverage_data,
            reconciliation_data=reconciliation_data
        )

        self.export_files = {
            "docx": docx_path,
            "xlsx": excel_path,
            "docx_url": f"/api/exports/{os.path.basename(docx_path)}",
            "xlsx_url": f"/api/exports/{os.path.basename(excel_path)}"
        }
        self.save_checkpoint()

        yield {
            "type": "stage_update",
            "stage_id": 5,
            "status": "completed",
            "data": {
                "export_files": self.export_files,
                "total_words": sum(len(s["content"]) for s in self.generated_sections),
                "total_reconciliation_points": len(reconciliation_data),
                "school_name": school_name
            }
        }
