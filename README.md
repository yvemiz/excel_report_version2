# 高校发展检验报告智能生成系统 (Pi-Agent 工业级流水线版 v2.1)

> **基座引擎**：Pi-Agent (`pi-main`) + Python 数据工程微服务 (`excel_report_env`)  
> **核心架构**：确定性分阶段流水线（Deterministic Staged Pipeline）+ 单 Pi-Agent 核心撰写节点 + Jev 极速判定  
> **交付形态**：白色学术教务风格 Multi-Panel Studio 前端（Vue 3）+ 100% 穿透溯源数据湖（Cell Lake）  
> **生成模式**：**表格数据驱动的动态大纲**（用户上传任意 Excel，自动推导章节与自适应图表）

---

## 🌟 系统核心特性

1. **单 Agent 确定性流水线 (0 死循环、0 幻觉)**：
   - 彻底摒弃多 Agent 自由对话协商缺陷，采用 5 阶段状态机（Stage 1 规划 -> Stage 2 检索 -> Stage 3 撰写 -> Stage 4 质检 -> Stage 5 汇编）。
   - **数据驱动动态大纲**：Stage 1 自动扫描 DuckDB Catalog 与复合表头，根据用户上传的任意 Excel 报表动态生长对应章节；支持自适应推荐折线图、柱状图或环形图，并由 DuckDB 查询真实数值。
   - 数据检索阶段坚决由 Python/DuckDB 参数化执行，实现 **0 Token 消耗、毫秒级响应、100% 真实**。

2. **穿透式数据审计湖 (Cell Lake)**：
   - 使用 SQLite 将每个单元格物理坐标归档入库：`(file_name, sheet_name, row, col, cell_ref, raw_value, metric_path)`。
   - 正文每个引用数值均携带 `[^doc_cell_id]` 锚点。
   - 前端悬浮穿透气泡（Popover）可实时反查并呈现原始 Excel 文件名、工作表与单元格编号（如 `C14`）。

3. **双重图表生成体系（报告必须有图）**：
   - **`chart-tool` 高清学术统计图表**：Pi-Agent 自动调用 Python Matplotlib/Seaborn 绘图引擎，生成 300 DPI 柱状图、折线图、环形图、雷达图，直插 Word 报告与前端。
   - **`grok-mermaid` 拓扑流程图**：原生生成并渲染高校学科网络与组织构架 Mermaid 图。

4. **双份成品一键导出**：
   - **带学术排版的正式报告（`.docx`）**：公文封皮、目录、多级标题编号、嵌入式高清图表与尾注。
   - **《数据穿透审计与指标覆盖清单》（`.xlsx`）**：
     - Sheet 1: 指标覆盖率矩阵（已覆盖指标、来源表与关联章节）。
     - Sheet 2: 全文数字对账总表（报告所引数值、物理文件、Sheet、单元格坐标、原始值、质检吻合状态）。

5. **白色清爽教务系统界面风格**：
   - 纯白背景与深蓝教务基调，三栏 Multi-Panel 工作台，信息高密度、高可读性。

### 系统全流程运行架构图（通用兼容格式）

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│             🏫 高校发展检验报告智能生成系统 - 5阶段确定性流水线全景图          │
│                                                                             │
│  [原始 Excel 数据源 (.xls/.xlsx)]                                           │
│           │                                                                 │
│           ▼ (STC 复合表头结构感知解析器: 跨行跨列合并单元格前向填充)         │
│  [SQLite 单元格湖] (物理坐标归档存底) <─> [DuckDB 分析引擎] (0-Token参数化计算)│
│                                            │                                │
│                                            ▼                                │
│  Stage 1: 规划阶段 ───> 扫描 Catalog 与复合表头，数据驱动动态规划章节与图表  │
│           │                                                                 │
│           ▼                                                                 │
│  Stage 2: 检索阶段 ───> 表级精准下推，毫秒级提取真实坐标与统计指标 (0 Token) │
│           │                                                                 │
│           ▼                                                                 │
│  Stage 3: 撰写阶段 ───> Pi-Agent 学术流式撰写 + 注入 [数值][^cell_id] 锚点   │
│           │            + 触发 chart-tool 自动直插 300DPI 学术统计图表       │
│           ▼                                                                 │
│  Stage 4: 质检阶段 ───> 100% 单元格反查严格断言 + Jev 极速质量打分 (0.95/通过)│
│           │                                                                 │
│           ▼                                                                 │
│  Stage 5: 汇编阶段 ───> 导出学术 Word 研报 (.docx) + 数据穿透对账表 (.xlsx) │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 完整项目目录结构


```text
excel_report/
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI 自动化语法与构建检测流水线
├── .env.example                    # 环境变量配置示例模板 (不含敏感 Key)
├── .gitignore                      # 工业级 Git 忽略配置 (隔离密钥、数据库与依赖)
├── CONTRIBUTING.md                 # 团队协作与分支合并规范指引 (新开发者必读)
├── README.md                       # 项目总体介绍与运行使用指南 (本文档)
├── SYSTEM_WORKFLOW.md              # 全流程技术实现与业务流转说明书
├── excel_report_agent_system_architecture.md # 系统总体架构设计白皮书
├── backend/                        # FastAPI 后端服务工程
│   ├── requirements.txt            # Python 核心依赖清单 (Python 3.12)
│   ├── test_core.py                # 底座核心模块 (STC/CellLake/DuckDB) 单元测试
│   ├── test_dynamic_outline.py     # 数据驱动动态大纲与自适应图表推导测试
│   ├── test_e2e_pipeline.py        # 端到端 5 阶段全自动化流水线集成测试
│   ├── app/
│   │   ├── config.py               # 项目路径与模型服务环境变量配置
│   │   ├── main.py                 # FastAPI 服务入口与静态/CORS 路由挂载
│   │   ├── core/                   # 数据工程与穿透审计底座核心模块
│   │   │   ├── stc_parser.py       # STC 复合表头结构感知解析器 (.xls / .xlsx)
│   │   │   ├── cell_lake.py        # SQLite 单元格溯源湖 (Cell Lake 物理坐标存底)
│   │   │   ├── duckdb_engine.py    # DuckDB 列式指标分析引擎 (0 Token 参数化计算)
│   │   │   ├── chart_service.py    # Matplotlib 300DPI 学术统计图表渲染引擎
│   │   │   ├── audit_service.py    # 正则反查与 100% 单元格坐标穿透断言服务
│   │   │   ├── docx_exporter.py    # 学术规范 Word (.docx) 图文研报导出器
│   │   │   └── excel_exporter.py   # 数据穿透对账总表 (.xlsx) 双表导出器
│   │   ├── pipeline/               # 确定性 5 阶段调度核心
│   │   │   ├── stages.py           # 5 阶段流水线调度器 (含动态大纲与自适应图表)
│   │   │   ├── agent_runner.py     # 单 Pi-Agent 核心学术研报撰写节点 (流式/确定性)
│   │   │   └── jev_judge.py        # Jev 极速质量决策与逻辑打分器
│   │   └── api/                    # RESTful & WebSocket API 路由
│   │       ├── routes_upload.py    # 文件上传、STC 解析与示例数据载入 API
│   │       ├── routes_pipeline.py  # 流水线执行与 WebSocket / SSE 流式推送 API
│   │       └── routes_export.py    # Word 研报与 Excel 穿透对账表下载 API
│   ├── data/                       # 本地数据存储与导出目录 (已由 .gitignore 隔离)
│   │   ├── cell_lake.db            # SQLite 单元格湖数据库文件
│   │   ├── metrics.duckdb          # DuckDB 列式指标存储数据库文件
│   │   ├── exports/                # 动态生成的 Word 与 Excel 成果物下载目录
│   │   └── uploads/                # 临时上传的原始 Excel 文件目录
│   └── static/charts/              # 动态生成的 300DPI 学术矢量统计图表存储目录
├── frontend/                       # Vue 3 前端工程 (Vite + TypeScript + Pinia)
│   ├── package.json                # 前端依赖配置
│   ├── tsconfig.json               # TypeScript 配置文件
│   ├── vite.config.ts              # Vite 代理与工程构建配置
│   ├── index.html                  # 单页面应用入口
│   └── src/
│       ├── App.vue                 # 白色教务公文风 Multi-Panel Studio 主工作台
│       ├── style.css               # 学术公文规范排版设计系统
│       └── main.ts                 # Vue 应用初始化入口
├── example/                        # 8 份高校真实本科教学状态评估报表 (.xls)
├── pi-main/                        # Pi-Agent 底座源码及插件套件
├── run_backend.bat                 # 后端一键启动脚本 (端口 8000，GBK 编码)
├── run_frontend.bat                # 前端一键启动脚本 (端口 5173，GBK 编码)
├── start_all.bat                   # 前后端双服务一键联动启动脚本 (GBK 编码)
└── start_all.ps1                   # PowerShell 跨平台双服务启动脚本
```

---

## 🚀 启动与使用指南

### 1. 一键启动前后端服务
双击根目录下的 **`start_all.bat`**，系统将自动弹出两个终端窗口分别启动 FastAPI 后端（端口 8000）与 Vue 3 前端（端口 5173）。

启动完成后，使用现代浏览器打开：
👉 **`http://localhost:5173`**

### 2. 操作流程指引
1. **载入数据**：
   - 点击顶栏右侧 **“📥 一键载入高校示例数据 (8份表)”**，系统自动执行 STC 复合表头解析，将 2200+ 个单元格物理坐标录入 Cell Lake，并向 DuckDB 注册 8 个宽表。
   - 或直接在左侧拖拽上传您自己的教育部高校评估报表（`.xls` / `.xlsx`）。
2. **大模型配置（可选）**：
   - 点击顶栏 **“⚙️ 模型设置 (DeepSeek)”**，可填入您的 DeepSeek API Key。
   - 若未填入 Key，系统将自动切换为**高保真确定性真实数据合成引擎**，依然完整执行 5 阶段流水线、100% 真实单元格穿透与高清图表生成。
3. **启动生成**：
   - 点击顶栏右侧绿色按钮 **“🚀 启动全流程生成流水线”**。
   - 中间面板将实时呈现 5 阶段步进状态、各章节 Todo 进展、Jev 毫秒级打分与单元格反查吻合率。
4. **研报交互与穿透反查**：
   - 右侧实时流式呈现带有官方排版的正式学术研报与内嵌图表。
   - **将鼠标悬停在任意引用的数字上**（如 `[64个]`），即可浮现单元格穿透审计气泡，查看其真实来源文件、工作表、坐标（如 `C14`）及原始值。
5. **一键导出成果**：
   - 点击右侧面板顶部的 **“📄 导出 Word 报告”**，下载格式完美的学术 Word 报告（`.docx`）。
   - 点击 **“📊 导出对账总表 (.xlsx)”**，下载带有《指标覆盖率矩阵》与《全文数字对账总表》的双表 Excel 穿透审计交付物。

---

## ⚠️ 团队协作与开发规范（新开发者必读）

为了防止多人协作导致代码冲突、破坏主干或泄露密钥，所有参与本项目开发的同学请**务必严格遵守**以下规范：

### 1. 🚫 四大绝对红线（违者直接驳回 PR）
* **严禁直推主分支**：主分支（`master` / `main`）受保护锁定，**严禁直接在主分支写代码或提交**，必须通过个人功能分支发起 Pull Request (PR)。
* **严禁强制推送**：严禁使用 `git push --force` 或 `git push -f` 覆盖远端提交。
* **严禁提交密钥**：严禁在任何代码、配置文件中硬编码真实的 `sk-...` API Key。本地如需配置，请复制 `.env.example` 为 `.env`（已配置 `.gitignore` 自动忽略）。
* **严禁提交生成物与大文件**：严禁提交 `node_modules/`、`backend/data/*.db`、`backend/data/*.duckdb`、`backend/data/exports/*` 以及 `__pycache__/` 等二进制文件与缓存。

### 2. 🚀 新手标准开发流程（极简四步口诀）

```bash
# ① 开发前：拉取主分支最新代码并切出个人分支
git checkout master
git pull origin master
git checkout -b feature/功能名称-你的姓名拼音     # 例如 feature/parse-header-zhangsan

# ② 开发中：在个人分支上编写代码、本地测试

# ③ 提交前：严禁无脑使用 git add .，先自检变动文件！
git status
git add backend/app/xxx.py frontend/src/xxx.vue   # 仅添加你修改的代码文件
git commit -m "feat: 简短描述新增功能或修复内容"
git push origin feature/功能名称-你的姓名拼音

# ④ 合并时：在 GitHub 网页上发起 Pull Request (PR)
# 等待 GitHub Actions CI 自动化检查变绿，并联系负责人 Review 通过后通过 Squash 压缩合并入主干。
```

### 3. 🛠️ 本地环境初始化准备
* **Python 后端环境**：推荐 Python 3.12（如 Conda 环境），首次运行需安装依赖：
  ```bash
  pip install -r backend/requirements.txt
  ```
* **Node.js 前端环境**：需要 Node.js 18+ 或 20+：
  ```bash
  cd frontend
  npm install
  ```
* **一键启动**：日常开发双击根目录的 `start_all.bat` 即可同时启动前后端。

> 📘 完整的开发准则、冲突解决与提交流程，请参阅根目录专属指南：[**`CONTRIBUTING.md`**](file:///d:/vs_project/excel_report/CONTRIBUTING.md)。
