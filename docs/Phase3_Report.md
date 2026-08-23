# ATP-Navigator Phase 3 Report — AI Ranking v1.0

更新日期：2026-08-22  
模型版本：`lightgbm_enhanced_v1.0`  
训练数据：`dataset_v0.2`

## 1. 当前模型

Phase 3 建立了第一个可运行的 ATP-Navigator AI ranking pipeline：

候选分子与来源计算记录核验 → Morgan / RDKit / Docking / QuickProp 特征提取 → LightGBM 排序分数 → 候选优先级分数。

模型预测目标是 VSW 静态 MM/GBSA 计算排序，lower-is-better。它不是生物活性预测模型，也不输出成药概率。`candidate_priority_score` 是模型原始分数在当前候选批次内转换得到的 0–100 排名分数，higher-is-better，不是校准概率。

模型采用固定、小样本约束参数：160 棵树、learning rate 0.03、num leaves 7、max depth 3、min child samples 2、固定随机种子 42。没有使用 GNN、Transformer、大模型或 Agent。

## 2. dataset_v0.2

### 2.1 样本与身份规则

- 样本数：17 个独立候选；
- 唯一 compound ID：17；
- 唯一 InChIKey：17；
- Bemis–Murcko scaffold：11 组；最大组 4 个样本；
- 身份条件：`VSW.csv` 的来源 SMILES 与 `VSW.maegz` 中的 SMILES、compound code、variant 和计算记录必须形成唯一匹配；
- 无法确认身份、出现多重记录或缺失必要字段的记录不进入数据集。

每个样本明确保存：

- `compound_id`、compound code、variant、历史 Hit 名称；
- SMILES、canonical SMILES、InChIKey、scaffold；
- `feature_source`：`VSW.maegz`；
- `label_source`：`VSW.csv`；
- label type、protocol 和 score direction；
- `mapping_confidence=confirmed`。

两个来源文件均在 dataset metadata 中保存 SHA-256，用于复现和文件版本核验。

### 2.2 特征

Model 2 使用 1,089 个特征：

| 特征组 | 数量 | 来源与处理 |
|---|---:|---|
| Morgan fingerprint | 1,024 | radius=2，1024 bit，启用手性，由核验后的来源 SMILES 计算 |
| RDKit descriptors | 11 | MW、LogP、TPSA、HBD、HBA、可旋转键、芳香环、Fraction Csp3、重原子、总环数、形式电荷 |
| Docking | 11 | Glide docking score、gscore、emodel、energy、evdw、ecoul、einternal、state penalty、三类 ligand efficiency |
| QuickProp | 43 | 原始 51 个字段均为 17/17 完整；其中 8 个为常量，保留在 manifest 但不进入拟合 |

MM/GBSA、ADMET 和任何标签衍生字段均未作为 Model 2 输入。所有 Docking 与 QuickProp 字段来自和候选身份相同的 VSW 记录。

## 3. 公平比较

三组结果均使用相同的 17 候选和相同 MM/GBSA 标签。两个 LightGBM 模型使用相同的 scaffold-grouped leave-one-group-out OOF 协议；Docking-only 不拟合模型，直接按 Glide score 排序。

| 模型 | Spearman | RMSE | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---:|---:|---:|---:|---:|
| Model 0：Docking-only | -0.532 | 40.232* | 0.275 | 0.68 | 0.20 |
| Legacy P1 LightGBM | 0.598 | 6.700 | 0.788 | 1.36 | 0.40 |
| Model 2：LightGBM enhanced | **0.752** | **4.846** | 0.777 | 1.36 | 0.40 |

\* Docking score 与 MM/GBSA 不在同一数值尺度，Model 0 的 RMSE 仅为统一程序输出，不适合作为主要比较依据。

### 3.1 相对历史 LightGBM

- Spearman：0.598 → 0.752，增加 0.154；
- RMSE：6.700 → 4.846，下降约 27.7%；
- NDCG@5：0.788 → 0.777，轻微下降 0.010；
- Top-5 enrichment：1.36 → 1.36，持平；
- Hit recovery：0.40 → 0.40，持平。

因此 Model 2 的改进是“整体排序相关性和连续分数误差改善”，不是所有 Top-k 指标全面提高。当前结果支持“增强特征有潜力改善候选顺序判断”，但不支持“已稳定提升所有排名指标”。

### 3.2 相对 Docking-only

Docking-only 在当前候选集上的 Spearman 为负，NDCG@5 和 hit recovery 也明显低于两个 ML 模型。这说明单一 Glide score 在该 17 候选集上不能稳定复现后续 MM/GBSA 排序，同时也提供了 AI 证据融合的展示基础。

## 4. SHAP 解释

SHAP 基于最终全量拟合的 `lightgbm_enhanced_v1.0` 计算。前列特征为：

1. Glide ligand efficiency；
2. Glide ligand efficiency SA；
3. Glide emodel；
4. Glide docking score；
5. Glide gscore；
6. QuickProp ionization potential；
7. QuickProp non-hydrogen atom count；
8. RDKit heavy atom count；
9. Glide electrostatic energy；
10. Morgan bit 72。

模型主要依赖结合评价相关字段，同时使用 QuickProp、分子大小和局部结构位点调整顺序。这符合“AI 融合多类计算证据，而不是替代 Schrödinger”的项目定位。

SHAP 值解释的是对模型原始 MM/GBSA 预测值的影响：负 SHAP 值推动预测向更低、更优方向移动，正 SHAP 值推动预测向更高、更差方向移动。Morgan bit 在没有保存 bitInfo 子结构映射前只按 bit 编号展示，不赋予机制含义。

该 SHAP 分析是 17 个样本上的 full-fit 探索性解释，不是 OOF 因果解释，也不能证明特征对应真实生物机制。

## 5. AI ranking workflow 输出

`results/ranking_output.csv` 保存：

- compound ID、VSW code、历史 Hit 名称和 SMILES；
- 模型版本；
- `model_raw_score`；
- `ai_rank`；
- `candidate_priority_score`；
- Glide score 与参考 MM/GBSA；
- feature source 和 prediction scope。

当前输出是在 dataset_v0.2 上进行的 retrospective full-fit demonstration。它用于展示端到端工作流，不作为独立外部验证性能。对新候选调用保存模型时，必须提供和模型 bundle 完全一致、身份已核验且无缺失的 1,089 个特征；管线遇到缺字段会失败，不进行静默填补。

## 6. 当前限制

1. 只有 17 个候选、11 个 scaffold，模型稳定性和 SHAP 排名对单个样本敏感。
2. 标签是静态 MM/GBSA 计算值，不是 ATP 合酶抑制活性、MIC、IC50 或其他实验结果。
3. 候选已经经过上游虚拟筛选，存在明显选择偏差，不能代表完整化学空间。
4. 没有独立外部测试集；当前性能来自 scaffold-grouped OOF。
5. 模型参数为固定小样本配置，未在当前数据上进行大规模调参，以避免进一步的模型选择偏差。
6. Docking、emodel 和 ligand efficiency 高度相关；SHAP 贡献会在相关特征之间分配，不能把单个排序解释为唯一机制。
7. 全量模型在训练候选上的 ranking output 不能作为泛化证据。

## 7. 下一步计划

1. 对 Model 2 增加 scaffold-level bootstrap 区间和折间排序稳定性分析。
2. 建立预注册特征消融：Morgan → +RDKit → +Docking → +QuickProp，量化每一类证据的边际贡献。
3. 恢复更多完整筛选记录和中间候选，扩大同协议 MM/GBSA 样本，而不是升级复杂模型。
4. 实验活性产生后建立独立 `experimental_labels` 数据版本，与计算标签并行保存并进行真正的外部验证。
5. 为重要 Morgan bit 保存 RDKit bitInfo 和对应子结构，增强化学可解释性。
6. 在样本量、scaffold 数和外部验证满足门槛前，继续不开发 GNN、Transformer 或前端。

