# 团队协作开发指南与规范 (Contributing Guide v2.2)

欢迎参与本项目开发！为了保证代码质量与版本库干净稳定，请所有开发同学严格遵守本规范。

---

## 🚫 新手开发“五大禁令”（绝对红线）

1. **绝对禁止直接在 `main` / `master` 分支写代码并提交**。
2. **绝对禁止使用 `git push --force` 或 `-f` 强推覆盖代码**。
3. **绝对禁止将任何真实密钥（如 `sk-...` API Key）写入代码或配置文件**。
4. **绝对禁止向 Git 提交 `.env`、`node_modules/`、`backend/data/*.db`、`backend/data/*.duckdb`、`backend/data/exports/*` 等缓存或数据库文件**。
5. **绝对禁止将 Windows 批处理脚本（`.bat`）保存为 Unix LF 换行或 UTF-8 编码**：Windows `cmd.exe` 要求批处理文件必须使用 **CRLF (`\r\n`)** 换行符与 **ANSI / GBK** 编码，否则会导致命令粘连与乱码。

---

## 🚀 标准开发流程：四步走

```text
┌────────────────────────────────────────────────────────┐
│               1. 拉取最新 master 并切新分支             │
│        git checkout -b feature/xxx-你的姓名             │
└───────────────────────────┬────────────────────────────┘
                            │ (在个人分支上编写与调试)
                            ▼
┌────────────────────────────────────────────────────────┐
│            2. 自检文件并推送到远端个人分支              │
│       git status -> git add -> git commit -> git push  │
└───────────────────────────┬────────────────────────────┘
                            │ (在 GitHub 网页发起申请)
                            ▼
┌────────────────────────────────────────────────────────┐
│            3. 提交 PR (Pull Request) 申请              │
│       点击 Compare & pull request 按钮填写修改说明      │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
╭────────────────────────────────────────────────────────╮
│          4. GitHub Actions CI 自动化守门检测           │
│   • Python 语法与依赖导入检测   • 前端 TypeScript/打包  │
╰───────────────────────────┬────────────────────────────╯
                            │ 自动化全部通过 (变绿)
                            ▼
╭────────────────────────────────────────────────────────╮
│             5. 项目负责人 Code Review 审核             │
╰───────────────────────────┬────────────────────────────╯
              /                            \
             / 不合规打回                   \ 审核批准
            ▼                               ▼
┌─────────────────────────┐   ┌──────────────────────────┐
│   新手本地修改后 push    │   │  点击 Squash and merge   │
│   PR 页面将自动同步更新  │   │  压缩合并入 master 分支  │
└─────────────────────────┘   └─────────────┬────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │ 6. master 主干安全更新 🔒 │
                              └──────────────────────────┘
```

### 第一步：同步最新代码并创建个人功能分支


每次准备写新功能或修 Bug 前，先拉取主干最新进度，然后切出新分支：

```bash
# 1. 切回主分支
git checkout master

# 2. 拉取最新进度
git pull origin master

# 3. 创建并切换到自己的功能分支 (分支命名规则：feature/功能简写-你的名字 或 fix/bug名称)
git checkout -b feature/upload-excel-zhangsan
```

### 第二步：在个人分支上进行本地开发与调试

- **Python 后端开发**：运行环境为 Python 3.12（端口 `8008`），新增依赖请同步记录到 `backend/requirements.txt`。
- **前端开发**：运行环境为 Node.js 20+ / 22+（端口 `5173`），新增依赖请同步记录到 `frontend/package.json`。
- **Pi-Agent 侧车开发**：位于 `pi-main/pi_agent_sidecar.mjs`，请保持原生 ES Module 零外部依赖设计。

### 第三步：提交前自检并推送到远端

**在执行 `git add` 前，请务必查看变动文件：**

```bash
# 1. 检查本次修改了哪些文件，确保没有误加临时文件或大文件
git status

# 2. 仅添加你需要提交的代码文件（不要无脑 git add .）
git add backend/app/xxx.py frontend/src/xxx.vue

# 3. 提交说明请遵循统一规范 (feat:, fix:, docs:, refactor:)
git commit -m "feat: 完善 .xlsx 复合表头跨行跨列解析逻辑"

# 4. 推送到远端自己的分支
git push origin feature/upload-excel-zhangsan
```

### 第四步：在 GitHub 网页上发起 Pull Request (PR)

1. 打开 GitHub 仓库页面，点击黄色提示条的 **Compare & pull request** 按钮；
2. 填写清晰的修改描述（解决了什么问题，改动了哪些模块）；
3. 等待 CI 自动化流水线（Lint、测试、构建）全部通过；
4. 邀请 Reviewer 审查代码，通过后由负责人使用 **Squash and merge** 压缩合并入主干。

---

## 🧪 本地测试验证命令清单

提交代码前请在本地执行完整测试以确保无回归故障：

```bash
# 1. 运行核心算法与大纲生成单元测试
cd backend
python -m unittest test_core.py test_dynamic_outline.py test_xlsx_and_custom_school.py

# 2. 运行 Pi-Agent 跨语言 IPC 桥接测试
python test_pi_bridge.py

# 3. 运行端到端 5 阶段流水线测试
python test_e2e_pipeline.py

# 4. 前端类型检查与生产构建测试
cd ../frontend
npm run build
```
