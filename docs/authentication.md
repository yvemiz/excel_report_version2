# 账号与个人工作空间

本地实现日期：2026-10-16。

## 使用方式

打开网页后，先在“注册账号”创建用户名和密码。姓名或称呼选填，用户名使用3至32位字母、数字或下划线，大小写视为同一账号，注册密码为12至128个字符。注册成功后自动登录；后续直接登录即可。右上角账号菜单提供“退出登录”。

登录状态最长保留7天，可跨后端重启。退出后该会话立即失效。多个标签页会同步账号变更；切换账号时重新加载对应工作空间，不沿用前一账号的页面数据。

每个账号从独立空空间开始。旧版 `backend/data/cell_lake.db`、`metrics.duckdb`、`uploads`、`exports` 等文件保留原状，不自动迁移到首个注册账号。如果需要使用旧表格，可先复制所需原始 Excel 到独立报表文件夹，再登录后上传或导入。

## 保存位置

```text
backend/data/
  accounts.db                   # 账号、密码摘要、会话摘要、加密后的模型配置
  auth.key                      # 本机模型密钥加密所需的密钥文件
  users/<账号ID>/
    cell_lake.db                # 当前账号的单元格与物理坐标
    metrics.duckdb              # 当前账号的结构化工作表
    uploads/                    # 当前账号上传的原始 Excel
    exports/                    # 当前账号的 Word 与 Excel 成果
    charts/                     # 当前账号的图表
    telemetry_traces.jsonl      # 当前账号的生成耗时、Token 估算与章节统计
    checkpoints/
      pipeline_checkpoint.json  # 最近一次报告的已完成小节、核验结果和导出位置
```

这些私有运行文件已纳入 Git 忽略规则。备份时需同时保留 `accounts.db`、`auth.key` 和 `users` 目录；缺少 `auth.key` 将无法解密已保存的 API Key。

API Key、模型名称、接口地址和执行引擎按账号保存。读取设置时只返回“是否已配置密钥”，不返回密钥原文。密钥输入框留空会保留原值；要改用本地规则，勾选“停用并清除已保存的 API Key”并保存。

## 接口与隔离

`POST /api/auth/register` 注册，`POST /api/auth/login` 登录，`GET /api/auth/me` 读取当前账号，`POST /api/auth/logout` 退出。其余数据、生成、下载、图表及 WebSocket 接口都要求登录。账号由后端会话确定，请求参数不能指定其他账号的工作空间。

密码使用随机盐和 PBKDF2-HMAC-SHA256 600,000次迭代摘要；会话 Cookie 设置 HttpOnly、SameSite=Lax，HTTPS 请求下设置 Secure，数据库只存会话令牌摘要。注册和登录有频率限制。写入接口、启动生成和 WebSocket 会检查浏览器来源。模型密钥使用 Fernet 加密保存，不写入前端本地存储。

下载与图表接口只在当前账号目录查找，响应禁止缓存；目录导入拒绝读取系统数据目录和其他账号的数据。上传文件名和下载路径也进行边界检查。

## 与远程流水线和 Docker 的兼容

合并后保留远程功能分支的并发章节生成、Pi-Agent 侧车、工作簿检查和 Word 原生目录。`/api/pipeline/balance` 使用当前账号的模型密钥，`/api/pipeline/telemetry` 只汇总当前账号的运行统计。

`/api/pipeline/stream?resume=true` 可手动请求从当前账号的检查点恢复已通过核验的小节；学校名称或入库数据变化后不复用旧章节。前端重新生成仍按完整新任务执行，刷新页面只读取状态。

Docker 健康检查使用无需登录、只返回服务存活状态的 `/healthz`。`/api/health` 继续要求登录并返回当前账号的数据规模。通过 `APP_ALLOWED_ORIGINS` 配置浏览器实际访问地址，多个地址以英文逗号分隔；本地 Docker 默认允许 `http://localhost:8080` 和 `http://127.0.0.1:8080`，部署到域名时应改成对应的完整地址。

2026-10-17 合并验证：账号与合并兼容检查11项、原有数据解析/并发/插件检查15项通过；Pi-Agent撰写与大纲桥接检查、8张示例表共2,221个单元格的完整报告生成、前端类型检查和生产构建通过。生成检查使用独立临时数据库及导出目录，未调用真实模型生成接口。

参考：[OWASP 密码存储建议](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[OWASP 会话管理建议](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)。

## 检查记录

在独立临时数据库中运行：

```powershell
# backend 目录
& 'D:\miniconda3\python.exe' -m unittest discover -s tests -p test_auth_workspaces.py -v
```

5组接口检查通过：账号注册与密码摘要、会话撤销、匿名与非法来源访问、两个账号间的数据与文件隔离、目录与路径限制、重启后的配置及报告恢复、登录频率限制。

前端类型检查及生产构建通过。临时浏览器环境用两个账号验证了注册、密码确认、登录、实际 Excel 上传、模型配置持久化、刷新保持登录、退出与再次登录，以及本地规则报告生成和导出。第二账号不能取得第一账号的表格、报告、配置或文件；六个业务页面在1440、1024、390像素宽度下无页面横向溢出。未使用真实账号、真实 API Key 或原有数据库进行写入检查。
