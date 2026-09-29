# 高校发展检验报告智能生成系统 (Pi-Agent 工业级侧车流水线版 v2.2)

> **基座引擎**：Pi-Agent 侧车智能体 (`pi-main` Node.js 22) + Python 数据工程微服务 (`excel_report_env` Python 3.12)  
> **核心架构**：确定性分阶段流水线（Deterministic Staged Pipeline）+ Node.js Pi-Agent 侧车智能体节点 + Jev 极速判定  
> **交付形态**：白色学术教务风格 Multi-Panel Studio 前端（Vue 3）+ 100% 穿透溯源数据湖（Cell Lake）  
> **生成模式**：**表格数据驱动的动态大纲**（用户上传任意 Excel，自动推导章节、自适应图表与数据绑定）

---

## 🌟 系统核心特性

1. **Pi-Agent 跨语言侧车智能体架构 (Route A - Sidecar IPC)**：
   - 采用标准 `stdio` 管道实现 Python 与 Node.js 22 侧车子进程的异步 IPC 通信，逐行流式接收 JSONL 事件流（`agent_info`、`chunk`、`done`）。
   - **双引擎自适应切换与平滑降级**：支持 `Pi-Agent 侧车模式` 与 `Python 原生极速模式`，若检测到 Node 运行环境异常，系统自动无感降级至 Python 原生引擎，保证 100% 稳定交付。

2. **数据驱动动态大纲与智能生长 (Stage 1 AI 规划)**：
   - Stage 1 自动扫描 DuckDB Catalog 与复合表头，根据用户上传的任意 Excel 报表由 Pi-Agent 侧车智能体进行全局章节拓扑编排与图表推荐。
   - 内置高校教育质量监测公文规范，支持未知新业务表（如科研、资产、智慧校园）自主“动态生长”出专属章节，彻底告别僵硬硬编码。

3. **STC 全格式复合表头结构感知解析 (.xls / .xlsx)**：
   - 深度支持 `.xls` (xlrd) 与 `.xlsx` (openpyxl) 格式，自动识别跨行跨列合并单元格（Merged Cell Ranges）并完成前向填充（Forward Fill）。
   - 自动生成指标绝对层级路径（如 `师资队伍 > 职称结构 > 正高级`、`高层次人才 > 领军人才`）。

4. **100% 穿透式单元格数据审计湖 (Cell Lake)**：
   - 使用 SQLite 将每个单元格物理坐标精确归档入库：`(file_name, sheet_name, row, col, cell_ref, raw_value, metric_path)`。
   - 正文每个引用数值均携带 `[^doc_cell_id]` 锚点。
   - 前端悬浮穿透气泡（Popover）可实时反查并呈现原始 Excel 文件名、工作表与单元格编号（如 `C14`）。

5. **Stage 4 质检自愈重审闭环 (Quality Gate Closed Loop)**：
   - 引入正则反查断言（100% 真实值吻合）与 Jev 极速质量打分（>= 0.85）。
   - 若章节质检未通过，流水线自动触发 Agent 带反馈重写（Refining Retry）机制，实现自愈闭环。

6. **高校名称智能感知与手动覆盖**：
   - 自动从常态监测元数据表中智能提取高校全称（如“海南师范大学”），前端顶栏提供直观输入框支持手动重命名，并实时联动更新大纲、封面与导出 Word 报告。

7. **双重交付物规范导出**：
   - **学术公文规范 Word 报告（`.docx`）**：包含正式公文封面页、目录页（TOC）、多级标题编号、嵌入式高清图表、Mermaid 流程图与附录全量穿透数据审计总表。
   - **《数据穿透审计与指标覆盖清单》（`.xlsx`）**：
     - Sheet 1: 指标覆盖率矩阵（已覆盖指标、来源表与关联章节）。
     - Sheet 2: 全文数字对账总表（报告所引数值、物理文件、Sheet、单元格坐标、原始值、质检吻合状态）。

8. **500+ Excel 高通量支撑与两级分层拓扑架构（100+ 页长报告规划）**：
   - **高并发并行入湖**：支持通过 `/api/scan_directory` 递归扫描本地多级文件夹，Python 多线程并行解析复合表头，SQLite 开启 WAL 高并发写入与分块批处理（Batch Size=5000），毫秒级完成数万物理单元格入湖；
   - **数据驱动两级分层拓扑（Two-Level Topology）**：彻底摒弃“将所有 Excel 内容喂给大模型”的粗暴模式。先将表格预聚类并强绑定至宏观领域（`bound_tables`、`bound_files`），再根据表格密度 $N$ 自适应确定细分小节（$N \le 3 \rightarrow 1$节；$4 \le N \le 12 \rightarrow 2\sim 4$节；$N > 12 \rightarrow 5\sim 8$节）；
   - **Stage 1 Jev 架构质检断言**：在生成正文前由 Jev 裁判模型对大纲结构与物理表绑定率进行合规评估（`structure_score`），低于 0.85 自动微调；
   - **定向范围检索（Targeted Scope Retrieval）**：Stage 2 仅穿透提取本小节预绑定的表格数据，严格控制上下文，杜绝 20万 Token 上下文超限与大模型注意力发散；
   - **增量断点持久化（Checkpointing）**：每小节完成质检后自动写入 `data/checkpoints/`，保障百页级超长篇幅报告断点续跑。

---

### 系统全流程运行架构图

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
│  Stage 1: 规划阶段 ───> Pi-Agent 侧车/规则引擎，数据驱动动态规划章节与图表   │
│           │                                                                 │
│           ▼                                                                 │
│  Stage 2: 检索阶段 ───> 表级精准下推，毫秒级提取真实坐标与统计指标 (0 Token) │
│           │                                                                 │
│           ▼                                                                 │
│  Stage 3: 撰写阶段 ───> Pi-Agent 侧车流式撰写 + 注入 [数值][^cell_id] 锚点    │
│           │            + 触发 chart-tool 自动直插 300DPI 学术统计图表       │
│           ▼                                                                 │
│  Stage 4: 质检阶段 ───> 100% 单元格反查严格断言 + Jev 极速打分 (失败自动重写) │
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
│   ├── test_xlsx_and_custom_school.py # .xlsx 复合表头与学校名称嗅探集成测试
│   ├── test_pi_bridge.py           # Pi-Agent 跨语言 IPC 桥接与大纲流式测试
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
│   │   │   ├── docx_exporter.py    # 学术规范 Word (.docx) 封面/TOC/图文研报导出器
│   │   │   └── excel_exporter.py   # 数据穿透对账总表 (.xlsx) 双表导出器
│   │   ├── pipeline/               # 确定性 5 阶段调度核心
│   │   │   ├── stages.py           # 5 阶段流水线调度器 (含自愈重审与图表规划)
│   │   │   ├── agent_runner.py     # Pi-Agent 撰写调度器 (支持 Pi 侧车/Python 原生)
│   │   │   ├── pi_bridge.py        # Python 与 Node.js Pi-Agent stdio IPC 桥接器
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
│   ├── vite.config.ts              # Vite 代理与工程构建配置 (代理至 8008 端口)
│   ├── index.html                  # 单页面应用入口
│   └── src/
│       ├── App.vue                 # 白色教务公文风 Multi-Panel Studio 主工作台
│       ├── style.css               # 学术公文规范排版设计系统
│       └── main.ts                 # Vue 应用初始化入口
├── example/                        # 高校真实本科教学状态评估报表 (.xls)
├── pi-main/                        # Pi-Agent 底座工程
│   └── pi_agent_sidecar.mjs        # Node.js 22 原生 ES Module 侧车智能体执行器
├── run_backend.bat                 # 后端一键启动脚本 (端口 8008，ANSI/GBK CRLF 格式)
├── run_frontend.bat                # 前端一键启动脚本 (端口 5173，ANSI/GBK CRLF 格式)
├── start_all.bat                   # 前后端双服务一键联动启动脚本 (ANSI/GBK 格式)
└── start_all.ps1                   # PowerShell 跨平台双服务启动脚本
```

---

## 🚀 启动与使用指南

### 1. 一键启动前后端服务
双击根目录下的 **`start_all.bat`**，系统将自动弹出两个终端窗口分别启动 FastAPI 后端（端口 `8008`）与 Vue 3 前端（端口 `5173`）。

> 💡 **端口设计说明**：为了彻底避开常见本地软件（如电子书阅读器 NeatReader、IIS 等）对 `8000` 端口的独占冲突，后端服务默认运行在专属的 **`8008`** 端口上，前端 Vite 代理已自动完成对齐。

启动完成后，使用现代浏览器打开：
👉 **`http://localhost:5173`**

### 2. 操作流程指引
1. **载入数据**：
   - 点击顶栏右侧 **“📥 一键载入高校示例数据”**，系统自动执行 STC 复合表头解析，将 2200+ 个单元格物理坐标录入 Cell Lake，向 DuckDB 注册宽表，并自动嗅探出学校名称。
   - 或直接在左侧拖拽上传您自己的高校报表（支持 `.xls` 与 `.xlsx` 格式）。
2. **大模型与智能体引擎配置（可选）**：
   - 点击顶栏 **“⚙️ 设置”** 按钮打开设置面板：
     - 可填入您的 DeepSeek API Key 与模型端点。
     - **生成引擎模式切换**：支持选择 **🚀 Pi-Agent 侧车模式**（默认，Node.js 侧车子进程驱动）或 **🐍 Python 原生模式**。
     - 若未配置 API Key，侧车引擎将自动启用高保真教育公文启发式生成，同样支持完整的单元格穿透与高清图表。
3. **高校名称覆盖（可选）**：
   - 顶栏中心显示当前嗅探出的高校名称（如“海南师范大学”），可直接手动修改，修改后将同步覆盖后续报告标题、公文封皮与导出文档。
4. **启动全流程流水线**：
   - 点击顶栏右侧绿色按钮 **“🚀 一键运行全部阶段”**。
   - 界面实时展现：
     - Stage 1: 由 Pi-Agent 侧车智能体结合数据湖完成大纲规划，左侧导航树动态刷新；
     - Stage 2~4: 逐小节流式打字输出学术论述、绘制高清图表，并执行 Jev 质检与自愈闭环。
5. **交互式穿透审计**：
   - **将鼠标悬停在右侧报告中的任意引用数字上**（如 `[64个]`），即可弹出穿透审计气泡，直观查验其原始文件、工作表、物理坐标（如 `C14`）与数值。
6. **一键导出正式成果物**：
   - 点击右侧面板顶部的 **“📄 导出 Word 报告”**，下载排版精美的官方 `.docx` 研报（含封皮、目录、高清图表与附录对账表）。
   - 点击 **“📊 导出对账总表 (.xlsx)”**，下载包含《指标覆盖率矩阵》与《全文数字对账总表》的穿透审计交付物。

---

## 🛠️ 本地开发与环境初始化

* **Python 后端环境**：推荐 Python 3.12（如 Conda 环境）：
  ```bash
  pip install -r backend/requirements.txt
  ```
* **Node.js 运行环境**：需要 Node.js 20+ 或 22+（已验证 Node.js v22.14）：
  ```bash
  cd frontend
  npm install
  ```
* **自动化测试运行**：
  ```bash
  cd backend
  python -m unittest test_core.py test_dynamic_outline.py test_xlsx_and_custom_school.py
  python test_pi_bridge.py
  python test_e2e_pipeline.py
  ```

> 📘 完整的团队协作与开发分支规范，请参阅根目录专属指南：[**`CONTRIBUTING.md`**](file:///d:/vs_project/excel_report/CONTRIBUTING.md)。
