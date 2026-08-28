# ATP-Navigator Phase 18A GUI Architecture

## 设计原则

Phase18A 在已有架构之上增加本地显示和交互层，不建立第二套科学数据，不复制决策公式，不修改模型。

```text
Streamlit UI (app.py)
        │
        ├── ProjectData adapter ── frozen CSV/JSON artifacts
        │                       ├─ workspace.sqlite3 / Job Registry
        │                       ├─ Evidence Registry
        │                       ├─ FeedbackStore
        │                       └─ git history
        │
        ├── Frozen Decision outputs (Phase10)
        ├── AcquisitionEngine (Phase15 exact strategy ordering)
        ├── GeneratedCandidateRegistry (Phase16)
        ├── capability gates (Phase12/15/16/17)
        └── deterministic ResearchQueryRouter
```

## 关键约束

- `src/app/data_adapter.py` 是只读适配器；不调用模型训练，不生成 docking/MMGBSA 数值。
- Decision Workspace 读取 `results/phase10_workflow/profile_comparison.csv` 和冻结决策分量。
- Acquisition Workspace 直接调用现有 `AcquisitionEngine.build_features()` 与 `_strategy_orders()`，没有在 GUI 中复制策略公式。
- 任务页读取 `workspace_local/workspace.sqlite3` 的 `calculation_job`；没有新的任务状态表。
- 实验反馈继续使用 `FeedbackStore`，上传预览不等于正式导入。
- 所有导出由 `export_service.py` 添加 commit、时间、模型范围和协议范围元数据。
- 缓存仅用于界面读取（TTL 120秒），不缓存或改变科学计算结果。

## 数据规模与性能

- Candidate master：2010 个身份记录（1633 HTVS + 360 generated + 17 internal）；
- Evidence matrix：2010 行；
- 分页默认 40–50 行；
- 图表使用冻结的 1633 matched subset，规模无需采样；
- Evidence provenance 按候选惰性筛选；
- 高成本 acquisition feature 仅在打开页面时计算。

## 安全的写入边界

Phase18A 只有两类受控交互写入：

1. 生成任务请求保存到 `workspace_local/phase18a/requests/`，写入前显示完整预览并要求确认；它不执行计算；
2. 浏览器下载导出，不修改 Registry。

不可用后端的运行按钮保持禁用；终态计算任务不会被自动重试。

