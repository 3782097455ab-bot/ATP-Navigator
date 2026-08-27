# Phase 15 Budget-aware Evidence Acquisition Report

日期：2026-08-28  
状态：完成；未训练模型；未改变Model v0–v4-alpha、Decision Engine、历史Glide/MMGBSA或`vina_7p3w_v1`

## 1. 科学问题与边界

Phase 15回答：当Glide与Vina排序不一致、候选级MM/GBSA尚未覆盖且计算预算有限时，下一份高成本计算证据应优先获取在哪些候选上。

本阶段的consensus只表示计算协议一致性；uncertainty只表示现有证据下的可追溯不确定性；VOI proxy只是一种证据获取启发式。三者均不等于生物活性、实验命中率或真实经济价值。

## 2. 输入与可追溯性

- 1633个HTVS候选的结构、Bemis–Murcko scaffold、Morgan/Butina cluster；
- 1633个冻结Vina rank与1633个历史Glide rank；
- QuickProp完整性与Glide ligand efficiency；
- Phase 14.1身份审计和Phase 8既有数据获取计划，仅用于解释性分层；
- 候选级同协议MM/GBSA仍缺失；不存在新的MIC、ATP酶、毒性或实验标签。

所有输入SHA-256、配置hash和输出语义记录在`results/phase15/phase15_summary.json`。

## 3. Protocol robustness

- Glide/Vina matched=1633；Phase 14相关性：Spearman=0.1687，Kendall=0.1127；
- mean normalized rank disagreement=0.2975，median=0.2567；
- disagreement≥0.8的候选42个，≤0.2的候选668个；
- `rank_consensus`、`normalized_rank_variance`、`rank_entropy`和`protocol_disagreement_score`逐候选保存；
- protocol consensus不被解释为activity。

## 4. 五类不确定性

| 分量 | 计算来源 | 当前状态 |
|---|---|---|
| protocol uncertainty | Glide/Vina normalized rank delta | 1633/1633可计算 |
| model uncertainty | 可比较的全库候选级模型输出 | 当前不可用，显式NaN，不填0 |
| objective uncertainty | consensus binding、ligand efficiency和size-tractability代理的离散度 | 1633/1633可计算；不是药效概率 |
| evidence uncertainty | structure/preparation/Glide/QuickProp/Vina/pose QC/MMGBSA七组证据完整度 | 1633/1633可计算；候选级MM/GBSA均缺失 |
| chemical-space uncertainty | scaffold与cluster稀有度 | 1633/1633可计算 |

可用四分量的主导来源分布：chemical space 1337、protocol 202、objective 87、evidence 7。由于缺少可比较的全库模型输出，model uncertainty没有参与综合平均，且`uncertainty_available_components=4`被显式记录。

## 5. Acquisition策略

Baseline：random、Vina top、Glide top、consensus top。  
高级策略：disagreement-aware、diversity-aware、uncertainty-aware、rank-boundary、evidence-gap，以及配置化`ATP_Navigator_hybrid`。

Hybrid权重：exploitation 0.30、protocol disagreement 0.20、evidence uncertainty 0.15、scaffold diversity 0.15、cluster coverage 0.10、rank-boundary proximity 0.10；再除以显式calculation cost。权重保存在`configs/acquisition_phase15.json`。

## 6. 60候选高成本证据面板

| selection class | 数量 | 目的 |
|---|---:|---|
| multi-protocol strong | 15 | 两协议上部区域或最佳共识 |
| extreme disagreement | 15 | 让高成本证据解决协议冲突 |
| rank-boundary uncertain | 10 | 检查可能改变预算截断决策的候选 |
| scaffold diverse | 10 | 扩大结构空间覆盖 |
| medium controls | 5 | 中位区域、低分歧计算控制 |
| historical bridge / interpretable | 5 | 1个Hit13 exact bridge + 4个Phase 8可追溯既有计划候选 |

面板严格60个唯一candidate；历史可解释组中只有Hit13对应的`91074`是内部exact structure bridge，其余4个不得描述为内部Hit身份。

## 7. 预算模拟

以下列出Hybrid在各预算下的覆盖结果；完整十策略比较见`budget_simulation.csv`。

| budget | unique scaffolds | scaffold fraction | protocol bins | uncertainty coverage | boundary candidates | cost units |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 10 | 1.000 | 3 | 0.00993 | 1 | 100 |
| 20 | 20 | 1.000 | 4 | 0.01941 | 1 | 200 |
| 40 | 40 | 1.000 | 5 | 0.03634 | 2 | 400 |
| 60 | 60 | 1.000 | 5 | 0.05311 | 3 | 600 |
| 100 | 98 | 0.980 | 5 | 0.08641 | 5 | 1000 |

在budget=60时：Vina top覆盖36个scaffold，Glide top 47，consensus top 42，disagreement-aware 44，diversity-aware 59，Hybrid 60。Hybrid与Vina top/Glide top/consensus top的重叠分别为15/13/7，说明它不是简单复制任一评分前列，而是同时保留exploitation、冲突、边界和结构覆盖。

`evidence_gain_proxy`在当前库中主要随候选数增长，因为所有候选都缺同一类MM/GBSA证据；它不能用于声称Hybrid获得更高生物学收益。

## 8. VOI proxy

VOI proxy=min 7.80e-7、median 0.001370、mean 0.002003、max 0.009716。定义由potential decision change、可用uncertainty、evidence importance和estimated cost组成；原始分量全部保存在`voi_proxy.csv`。它只用于排计算先后，不是货币价值或活性概率。

## 9. Research Agent与GNINA

Research Workspace新增只读`acquisition_advice`，能从保存的Phase 15结果回答预算20、协议冲突、双协议强、协议主导不确定性、预算60降20等问题。LLM若启用只负责路由和解释，不能生成计算数值。

GNINA认证在30秒内结束：`unavailable / executable_not_found`，生成shadow score=0，不阻塞Phase 15。未下载、安装或模拟GNINA。

## 10. 输出

- `results/phase15/acquisition_panel_v1.csv`
- `results/phase15/acquisition_strategy_comparison.csv`
- `results/phase15/protocol_robustness.csv`
- `results/phase15/uncertainty_decomposition.csv`
- `results/phase15/voi_proxy.csv`
- `results/phase15/budget_simulation.csv`
- `results/phase15/gnina_shadow_status.json`
- `results/phase15/figures/`

## 11. 限制

- 没有真实实验标签，不能比较biological hit rate或expected activity gain；
- Glide与Vina不是等价协议，共识只反映计算一致性；
- 全库model uncertainty不可用，未用0伪填；
- 候选级MM/GBSA均缺失，因此evidence-gap维度区分度有限；
- calculation cost是相对单位，不是实测财务成本；
- 60候选是下一步证据获取面板，不是实验有效候选声明。

## 12. 验收

- 完整历史测试与Phase 15新增测试：141/141通过；
- 24个受保护模型文件逐文件SHA-256 mismatch=0；
- GNINA unavailable时数值输出=0；
- 未训练模型、未改Decision Engine、未进入Phase 16。
