import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls

class DocxExporter:
    """
    学术级规范 Word 报告导出器 (.docx)
    包含：
    1. 标准公文独立封皮页（大标题、评估对象、编制单位、对账印鉴、编制日期）
    2. 目录导引与多级标题规范排版
    3. 嵌入式 300DPI 学术统计图表与图注
    4. Mermaid 拓扑结构优雅转写过滤
    5. 文末《附录：全文核心指标数据穿透溯源清单》专业表格
    """

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    @staticmethod
    def _strip_cell_citations(text: str) -> str:
        """输出可读正文，原始引用仍保留在流水线数据和对账表中。"""
        # 去掉 Markdown 脚注定义行，避免其内部编号和说明落入正文。
        text = re.sub(
            r'^\s*\[\s*\^\s*cell_[^\]\r\n]*\]\s*[:：].*$',
            '', text, flags=re.IGNORECASE | re.MULTILINE,
        )
        # 保留 [数值][^cell_id] 中的数值；连续脚注不能被当成数值。
        text = re.sub(
            r'\[((?!\s*\^\s*cell_)[^\]\r\n]+)\]\s*\[\s*\^\s*cell_[^\]\r\n]*\]',
            r'\1', text, flags=re.IGNORECASE,
        )
        # 同时清理单独脚注、连续脚注，以及旧导出遗留的 [^cell_id*]。
        text = re.sub(r'\[\s*\^\s*cell_[^\]\r\n]*\]', '', text, flags=re.IGNORECASE)
        return re.sub(r'\[\s*\^\s*cell_[^\]\r\n]*$', '', text, flags=re.IGNORECASE | re.MULTILINE)


    @staticmethod
    def _add_markdown_table(doc, table_lines: List[str]):
        rows = []
        for line in table_lines:
            raw = line.strip()
            inner = raw.strip('|').strip()
            if re.fullmatch(r'[\s:|-]+', inner):
                continue
            rows.append([cell.strip() for cell in raw.strip('|').split('|')])
        if not rows:
            return
        cols = max(len(row) for row in rows)
        table = doc.add_table(rows=0, cols=cols)
        try:
            table.style = "Table Grid"
        except Exception:
            pass
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for row_index, row in enumerate(rows):
            cells = table.add_row().cells
            for col_index in range(cols):
                text = row[col_index] if col_index < len(row) else ""
                text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
                cells[col_index].text = text
                for paragraph in cells[col_index].paragraphs:
                    paragraph.alignment = (
                        WD_ALIGN_PARAGRAPH.CENTER
                        if row_index == 0 or col_index > 0
                        else WD_ALIGN_PARAGRAPH.LEFT
                    )
                    for run in paragraph.runs:
                        run.font.size = Pt(9)
                        if row_index == 0:
                            run.font.bold = True
                            run.font.color.rgb = RGBColor(255, 255, 255)
                if row_index == 0:
                    shading = parse_xml(r'<w:shd {} w:fill="1E3D59"/>'.format(nsdecls('w')))
                    cells[col_index]._tc.get_or_add_tcPr().append(shading)
        doc.add_paragraph().paragraph_format.space_after = Pt(4)

    def export_report(
        self,
        report_title: str,
        school_name: str,
        sections: List[Dict[str, Any]],
        charts_dir: str,
        quality_summary: Optional[Dict[str, Any]] = None,
        generated_at: Optional[datetime] = None,
        organization: str = "",
        is_demo: bool = False,
    ) -> str:
        quality_summary = quality_summary or {}
        generated_at = generated_at or datetime.now()
        doc = Document()

        # 设置页面边距 (符合公文标准：上28mm，下28mm，左30mm，右30mm 约合 1.1~1.15 英寸)
        for section in doc.sections:
            section.top_margin = Inches(1.1)
            section.bottom_margin = Inches(1.1)
            section.left_margin = Inches(1.15)
            section.right_margin = Inches(1.15)

        # ==================== 1. 独立公文封皮页 ====================
        # 顶部空白
        p_top = doc.add_paragraph()
        p_top.paragraph_format.space_before = Pt(36)

        # 封皮顶眉
        p_org = doc.add_paragraph()
        p_org.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_org = p_org.add_run("高等教育本科教学质量常态监测与发展成效评估")
        r_org.font.size = Pt(14)
        r_org.font.bold = True
        r_org.font.color.rgb = RGBColor(100, 116, 139)
        p_org.paragraph_format.space_after = Pt(24)

        # 封面大标题
        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_title = p_title.add_run(report_title)
        r_title.font.size = Pt(24)
        r_title.font.bold = True
        r_title.font.color.rgb = RGBColor(30, 61, 89)  # 经典教务海军蓝
        p_title.paragraph_format.space_after = Pt(14)

        if is_demo:
            p_notice = doc.add_paragraph()
            p_notice.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r_notice = p_notice.add_run(
                "【示例报告】基于示例数据生成，仅用于功能体验，不得作为正式评估材料"
            )
            r_notice.font.size = Pt(12)
            r_notice.font.bold = True
            r_notice.font.color.rgb = RGBColor(180, 83, 9)
            p_notice.paragraph_format.space_after = Pt(10)

        # 封面副标
        p_sub = doc.add_paragraph()
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r_sub = p_sub.add_run("（数据驱动·穿透审计·全周期质检版本）")
        r_sub.font.size = Pt(13)
        r_sub.font.color.rgb = RGBColor(71, 85, 105)
        p_sub.paragraph_format.space_after = Pt(140)

        # 封面底部公文元信息框
        p_meta = doc.add_paragraph()
        p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_meta.paragraph_format.line_spacing = 1.6
        
        failed_count = int(quality_summary.get("sections_failed") or 0)
        outline_needs_attention = quality_summary.get("outline_approved") is False
        if quality_summary.get("needs_attention"):
            quality_parts = []
            if outline_needs_attention:
                score = quality_summary.get("outline_score")
                quality_parts.append(
                    f"大纲需复核{'' if score is None else f'（{round(float(score) * 100)} 分）'}"
                )
            if failed_count:
                quality_parts.append(f"{failed_count} 个小节核验异常")
            quality_verdict = "；".join(quality_parts) + "，暂不建议正式交付"
        elif quality_summary.get("can_deliver"):
            quality_verdict = f"{int(quality_summary.get('sections_total') or 0)} 个小节核验通过，可交付"
        else:
            quality_verdict = "待核验"
        runs_info = [
            f"评 估 对 象：{school_name}",
            f"编 制 单 位：{organization or school_name}",
            "数 据 底 座：原始 Excel 报表与单元格级溯源记录",
            f"质 检 裁 定：{quality_verdict}",
            f"编 制 日 期：{generated_at.year} 年 {generated_at.month} 月 {generated_at.day} 日",
        ]
        for idx, line in enumerate(runs_info):
            r = p_meta.add_run(line + ("\n" if idx < len(runs_info) - 1 else ""))
            r.font.size = Pt(11.5)
            r.font.color.rgb = RGBColor(51, 65, 85)

        # 封皮后插入分页符
        doc.add_page_break()

        # ==================== 2. 报告简目导航与原生目录域 ====================
        toc_p = doc.add_paragraph()
        toc_run = toc_p.add_run("【 报 告 概 览 与 章 节 目 录 】")
        toc_run.font.size = Pt(13)
        toc_run.font.bold = True
        toc_run.font.color.rgb = RGBColor(30, 61, 89)
        toc_p.paragraph_format.space_after = Pt(10)

        # 嵌入 Word 规范原生目录域代码 (TOC Field, Word 中自动生成带页码目录)
        p_toc_field = doc.add_paragraph()
        run_fld = p_toc_field.add_run()
        fldChar1 = parse_xml(r'<w:fldChar %s w:fldCharType="begin"/>' % nsdecls('w'))
        instrText = parse_xml(r'<w:instrText %s xml:space="preserve"> TOC \o "1-3" \h \z \u </w:instrText>' % nsdecls('w'))
        fldChar2 = parse_xml(r'<w:fldChar %s w:fldCharType="separate"/>' % nsdecls('w'))
        fldChar3 = parse_xml(r'<w:fldChar %s w:fldCharType="end"/>' % nsdecls('w'))
        run_fld._r.append(fldChar1)
        run_fld._r.append(instrText)
        run_fld._r.append(fldChar2)
        run_fld._r.append(fldChar3)

        for sec in sections:
            sec_p = doc.add_paragraph()
            sec_p.paragraph_format.line_spacing = 1.3
            sec_p.paragraph_format.space_after = Pt(3)
            r_item = sec_p.add_run(f"•  {self._strip_cell_citations(sec.get('title', ''))}")
            r_item.font.size = Pt(10.5)
            r_item.font.color.rgb = RGBColor(71, 85, 105)

        doc.add_page_break()

        # ==================== 3. 正文分章节排版 ====================
        all_citations_for_appendix = []
        in_mermaid = False

        for sec in sections:
            title = self._strip_cell_citations(sec.get("title", ""))
            level = sec.get("level", 1)
            content = sec.get("content", "")

            # 标题排版（使用 Heading 样式使得 Word 原生目录与导航窗格自动感知）
            heading_style = "Heading 1" if level == 1 else "Heading 2"
            try:
                h_p = doc.add_paragraph(style=heading_style)
            except Exception:
                h_p = doc.add_paragraph()

            h_p.paragraph_format.space_before = Pt(16)
            h_p.paragraph_format.space_after = Pt(8)
            h_p.paragraph_format.keep_with_next = True

            h_run = h_p.add_run(title)
            h_run.font.bold = True
            if level == 1:
                h_run.font.size = Pt(15)
                h_run.font.color.rgb = RGBColor(30, 61, 89)
            else:
                h_run.font.size = Pt(13)
                h_run.font.color.rgb = RGBColor(51, 65, 85)

            # 收集该章节正文中的所有引用
            for m in re.finditer(
                r'\[((?!\s*\^\s*cell_)[^\]\r\n]+)\]\s*\[\s*\^\s*(cell_[a-zA-Z0-9_]+)\s*\]',
                content, flags=re.IGNORECASE,
            ):
                source = next((
                    citation for citation in (sec.get("audit") or {}).get("citations", [])
                    if citation.get("cell_id") == m.group(2)
                ), {})
                source_location = (
                    f"{source.get('sheet_name', '')}!{source['cell_ref']}"
                    if source.get("cell_ref") else "见 Excel 对账表"
                )
                if source.get("is_verified") is True:
                    citation_status = "已匹配"
                elif source:
                    citation_status = "需人工复核"
                else:
                    citation_status = "待核验"
                all_citations_for_appendix.append({
                    "section_title": title,
                    "cited_text": self._strip_cell_citations(m.group(1)),
                    "source_location": source_location,
                    "status": citation_status,
                })

            # 正文段落与图表解析
            lines = self._strip_cell_citations(content).split("\n")
            index = 0
            while index < len(lines):
                line = lines[index]
                index += 1
                line_str = line.strip()
                if not line_str:
                    continue
                if (
                    not in_mermaid
                    and line_str.startswith("|")
                    and line_str.endswith("|")
                    and index < len(lines)
                    and re.fullmatch(r"\|?[\s:|-]+\|?", lines[index].strip())
                ):
                    table_lines = [line_str]
                    while index < len(lines) and lines[index].strip().startswith("|"):
                        table_lines.append(lines[index].strip())
                        index += 1
                    self._add_markdown_table(doc, table_lines)
                    continue

                # 识别 Mermaid 块开始与结束，杜绝语法外泄到 Word 正文
                if line_str.startswith("```mermaid"):
                    in_mermaid = True
                    # 插入占位提示
                    diag_p = doc.add_paragraph()
                    diag_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    diag_p.paragraph_format.space_before = Pt(6)
                    diag_p.paragraph_format.space_after = Pt(6)
                    d_run = diag_p.add_run("图：本节结构关系示意图（详见电子版报告）")
                    d_run.font.size = Pt(9.5)
                    d_run.font.italic = True
                    d_run.font.color.rgb = RGBColor(100, 116, 139)
                    continue
                elif in_mermaid:
                    if line_str.startswith("```"):
                        in_mermaid = False
                    continue

                if line_str.startswith("```"):
                    continue

                # 识别图片 Markdown: ![title](/api/assets/charts/xxx.png)
                img_match = re.search(r'!\[([^\]]*)\]\((.*?)\)', line_str)
                if img_match:
                    img_alt = img_match.group(1)
                    img_url = img_match.group(2)
                    img_name = os.path.basename(img_url)
                    img_path = os.path.join(charts_dir, img_name)

                    if os.path.exists(img_path):
                        img_p = doc.add_paragraph()
                        img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        img_p.paragraph_format.space_before = Pt(12)
                        img_p.paragraph_format.space_after = Pt(4)
                        doc.add_picture(img_path, width=Inches(5.6))

                        caption_p = doc.add_paragraph()
                        caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        cap_run = caption_p.add_run(f"图：{img_alt}")
                        cap_run.font.size = Pt(9.5)
                        cap_run.font.italic = True
                        cap_run.font.color.rgb = RGBColor(100, 116, 139)
                        caption_p.paragraph_format.space_after = Pt(10)
                    continue

                # 忽略模型重复输出的小节标题，避免 Markdown 标记落入 Word。
                if line_str.startswith(("## ", "### ")):
                    continue

                # 普通段落渲染：首行缩进，高保真学术公文排版
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing = 1.35
                p.paragraph_format.space_after = Pt(6)
                p.paragraph_format.first_line_indent = Inches(0.28)  # 约合中文两字符缩进

                clean_line = re.sub(r'\*\*(.*?)\*\*', r'\1', line_str)

                run = p.add_run(clean_line)
                run.font.size = Pt(11)
                run.font.color.rgb = RGBColor(30, 41, 59)

        # ==================== 4. 附录：全文核心指标数据穿透溯源清单 ====================
        if all_citations_for_appendix:
            doc.add_page_break()
            app_h = doc.add_paragraph()
            app_h.paragraph_format.space_before = Pt(16)
            app_h.paragraph_format.space_after = Pt(8)
            app_run = app_h.add_run("附录：全文核心指标数据穿透溯源清单")
            app_run.font.size = Pt(14)
            app_run.font.bold = True
            app_run.font.color.rgb = RGBColor(30, 61, 89)

            intro_p = doc.add_paragraph()
            intro_run = intro_p.add_run("本附录列示正文中所引关键统计数值的来源位置，便于逐项核验；核验状态表示该数值与原始单元格是否匹配。")
            intro_run.font.size = Pt(9.5)
            intro_run.font.color.rgb = RGBColor(100, 116, 139)
            intro_p.paragraph_format.space_after = Pt(12)

            # 插入对账表格
            headers = ["序号", "报告章节", "引用数值", "来源位置", "核验状态"]
            table = doc.add_table(rows=1, cols=len(headers))
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            table.autofit = False

            # 表头样式
            hdr_cells = table.rows[0].cells
            for idx, h_text in enumerate(headers):
                hdr_cells[idx].text = h_text
                shading_elm = parse_xml(r'<w:shd {} w:fill="1E3D59"/>'.format(nsdecls('w')))
                hdr_cells[idx]._tc.get_or_add_tcPr().append(shading_elm)
                for p in hdr_cells[idx].paragraphs:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    for r in p.runs:
                        r.font.size = Pt(9.5)
                        r.font.bold = True
                        r.font.color.rgb = RGBColor(255, 255, 255)

            # 填入数据行
            for row_idx, cit in enumerate(all_citations_for_appendix, 1):
                row_cells = table.add_row().cells
                row_cells[0].text = str(row_idx)
                row_cells[1].text = cit["section_title"]
                row_cells[2].text = cit["cited_text"]
                row_cells[3].text = cit["source_location"]
                row_cells[4].text = cit.get("status", "待核验")

                # 隔行浅灰斑马纹
                if row_idx % 2 == 0:
                    for c in row_cells:
                        shd = parse_xml(r'<w:shd {} w:fill="F8FAFC"/>'.format(nsdecls('w')))
                        c._tc.get_or_add_tcPr().append(shd)

                for c_idx, c in enumerate(row_cells):
                    for p in c.paragraphs:
                        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx in [0, 2, 4] else WD_ALIGN_PARAGRAPH.LEFT
                        for r in p.runs:
                            r.font.size = Pt(9)
                            if c_idx == 4:
                                r.font.color.rgb = (
                                    RGBColor(21, 128, 61)
                                    if c.text == "已匹配"
                                    else RGBColor(180, 83, 9)
                                )
                            else:
                                r.font.color.rgb = RGBColor(30, 41, 59)

        # 保存文件
        clean_school = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5]', '', school_name) or "高校"
        file_name = f"高校发展检验与质量评估报告_{clean_school}.docx"
        file_path = os.path.join(self.output_dir, file_name)
        doc.save(file_path)
        return file_path
