# ATP-Navigator Phase 18B 用户指南

## 定位

ATP-Navigator 是 ATP 合酶虚拟筛选后的 AI 辅助候选优先级决策系统。界面用于查看和整合已经登记的结构、Docking、MM/GBSA、分子性质、外部知识和模型输出；它不生成实验结果，也不把计算排序解释为真实活性。

## 启动

在 Windows PowerShell 中进入仓库根目录：

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

浏览器访问 `http://127.0.0.1:8501`。这是本机界面，不要求把候选或研究数据上传到第三方服务。

## 页面

1. **AI Research Console**：自然语言查询、结构化意图、Plan Preview、人工确认、白名单执行和结果回到会话的统一入口。
2. **Dashboard**：实时显示 1633 个 HTVS 候选、360 个 Phase16 生成结构、Vina 证据、获取面板、活动任务和工具能力。
2. **Project Overview**：从 git 历史读取可核查的开发时间线。
3. **Candidate Explorer**：统一查询 HTVS、内部 17 候选和生成结构。内部候选与 HTVS 的身份映射只使用 Phase14.1 审计，不能按名称或排名猜测。
4. **Evidence Matrix**：显示 available、missing、unknown 和 not_applicable；缺失值不按 0 处理。
5. **Protocol Comparison**：查看 Glide/Vina 相关性、Top-k 重叠和排名差异。协议一致性不是活性。
6. **Decision Workspace**：读取冻结的 Phase10 profile 输出。切换模式不会重训模型或修改评分公式。
7. **Acquisition Workspace**：复用 Phase15 策略回答“预算有限时下一份高成本证据算谁”。VOI 是启发式，不是活性或真实经济价值。
8. **Molecule Generation**：查看 Phase16 已生成结构和谱系。新任务只保存带确认的版本化请求，不覆盖 Phase16。
9. **Execution Jobs**：读取共享 SQLite Calculation Job Registry。终态任务默认只读，不自动重启。
10. **Tool Capability**：显示真实能力、版本和阻塞原因；不可用后端不会产生模拟数值。
11. **Research Dialogue**：以可追溯规则查询候选证据、预算、协议分歧、证据缺口和工具能力。
12. **3D Structural Workspace**：显示登记的7P3W受体和协议特异性pose；无pose时保持missing。
13. **Team Review Board**：分开保存AI建议、团队意见和最终研究者决定。
14. **Activity Timeline**：汇总会话、计划、任务、证据和协作事件。
15. **DBTL Loop**：展示计算Design–Build–Test–Learn状态，不宣称湿实验闭环。
16. **Presentation Mode**：面向比赛现场的真实注册数据演示路径。
17. **Experiment Feedback**：展示空状态并预览反馈表头。正式导入仍需要证据文件 hash 和人工审查，不自动训练。
18. **Export**：导出当前表格，同时附加 commit、模型范围、时间与科学协议范围元数据。

## 推荐演示流程

AI Research Console（协议分歧查询 → “从这里”获取计划 → 确认）→ 3D Structural Workspace → Team Review Board → Activity Timeline → Presentation Mode。

## 当前限制

- 尚无经审核的 ATP 抑制、MIC 或毒性反馈，前瞻评价为 `not_available`；
- Prime/MMGBSA 当前许可证不可用；Windows OpenMM 依赖链尚不足以产生可接受的 protein–ligand MM/GBSA 证据；
- Phase18B 不停止、重启或修改独立运行的 WSL Phase17.1；
- Research Console 是受限、可追溯的执行编排层，不是能自由生成科学数值的大模型；
- AI推荐、团队投票和最终人类决定严格分开，投票不修改模型分数。
