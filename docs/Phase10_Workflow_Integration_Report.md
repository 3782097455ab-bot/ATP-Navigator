# Phase 10 Workflow Integration Report

日期：2026-08-26  
版本：`ATP-Navigator_Phase10_IntegratedWorkflow_v1.0`

## 1. 目标

把现有数据资产、Model v0-v4-alpha、Phase 5 Decision Engine和Phase 9 Agent能力串成可一次运行的“虚拟筛选结果到实验候选选择”流程。本阶段不训练模型，评价对象是工作流完整性、证据覆盖、可追溯性和确定性，不是生物活性性能。

## 2. 集成结构

```text
Standard candidate CSV
  ↓
Input processor
  ├─ schema/SMILES/duplicate QC
  ├─ Morgan1024 + RDKit descriptors
  ├─ ATP reference similarity
  └─ missing evidence ledger
  ↓
Frozen model tools
  ├─ Model v3 if 1128-feature contract is complete
  ├─ Model v2-A transparent structure-only fallback
  └─ preserved ATP/antibacterial external-prior models
  ↓
Four-component Decision Engine
  ├─ Binding
  ├─ ATP relevance
  ├─ Antibacterial prior
  └─ Drug-likeness / predicted risk
  ↓
Research profile + weight robustness
  ↓
Ranking + explanation + workflow self-audit
```

## 3. 研究模式

- `binding_focused`：Binding 60%；
- `atp_mechanism_focused`：ATP relevance 50%；
- `experimental_validation_focused`：Drug-likeness/预测风险 35%；
- `balanced`：兼容Phase 9的默认综合模式。

全部权重、边界、抽样数和风险阈值保存在`configs/research_profiles.json`。

## 4. 自评体系

Agent不使用缺失的实验标签自我声称准确率。Phase 10自评以下可证实项目：

1. 输入结构有效覆盖；
2. 冻结模型工具覆盖；
3. Model v3完整特征覆盖与降级状态；
4. 四分量完整决策覆盖；
5. 排名唯一与完整性；
6. 实验unknown完整性；
7. 分数非概率语义完整性；
8. 来源和版本追溯；
9. Model文件运行前后hash一致；
10. 相同输入/profile确定性复跑一致。

同时自动比较全部研究模式，输出profile间Spearman/Kendall稳定性及Top3/Top5跨模式出现次数。该分析衡量决策对研发目标的敏感性，不是生物学性能。

这些指标证明系统是否可运行和可信，不证明候选是否真实有效。真实ATP抑制、MIC和毒性返回后，才能增加命中率、EF@k、NDCG@k、cost-to-first-hit等前瞻性能评价。

## 5. 运行入口

完整演示：

```powershell
.venv\Scripts\python.exe examples\run_navigation_demo.py
```

自定义候选：

```powershell
.venv\Scripts\python.exe src\navigator_pipeline.py --input candidates.csv --profile atp_mechanism_focused
```

主要输出：

- `results/processed_candidate_table.csv`；
- `results/final_navigation_report.csv`；
- `docs/Candidate_Recommendation_Report.md`；
- `results/phase10_workflow/workflow_validation.csv`；
- `results/phase10_workflow/pipeline_trace.json`；
- `results/phase10_workflow/profile_comparison.csv`、`profile_rank_stability.csv`；
- `results/demo/`比赛演示包。

## 6. 不变性

- Model v0-v4-alpha不修改；
- 无模型训练；
- 无新监督标签；
- 不将Decision score回流为训练标签；
- 无ATP、MIC或毒性结果填充；
- 不宣称发现有效药物或预测实验成功概率。
