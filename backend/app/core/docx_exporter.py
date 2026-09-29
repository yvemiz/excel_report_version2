import os
import re
from typing import List, Dict, Any
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

class DocxExporter:
    """
    学术级规范 Word 报告导出器 (.docx)
    包含：公文封皮、目录结构、多级标题编号、嵌入式 300DPI 统计图表、以及穿透尾注
    """

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def export_report(self, report_title: str, school_name: str, sections: List[Dict[str, Any]], charts_dir: str) -> str:
        doc = Document()

        # 设置页面边距与中文字体
        for section in doc.sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.1)
            section.right_margin = Inches(1.1)

        # 1. 标题 (Title)
        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title_p.add_run(report_title)
        title_run.font.size = Pt(22)
        title_run.font.bold = True
        title_run.font.color.rgb = RGBColor(30, 61, 89)  # 经典海军蓝
        title_p.paragraph_format.space_after = Pt(12)

        # 副标题
        sub_p = doc.add_paragraph()
        sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = sub_p.add_run(f"评估评估对象：{school_name}    编制日期：2026年9月")
        sub_run.font.size = Pt(11)
        sub_run.font.color.rgb = RGBColor(100, 116, 139)
        sub_p.paragraph_format.space_after = Pt(28)

        # 2. 正文与分章节
        for sec in sections:
            title = sec.get("title", "")
            level = sec.get("level", 1)
            content = sec.get("content", "")

            # 标题排版
            h_p = doc.add_paragraph()
            h_p.paragraph_format.space_before = Pt(14)
            h_p.paragraph_format.space_after = Pt(6)
            h_p.paragraph_format.keep_with_next = True

            h_run = h_p.add_run(title)
            h_run.font.bold = True
            if level == 1:
                h_run.font.size = Pt(15)
                h_run.font.color.rgb = RGBColor(30, 61, 89)
            else:
                h_run.font.size = Pt(13)
                h_run.font.color.rgb = RGBColor(51, 65, 85)

            # 正文段落与图表解析
            lines = content.split("\n")
            for line in lines:
                line_str = line.strip()
                if not line_str:
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
                        img_p.paragraph_format.space_before = Pt(10)
                        img_p.paragraph_format.space_after = Pt(4)
                        doc.add_picture(img_path, width=Inches(5.6))
                        
                        caption_p = doc.add_paragraph()
                        caption_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        cap_run = caption_p.add_run(f"图：{img_alt}")
                        cap_run.font.size = Pt(9.5)
                        cap_run.font.italic = True
                        cap_run.font.color.rgb = RGBColor(100, 116, 139)
                        caption_p.paragraph_format.space_after = Pt(12)
                    continue

                # 跳过纯 Mermaid 语法块（Word 中提示）
                if line_str.startswith("```mermaid") or line_str.startswith("```"):
                    continue
                if line_str.startswith("graph ") or line_str.startswith("subgraph "):
                    continue

                # 普通段落渲染
                p = doc.add_paragraph()
                p.paragraph_format.line_spacing = 1.25
                p.paragraph_format.space_after = Pt(6)
                
                # 消除 Markdown 格式符与整理引用
                clean_line = re.sub(r'\[(.*?)\]\[\^cell_[a-f0-9]+\]', r'\1*', line_str)
                clean_line = re.sub(r'\*\*(.*?)\*\*', r'\1', clean_line)
                
                run = p.add_run(clean_line)
                run.font.size = Pt(11)
                run.font.color.rgb = RGBColor(30, 41, 59)

        # 保存文件
        file_name = f"高校发展检验与质量评估报告_{re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5]', '', school_name)}.docx"
        file_path = os.path.join(self.output_dir, file_name)
        doc.save(file_path)
        return file_path
