# Phase 18A Productization Report

## 完成范围

本阶段建立了 Windows 本地 Streamlit 研究工作区，把 Phase0–17 的数据资产、Evidence Registry、冻结 Decision 输出、Phase15 Acquisition Engine、Phase16 Generation Registry、Calculation Job Registry、工具能力门控和实验反馈入口接入一个界面。

没有训练新模型，没有修改 Model v0–v4-alpha，没有执行 Phase17.1，没有生成新的 docking、MM/GBSA 或实验数值。

## 真实接入结果

| 资产 | UI接入规模 | 说明 |
|---|---:|---|
| HTVS候选 | 1633 | 全部具有冻结 Vina 结果 |
| Phase16生成结构 | 360 | 其中120个具有冻结 Vina 结果 |
| 内部候选 | 17 | 身份映射遵循Phase14.1；仅Hit13 exact canonical match |
| Candidate master | 2010 | 三类身份记录不猜测合并 |
| Phase15 acquisition panel | 60 | 可与多种冻结策略比较 |
| Generated acquisition panel | 30 | 只读展示 |
| 经审查实验反馈 | 0 | 明确 empty / not_available |

## 实现能力

- 13个工作页面；
- Candidate/证据/任务/工具查询；
- Glide/Vina协议分歧可视化；
- 冻结的四目标 Decision profile 切换；
- 预算10/20/40/60/100的 Phase15 获取策略；
- 生成结构谱系与可用后端展示；
- 受限、基于 Registry 的研究对话；
- 带元数据的 CSV/Markdown 导出；
- 生成请求的预览、确认和版本化记录；
- 空实验反馈入口和表头预检查。

## 浏览器验收

8个核心页面已在真实本地应用中逐页打开、标题核验并确认无 Traceback/KeyError/Exception。截图位于 `results/phase18a/screenshots/`：

- `01_dashboard.png`
- `02_candidate_explorer.png`
- `03_evidence_matrix.png`
- `04_protocol_comparison.png`
- `05_decision_workspace.png`
- `06_acquisition_workspace.png`
- `07_execution_jobs.png`
- `08_research_dialogue.png`

## 科学边界

当前项目的数据审计属于数据语义一致性、target annotation、endpoint segregation 和 provenance QC，不属于 biosafety。项目不涉及临床研究，也不扩展出临床前或生物安全叙事。

## 限制

- 研究对话目前为确定性查询路由，不是自由聊天智能体；
- GUI不直接控制后台 supervisor 的暂停/恢复，避免造成虚假状态；
- 新分子扩展在本阶段只生成可确认请求，不覆盖冻结 Phase16；
- 没有真实实验反馈，因此无法评价生物命中率或成本节约；
- 高成本物理证据后端仍由 Phase17 科学能力门控阻塞。

