# 2026-10-19 用户体验走查归档

## 测试信息

- **测试人**：LHRCarrier
- **测试时间**：2026-10-19 20:08–20:30（Asia/Shanghai）
- **分支**：`feature/Frontend-makeover`
- **提交**：`26cbfd3 refactor: make model output guard provider agnostic`
- **环境**：前端 `http://localhost:5173`，后端 `http://127.0.0.1:8008`，OpenCode Go 本地代理 `http://127.0.0.1:8011`
- **模型配置**：`deepseek-v4.1-flash`，Python 原生执行
- **现有数据**：8 个 Excel 文件、8 个工作表、2,221 个数据单元格
- **现有报告**：6 个小节、12,450 字符，生成于 2026-10-18 21:04

## 走查范围

按实际使用者路径走查：工作台 → 数据管理 → 报告生成 → 报告阅读 → 服务设置 → Word/对账表导出。

为避免额外模型费用，本次没有重新触发完整的 5 分钟生成，而是复用现有报告；生成相关结论来自现有状态、页面交互和导出文件核查。

## 结论

核心流程可以走通，没有出现阻断登录或阻断阅读的错误。但目前有 **4 个 P0、11 个 P1、8 个 P2** 体验问题，主要集中在校验结论的可信度、Word 导出质量、长任务控制、引用核验效率和数据可检查性。

最需要优先处理的是：**页面一边显示“生成完成 100%”，一边保留“大纲需要关注 82 分 / 2.1 核验异常”，并且仍然允许直接下载交付。** 此外，账号内数据没有项目/学校隔离，存在混表和同名模板覆盖风险。

## 归档文件

- `2026-10-19_用户体验问题清单.md`：完整问题清单、证据与修复优先级
- `screenshots/`：7 张走查截图

## 截图

- [01 工作台 100% 与核验异常并存](screenshots/01-overview.png)
- [02 生成页大纲需关注](screenshots/02-generation-quality-contradiction.png)
- [03 生成页 100% 完成状态](screenshots/03-generation-100-percent.png)
- [04 服务设置](screenshots/04-settings.png)
- [05 报告图表可读性](screenshots/05-reader-chart.png)
- [06 阅读页目录](screenshots/06-reader-toc.png)
- [07 引用抽屉跨路由残留](screenshots/07-citation-drawer-persists.png)

## 导出证据

- `backend/data/users/1/exports/高校发展检验与质量评估报告_海南师范大学.docx`
- `backend/data/users/1/exports/数据穿透审计与指标覆盖清单_海南师范大学.xlsx`

