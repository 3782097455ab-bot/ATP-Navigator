# ATP-Navigator Phase 6A Robustness Report

生成模块：`ATP-Navigator_Phase6A_Robustness_v1.0`

分析范围：Phase 5已有17个内部候选和四个计算决策分量。没有训练监督模型，没有修改Model v0-v3，没有加入实验标签。

## 1. 权重敏感性

共比较Phase 5默认权重和A-D四个预设场景。分数仍是当前17候选批次内的决策分数，不是活性或成功概率。

| 场景 | Top 1 compound | 历史别名 | 场景分数 |
|---|---|---|---:|
| default | ATP-SMI-C93E6EC67CDB | Hit2 | 73.9071 |
| A | ATP-SMI-C93E6EC67CDB | Hit2 | 77.1100 |
| B | ATP-SMI-5B36D3E11A3B | Hit13 | 65.5475 |
| C | ATP-SMI-C93E6EC67CDB | Hit2 | 73.9858 |
| D | ATP-SMI-C93E6EC67CDB | Hit2 | 74.0946 |

不同场景两两比较的最低Spearman为0.4583，最低Kendall tau为0.3235。完整矩阵见`results/phase6A/ranking_stability_matrix.csv`。

## 2. Top候选一致性

- 在A-D四个扰动场景中始终进入Top 3的候选数：1；候选：ATP-SMI-9DA3213A09E8 (Hit1)；
- 在A-D四个扰动场景中始终进入Top 5的候选数：1；候选：ATP-SMI-9DA3213A09E8 (Hit1)；
- 每个候选的Top 3/Top 5出现次数、平均排名和排名范围见`top_candidate_consistency.csv`。

## 3. Decision Engine消融

“Binding + ATP”保留默认二者相对比例并归一化为0.642857/0.357143；完整方案使用45/25/15/15。

| 消融 | Top 1 compound | Top rank | Spearman vs full | Kendall vs full |
|---|---|---:|---:|---:|
| A_binding_only | ATP-SMI-C93E6EC67CDB | 1 | 0.6205 | 0.4502 |
| B_binding_plus_ATP | ATP-SMI-9DA3213A09E8 | 1 | 0.8971 | 0.7353 |
| C_full_ATP_Navigator | ATP-SMI-C93E6EC67CDB | 1 | 1.0000 | 1.0000 |

消融结果用于观察多目标分量对候选顺序的影响，不代表任何方案具有更高实验准确率。

## 4. External benchmark

当前可评价benchmark数量：0。Dataset v1.0外部Layer 1/2与17候选没有精确canonical SMILES重叠，因此未计算外部性能指标。详见`results/phase6A/benchmark_report.md`。

## 5. 产物与可复现性

- `results/phase6A/weight_sensitivity_results.csv`
- `results/phase6A/ranking_matrix.csv`
- `results/phase6A/ranking_stability_matrix.csv`
- `results/phase6A/top_candidate_consistency.csv`
- `results/phase6A/decision_ablation.csv`
- `results/phase6A/benchmark_results.csv`
- `results/phase6A/benchmark_report.md`

输入文件SHA-256：

- `results/final_candidate_ranking.csv`: `8e9fdff47d305d12bf2a96ce6baa5c786b1a5a63a8efebdcb03e03e963ae29dc`
- `scoring_config.json`: `bf5a3773123025da8b1271a113342884eaa9acf1e0a49c0828bbcf14a84e3056`
- `data/dataset_v1.0/ATP_Navigator_Dataset_v1.csv`: `88df875d4c9bd65bbb5bf16c6608d57c5947b5fbb8ec58cc053bb8c9b9724bb0`
