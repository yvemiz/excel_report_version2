import os
import uuid
from typing import List, Dict, Any, Optional
import matplotlib
matplotlib.use("Agg")  # 非交互模式
import matplotlib.pyplot as plt
import numpy as np

# 设置中文字体与学术优雅样式
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 高雅学术色彩盘 (Navy, Slate Blue, Teal, Amber, Crimson, Sage)
ACADEMIC_COLORS = [
    "#1e3d59",  # 深海军蓝
    "#17b978",  # 薄荷翠绿
    "#ff6e40",  # 珊瑚暖橙
    "#438a5e",  # 雅致青绿
    "#4a4e69",  # 暮霭灰紫
    "#f6c90e",  # 金黄亮色
    "#226b80",  # 深湖水蓝
    "#822659"   # 暗红石榴
]

class ChartService:
    """
    Python 高清学术统计图表生成服务 (chart-tool 后端底座)
    支持柱状图、折线图、饼图/环形图、雷达图等，产出 300 DPI 矢量级 PNG 图片
    """

    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_chart(
        self,
        chart_type: str,
        title: str,
        labels: List[str],
        data: List[float],
        series_name: str = "数值",
        x_label: Optional[str] = None,
        y_label: Optional[str] = None
    ) -> Dict[str, str]:
        """根据类型生成统计图并保存"""
        chart_id = f"chart_{uuid.uuid4().hex[:10]}"
        file_name = f"{chart_id}.png"
        file_path = os.path.join(self.output_dir, file_name)

        fig, ax = plt.subplots(figsize=(8, 4.8), dpi=200)
        # 背景设置为清爽纯白，契合教务公文严谨风格
        fig.patch.set_facecolor('#ffffff')
        ax.set_facecolor('#fafbfc')

        # 浅色网格线
        ax.grid(True, linestyle="--", alpha=0.4, color="#cbd5e1", zorder=0)

        chart_type = chart_type.lower()
        if chart_type in ["bar", "column"]:
            colors = ACADEMIC_COLORS[:len(labels)] if len(labels) <= len(ACADEMIC_COLORS) else ACADEMIC_COLORS * 3
            bars = ax.bar(labels, data, color=colors[:len(labels)], width=0.55, edgecolor="#ffffff", linewidth=1.2, zorder=3)
            # 在柱子上方标注数值
            for bar in bars:
                height = bar.get_height()
                ax.annotate(f"{height:g}",
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom', fontsize=9, fontweight='bold', color='#1e293b')
            plt.xticks(rotation=20 if len(labels) > 6 else 0, ha='right' if len(labels) > 6 else 'center', fontsize=9)

        elif chart_type in ["pie", "donut"]:
            ax.clear()
            ax.set_facecolor('#ffffff')
            colors = ACADEMIC_COLORS[:len(labels)] if len(labels) <= len(ACADEMIC_COLORS) else ACADEMIC_COLORS * 3
            wedges, texts, autotexts = ax.pie(
                data,
                labels=labels,
                autopct='%1.1f%%',
                startangle=140,
                colors=colors[:len(labels)],
                pctdistance=0.75,
                wedgeprops=dict(width=0.45, edgecolor='#ffffff', linewidth=1.5)  # 优雅甜甜圈环形
            )
            for autotext in autotexts:
                autotext.set_color('#ffffff')
                autotext.set_fontweight('bold')
                autotext.set_fontsize(9)

        elif chart_type in ["line", "trend"]:
            ax.plot(labels, data, marker='o', linewidth=2.5, markersize=6, color="#1e3d59", label=series_name, zorder=3)
            for i, val in enumerate(data):
                ax.annotate(f"{val:g}", (labels[i], val), textcoords="offset points", xytext=(0, 6), ha='center', fontsize=9, fontweight='bold', color="#1e3d59")

        elif chart_type == "radar":
            plt.close(fig)
            return self._generate_radar(chart_id, title, labels, data, series_name)

        ax.set_title(title, fontsize=12, fontweight='bold', pad=15, color='#0f172a')
        if x_label:
            ax.set_xlabel(x_label, fontsize=10, color='#475569')
        if y_label:
            ax.set_ylabel(y_label, fontsize=10, color='#475569')

        # 隐藏上方和右侧边框
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#cbd5e1')
        ax.spines['bottom'].set_color('#cbd5e1')

        plt.tight_layout()
        plt.savefig(file_path, format="png", bbox_inches="tight", dpi=200)
        plt.close(fig)

        url = f"/api/assets/charts/{file_name}"
        return {
            "chart_id": chart_id,
            "file_name": file_name,
            "file_path": file_path,
            "url": url,
            "markdown": f"![{title}]({url})"
        }

    def _generate_radar(self, chart_id: str, title: str, categories: List[str], values: List[float], series_name: str) -> Dict[str, str]:
        N = len(categories)
        if N < 3:
            N = 3
            categories = categories + ["指标项"] * (3 - len(categories))
            values = values + [0] * (3 - len(values))

        angles = [n / float(N) * 2 * np.pi for n in range(N)]
        values_loop = values + values[:1]
        angles_loop = angles + angles[:1]

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True), dpi=200)
        fig.patch.set_facecolor('#ffffff')

        plt.xticks(angles, categories, color='#334155', size=10)
        ax.set_rlabel_position(0)
        
        ax.plot(angles_loop, values_loop, linewidth=2, linestyle='solid', color='#1e3d59', label=series_name)
        ax.fill(angles_loop, values_loop, color='#1e3d59', alpha=0.25)
        ax.set_title(title, size=12, fontweight='bold', y=1.08, color='#0f172a')

        file_name = f"{chart_id}.png"
        file_path = os.path.join(self.output_dir, file_name)
        plt.tight_layout()
        plt.savefig(file_path, format="png", bbox_inches="tight", dpi=200)
        plt.close(fig)

        url = f"/api/assets/charts/{file_name}"
        return {
            "chart_id": chart_id,
            "file_name": file_name,
            "file_path": file_path,
            "url": url,
            "markdown": f"![{title}]({url})"
        }
