# ATP-Navigator Decision Engine Report

版本：ATP-Navigator_Phase5_Decision_v1.0

状态：代码已运行并生成当前 17 候选的综合排序；没有训练或修改 Model v0–v3。

## 1. 目标与边界

Decision Engine 将已有计算证据转换为透明的多目标候选排序。`final_score` 是当前 17 候选批次内的相对决策分数，不是成功概率、活性概率或实验结论。

内部 MIC、ATP 酶抑制和实验毒性数据当前均不存在，输出中统一标记为 `unknown`，没有进行填补。

## 2. 最终公式

```text
final_score = 0.45 * binding_score + 0.25 * ATP_target_score + 0.15 * antibacterial_score + 0.15 * druglikeness_score
```

所有分量先转换为 0–100、higher-is-better 的批次内 rank percentile，然后再加权。原始 lower-is-better 字段在标准化时反向，因此最终公式不再使用隐藏的负号。

### Binding Score

```text
0.50 * model_v3_percentile + 0.20 * docking_percentile + 0.30 * static_mmgbsa_percentile
```

Model v3 prediction 与静态 MM/GBSA 高度相关，这三项是相关的计算证据，不是三个独立实验。权重是人工透明决策规则，不是从 17 个样本中优化得到。

### ATP Target Score

```text
0.30 * direct_ATP_similarity_percentile + 0.35 * PA_ATP_IC50_prior_percentile + 0.35 * Mtb_ATP_IC50_prior_percentile
```

AB ATP IC50 prior 保留在结果中供审计，但权重为 0，因为该外部子任务只有 10 个化合物、3 个 scaffold，且 Model v2 scaffold OOF Spearman 为负。PA 与 Mtb prior 也属于跨体系计算先验，不是内部候选 ATP 酶实验。

### Antibacterial Score

```text
AB_whole_cell_MIC_prior_percentile
```

该分量来自外部 AB whole-cell MIC 模型预测。它不证明 ATP 作用机制，也不是对当前候选完成的 MIC 测定。

### Drug-likeness Score

```text
0.50 * descriptor_rule_score + 0.50 * predicted_ADMET_safety_score
```

descriptor rule score 是 6 条公开阈值规则的通过比例；ADMET safety score 使用 27 个预测风险端点总和。二者都是启发式/预测证据，不是实验安全性。

## 3. 缺失数据策略

- 任一必需计算分量缺失：`final_score` 保持 unknown，不重新归一化剩余权重；
- 实验数据缺失：状态写为 `unknown`；
- 禁止以外部模型预测或零值填充实验 MIC、ATP enzyme 或 toxicity；
- confidence 最高 40% 权重来自实验验证。当前实验验证为 0，因此完整计算记录也只能达到 `medium_computational_only`。

## 4. 当前 Top 5

| Rank | Compound | Final | Binding | ATP target | Antibacterial | Drug-likeness | Confidence |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | ATP-SMI-C93E6EC67CDB | 73.91 | 90.00 | 25.16 | 93.75 | 87.04 | medium_computational_only |
| 2 | ATP-SMI-9DA3213A09E8 | 71.07 | 82.50 | 50.94 | 56.25 | 85.19 | medium_computational_only |
| 3 | ATP-SMI-5D3E7B6B6796 | 62.54 | 65.00 | 67.03 | 25.00 | 85.19 | medium_computational_only |
| 4 | ATP-SMI-96FD6257D8BA | 62.50 | 71.25 | 66.88 | 6.25 | 85.19 | medium_computational_only |
| 5 | ATP-SMI-E9798004BA11 | 59.95 | 63.75 | 65.47 | 18.75 | 80.56 | medium_computational_only |

该表是决策排序，不用于报告新的预测性能。Phase 5 没有新的监督标签，因此没有 Spearman/RMSE/NDCG 性能增量声明。

## 5. 输入追溯

| 输入 | 文件 | SHA-256 |
|---|---|---|
| `model_v3_prediction` | `results/model_v3/candidate_ranking.csv` | `25ab9436974928c4d66157662e0f79a302722f03a5cef4cb66f2f643b3ef120c` |
| `internal_candidates_and_binding` | `data/dataset_v0.2/samples.csv` | `fdef34d7984dafadd743b94f910bd2d4a529b553dfed892115775bd03baf31e3` |
| `external_knowledge_priors` | `results/model_v2/external_priors_internal.csv` | `62fac36bdfc4e58d0c6dcd1edf3f007deee98024f918328546a77d7794776195` |
| `chemical_similarity` | `data/model_v3/chemical_space_analysis.csv` | `f559592aceb4b2be10b27736e0ec3d7b747ad70678575bae622c04a00d2e7868` |
| `predicted_admet` | `data/admet_features_v0_2.csv` | `edc47010a604d99fcdd5584e43fb2a82f3170ffc83daeec8648252f1b2d348f0` |

完整公式、子权重、方向、阈值和缺失策略位于 `scoring_config.json`。

## 6. 软件调用接口准备

现有候选接口：

```json
{
  "compound_id": "ATP-SMI-C93E6EC67CDB",
  "score": 73.9071,
  "confidence": "medium_computational_only",
  "explanation": "binding=90.0; ATP-computational=25.2; antibacterial-prior=93.8; druglikeness-computational=87.0; experiments=unknown",
  "evidence_status": {
    "MIC_experiment": "unknown",
    "ATP_enzyme_experiment": "unknown",
    "toxicity_experiment": "unknown"
  }
}
```

对应 Python 调用：`DecisionEngine(project_root).candidate_payload(compound_id)`。

新 SMILES 接口已经定义，但当前不会在缺少 Docking、外部先验和 ADMET 时虚构分数：

```json
{
  "compound_id": "ATP-REQUEST-AB1DE819EDE9",
  "canonical_smiles": "CCO",
  "score": null,
  "confidence": "unknown",
  "explanation": "A new SMILES requires upstream Docking, Model v3-compatible features, external-prior predictions, and ADMET computation before the transparent decision formula can run.",
  "status": "requires_upstream_computational_evidence",
  "missing_experimental_evidence": {
    "MIC": "unknown",
    "ATP_enzyme": "unknown",
    "toxicity": "unknown"
  }
}
```

对应 Python 调用：`DecisionEngine(project_root).prepare_smiles_payload(smiles)`。未来软件层需要先调用特征提取、Docking/评分和外部 prior 模型，再进入本决策公式。

## 7. 命令行入口

- 生成排序与两份报告：`.venv/Scripts/python.exe src/decision_engine.py run`
- 查询已有候选 JSON：`.venv/Scripts/python.exe src/decision_engine.py explain --compound-id <ID>`
- 准备新 SMILES 请求：`.venv/Scripts/python.exe src/decision_engine.py prepare-smiles --smiles <SMILES>`

## 8. 限制

- 评分权重是可审计的项目决策规则，尚未由前瞻性实验优化；
- 分位分数依赖当前候选批次，不能跨批次直接比较；
- Binding 内部证据相关，存在重复强调计算结合证据的风险；
- ATP 与抗菌分量来自外部模型和结构相似性，存在 domain shift；
- 当前没有真实实验闭环，不能把 final score 描述为发现新药的成功概率。
