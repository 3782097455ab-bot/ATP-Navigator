# ATP-Navigator Model v4-alpha Report

版本：`ATP-Navigator_Model_v4-alpha`  
阶段：Phase 7 — External Knowledge Enhanced Training Experiment  
日期：2026-08-24

## 1. 实验目标与结论

本轮是第一次Dataset v2.0外部知识增强实验，不是最终模型。Model v0-v3、Phase 5 `results/final_candidate_ranking.csv`和`scoring_config.json`均未覆盖。

本次实验未同时满足Spearman提高与RMSE下降，因此不能宣称外部知识已经带来明确提升。

内部比较仍以17个候选的静态MM/GBSA计算标签为基准，不是MIC、IC50或真实生物活性提升证明。

## 2. Dataset v2.0接入审计

- 输入：8,820行，4,338个RDKit canonical structures，SMILES解析失败0；
- Task A：6,663行；Task B：77行；Benchmark：2,080行；
- activity值：exact 8,573，censored 239，range 8；
- 43个canonical structure跨task出现，所有划分按scaffold/canonical identity隔离；
- 2,080条Benchmark记录没有进入Task A/B训练，也没有进入内部MM/GBSA标签；
- `Dataset_QC_Report_external_source.md`审计的是早期6,777行主库；本pipeline对当前8,820行标准输入另行生成`dataset_audit.json`；
- source level与reference为用户提供的来源标注，本轮没有逐条重新打开论文或数据库验证。

## 3. 三任务隔离

### Task A — Antibacterial activity modeling

- 标签：精确、正值、MIC、μg/mL；回归目标为`log10(MIC μg/mL)`，lower-is-better；
- 截尾值、范围值、ETC inhibition和非MIC行不转数值；
- 同结构×organism species重复测量取中位数，保留测量数、范围、来源等级与reference数量；
- 特征：Morgan1024 + RDKit16 + organism species one-hot；source level和confidence仅作样本权重，不作分子特征；
- 训练规模：3,396个结构-物种样本，2,263个结构，832个scaffold；
- 评价：5-fold scaffold GroupKFold；正式报告切片为A/B且confidence=high；
- classification accuracy：不适用。当前没有预注册active/inactive阈值，未事后创造分类标签。

| slice | n | rmse | spearman | classification_status |
|---|---|---|---|---|
| all_eligible | 3396 | 0.8024 | 0.7457 | not_applicable_no_pre_registered_active_threshold |
| formal_A_B_high | 3395 | 0.8015 | 0.7464 | not_applicable_no_pre_registered_active_threshold |
| source_A | 82 | 0.5154 | 0.0149 | not_applicable_no_pre_registered_active_threshold |
| source_B | 3313 | 0.8073 | 0.7370 | not_applicable_no_pre_registered_active_threshold |

### Task B — ATP synthase target modeling

- 不把IC50、Activity%、Inhibition%或不同单位混成同一回归目标；
- 按`activity_type + organism species + unit`分别训练；每个stratum至少8个结构、3个scaffold；
- 标签为各stratum内`log10(activity_value)`，仅A/B实验来源；
- source weights：A=1.0、B=0.8；confidence high=1.0、medium=0.7；
- 当前训练strata：4；其余strata保留`insufficient_small_data`状态。

| stratum_id | samples | scaffolds | spearman | rmse | ndcg_at_5 | top_k_enrichment | hit_recovery |
|---|---|---|---|---|---|---|---|
| ic50__mycobacterium_tuberculosis__nm | 17 | 7 | 0.6170 | 0.7053 | 0.7965 | 2.0400 | 0.6000 |
| ic50_atp_synthesis_inhibition__acinetobacter_baumannii__ng_ml | 10 | 3 | -0.3283 | 0.2179 | 0.4973 | 0.8000 | 0.4000 |
| ic50_atp_synthesis_inhibition__pseudomonas_aeruginosa__g_ml | 25 | 18 | 0.7037 | 0.5043 | 0.8564 | 3.0000 | 0.6000 |
| ic50_atp_synthesis_inverted_membrane_vesicles__pseudomonas_aeruginosa__g_ml | 8 | 7 | 0.0838 | 0.4777 | 0.7621 | 1.2800 | 0.8000 |

Task B各stratum指标不可跨单位解释为一个统一IC50性能；Task C只对每个模型在内部17候选上的预测做rank percentile，再等权形成ATP知识ensemble。

### Task C — Candidate ranking

- 基础：保留Model v3全部1,128个特征；
- 新增：6个Dataset v2.0 Task A/B预测特征；总特征1134；
- 标签：内部17候选静态MM/GBSA，lower-is-better；Task A MIC和Task B IC50从未成为Task C标签；
- 评价：Leave-One-Scaffold-Group-Out，17个候选、11个scaffold。

## 4. Model v3 vs Model v4-alpha

| model_id | feature_count | spearman | rmse | ndcg_at_5 | top_k_enrichment | hit_recovery |
|---|---|---|---|---|---|---|
| Model v3 | 1128 | 0.7696 | 4.8877 | 0.7782 | 1.3600 | 0.4000 |
| Model v4-alpha | 1134 | 0.7549 | 4.9268 | 0.7774 | 1.3600 | 0.4000 |

性能差值必须结合n=17解释。即使某一指标提高，也不能证明真实活性命中率提高；Top-k指标单个候选即可显著改变。

## 5. Decision Engine实验接入

原Phase 5结果未覆盖。`decision_engine_candidate_ranking.csv`是shadow experiment：

- 仍用45/25/15/15总权重；
- Binding中将Model v3 percentile替换为Model v4-alpha percentile，Docking和静态MM/GBSA子权重不变；
- ATP Target = 30%直接ATP结构相似性 + 70% Task B分层ensemble；
- Antibacterial = Task A对A. baumannii预测的批次内percentile；
- Drug-likeness保留Phase 5结果；实验MIC和ATP enzyme仍标记`unknown`。

相对原Phase 5：Spearman 0.7721，Kendall 0.6029，Top3重叠2/3，Top5重叠4/5。这是排名变化，不是实验准确率。

| final_rank_v4_alpha | historical_alias | compound_id | final_score_v4_alpha | decision_status |
|---|---|---|---|---|
| 1 | Hit2 | ATP-SMI-C93E6EC67CDB | 78.8290 | experimental_shadow_not_replacing_phase5 |
| 2 | Hit1 | ATP-SMI-9DA3213A09E8 | 69.5512 | experimental_shadow_not_replacing_phase5 |
| 3 | Hit5 | ATP-SMI-96FD6257D8BA | 65.5434 | experimental_shadow_not_replacing_phase5 |
| 4 | Hit4 | ATP-SMI-5D3E7B6B6796 | 63.3364 | experimental_shadow_not_replacing_phase5 |
| 5 | Hit3 | ATP-SMI-874C2DE25FE4 | 63.1150 | experimental_shadow_not_replacing_phase5 |

## 6. Small-data limitation

- 内部Task C只有17个候选/11个scaffold，无独立前瞻测试集；
- Task B各同质stratum仅8–25个样本、3–18个scaffold，相关性方差很大；
- Dataset v2.0与既有Model v2知识来源存在内容重叠，本轮是增量工程实验，不是独立外部验证；
- Task A/B模型预测是计算先验，不是内部候选的MIC或ATP enzyme实验；
- 2,080条BindingDB benchmark严格未用于本轮训练，后续只能在冻结协议和训练去重后作验证/校准；
- source quality等级由提供文件给出，本轮未逐条回源核实；
- 未处理截尾MIC的删失回归；本轮直接排除，可能产生选择偏差。

## 7. 下一轮最缺数据

1. 更多同一ATP synthase亚型、同一assay、同一unit的A等级IC50，尤其A. baumannii且scaffold更分散；
2. 内部17候选的ATP synthase功能/酶抑制、MIC/MBC、实验毒性和重复测量；
3. 独立于Dataset v2.0和Model v2来源的冻结测试集；
4. 对截尾MIC可使用的检测上下限与原始实验条件，用于删失回归；
5. target protein ID、assay protocol、strain、pH/培养条件等可结构化条件字段；
6. 更多内部中等/负候选的同协议静态MM/GBSA，降低仅Top17的选择偏差。

## 8. 复现产物

- `src/model_v4_alpha_pipeline.py`
- `data/dataset_v2.0/ATP_Navigator_external_dataset_v1.csv`
- `models/model_v4_alpha/`
- `results/model_v4_alpha/`
- `docs/Model_v4_alpha_Report.md`

本报告只描述本次实际运行结果，不将Model v4-alpha登记为最终模型。
