# Phase 9 Literature and Architecture Report

日期：2026-08-26

## 1. 检索目标

本次检索不是寻找可直接复制的“万能药物智能体”，而是确认科学智能体、分子主动学习、多参数决策与研究者在环方法中哪些设计适用于 ATP-Navigator 的真实约束：17 个内部候选、计算标签、缺少生物活性实验、已有多版本模型和有限实验预算。

## 2. 文献到架构的映射

| 方法来源 | 可吸收原则 | ATP-Navigator实现 | 未采用内容与原因 |
|---|---|---|---|
| Coscientist | 规划器调用检索、代码和实验工具；过程可解释 | Agent只调用冻结模型、证据表、稳健排序和实验规划工具 | 不连接实验机器人；当前没有自动化实验接口 |
| ChemCrow | LLM由专业化学工具约束，不直接替代计算器 | 化学分数来自现有模型/RDKit/计算数据；自由文本仅解释意图 | 不让LLM生成Docking、活性或毒性数值 |
| Segall等多参数敏感性 | 检查权重变化是否扭曲候选推进决策 | 受约束权重抽样、rank acceptability、Pareto和反事实解释 | 不把单套人工权重包装成客观真值 |
| MolPAL | 预算约束下平衡高分候选与探索 | Phase 8队列与Phase 9实验面板兼顾优先级、分歧和结构多样性 | 当前不进行新模型迭代，等待真实返回值 |
| Human-in-the-loop AL | 研究者反馈纠正模型目标与domain shift | 研究意图profile需确认；实验反馈后才允许更新 | 没有实验反馈前不声称闭环已完成 |
| ChemScreener | uncertainty与chemical diversity共同驱动批次选择 | 下一实验面板使用排名区间、模型分歧、scaffold稀有度 | 该论文是WDR5案例，不能当作本项目ATP验证结果 |

## 3. 选定架构

```text
Research intent
      ↓  human confirmation
Intent profile / weight distribution
      ↓
Frozen evidence tools ── Model v3/v4 disagreement
      │                  Docking/MMGBSA/ADMET/external priors
      ↓
Robust multi-objective ranking
      ├─ rank acceptability
      ├─ Pareto front
      └─ counterfactual explanation
      ↓
Budget-aware experiment panel
      ↓
Evidence ledger + agent trace + unknown experiment fields
```

Agent不是新的监督模型，没有改写Model v0-v4-alpha，也没有产生新活性标签。

## 4. 先进性判断

对于当前小样本，先进性主要来自问题建模和不确定性管理，而非神经网络复杂度。强行训练GNN/Transformer会增加参数量和竞赛叙事复杂度，却没有足够同靶点实验标签支持泛化。Phase 9把“哪个候选值得先做实验”建模为研究意图条件化、证据受限、预算约束的序贯决策问题，更符合项目实际。

## 5. 可验证假设

ATP-Navigator当前不宣称提高真实命中率。它提出的前瞻假设是：在同等候选测试预算下，稳健多目标Agent策略相较Docking-only和历史人工选择，能够减少无效测试并更快获得满足预注册ATP synthase/MIC标准的候选。只有冻结面板的真实实验完成后才能检验该假设。

## 6. 文献登记状态

六篇主要方法论文已写入`data/literature/references.csv`，全部标记为架构依据、非训练数据。未下载或提交未授权论文全文。

