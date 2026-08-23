# ATP-Navigator Baseline 实验记录

版本：Phase 1 / v0.x（保留）与 Phase 1.5 严格 benchmark（增量）  
更新日期：2026-08-22

## 1. 模型目标与边界

当前模型目标是：**在传统虚拟筛选之后优化候选优先级排序**。

当前模型不是：

- 真实抗菌活性预测模型；
- 新药发现有效性证明；
- Schrödinger Docking、MM/GBSA 或 MD 的替代工具。

当前监督标签来自计算评价结果。模型学习的是现有计算筛选结果中的排序规律，尚不能外推为 MIC、IC50、抑菌圈或其他实验活性。

## 2. 数据来源

### 2.1 Dataset v0.1

| 数据表 | 当前用途 |
|---|---|
| `data/molecules.csv` | 分子主键、历史别名、SMILES 和结构来源。 |
| `data/screening_records.csv` | HTVS、MM/GBSA、ADMET 聚合记录。 |
| `data/systems.csv` | IN-2 与 HIT 两个 MD 体系及轨迹状态。 |
| `data/raw_manifest.csv` | 原始文件路径、SHA-256、模块和完整性状态。 |

当前结构化数据包含：

- 1,659 条分子记录；
- 4,373 条 HTVS 构象/变体记录，对应 1,633 个来源 compound code；
- 17 个同时具有 SMILES、VSW MM/GBSA 分数和 ADMET 聚合值的候选；
- 2 个 MD/MMGBSA 体系均值，其中原始 XTC 仍为下载残片；
- 18 条 ADMET 记录，当前结构化字段仅保留 27 个二元预测端点的总和。

### 2.2 当前 ML 训练集

训练集由以下条件得到：

1. `score_MMGBSA` 非空；
2. SMILES 可由 RDKit 解析；
3. 记录具有唯一 `canonical_id`。

最终得到 17 个候选。每个候选只有一条用于训练的 VSW 静态 MM/GBSA 标签，分数方向为越低越优。

IN-2 和 HIT 的 MD 逐帧 MM/GBSA 均值没有混入这 17 个候选的训练标签，因为当前数据层尚未建立它们与候选 SMILES 的可核验映射。

## 3. 特征

### 3.1 已进入当前 ML baseline 的特征

| 特征组 | 数量 | 设置 | 当前覆盖 |
|---|---:|---|---:|
| Morgan fingerprint | 1,024 | radius=2，包含手性 | 17/17 训练候选 |
| RDKit 理化描述符 | 10 | MolWt、LogP、TPSA、HBD、HBA、可旋转键、FractionCSP3、重原子数、环数、形式电荷 | 17/17 |
| ADMET 聚合证据 | 1 | 源工作簿 27 个二元端点之和 | 17/17 |

总候选特征列为 1,035。中位数填补和零方差筛选均放在交叉验证折内执行。

### 3.2 当前没有进入 ML baseline 的特征

- Docking/HTVS：1,633 个 HTVS 主键与 17 个 MM/GBSA 候选之间没有已验证的身份桥接，不能按文件名或排序位置强制合并。
- QuickProp：当前 `molecules.csv` 和 `screening_records.csv` 未结构化保存 QuickProp 字段。
- 蛋白–配体相互作用：现有 PDB、MD 报告和图像尚未形成按 `canonical_id` 对齐的数值特征表。
- MD 动态特征：仅两个体系，且原始轨迹不完整，不能作为 17 个候选的统一训练特征。

## 4. 模型与参数

### Model 0：Docking-only

- 输入：每个 HTVS `canonical_id` 的最佳（最低）Glide `r_i_docking_score`；
- 聚合：同一 compound code 的构象/变体取最优分数；
- 输出：1,633 个 HTVS 化合物的原始计算排序；
- 不进行模型拟合。

### Model 1：Random Forest

- `n_estimators=500`
- `max_features="sqrt"`
- `min_samples_leaf=2`
- `random_state=42`
- `n_jobs=1`

### Model 2：XGBoost

- `n_estimators=300`
- `max_depth=3`
- `learning_rate=0.03`
- `subsample=0.8`
- `colsample_bytree=0.8`
- `reg_alpha=0.05`
- `reg_lambda=1.0`
- `objective="reg:squarederror"`
- `random_state=42`

### Model 3：LightGBM

- `n_estimators=300`
- `num_leaves=7`
- `max_depth=3`
- `learning_rate=0.03`
- `min_child_samples=3`
- `subsample=0.8`
- `colsample_bytree=0.8`
- `reg_lambda=1.0`
- `random_state=42`

## 5. Phase 1 原始 baseline 结果（保留）

Phase 1 使用 leave-one-molecule-out（17 折 LOOCV），输出为折外预测。

| 模型 | n | Spearman | RMSE | NDCG@5 | Top-5 recall |
|---|---:|---:|---:|---:|---:|
| Docking-only | 0 | — | — | — | — |
| Random Forest | 17 | -0.0392 | 7.6438 | 0.6180 | 0.40 |
| XGBoost | 17 | 0.5564 | 6.8415 | 0.8078 | 0.60 |
| LightGBM | 17 | 0.6740 | 6.4267 | 0.8443 | 0.60 |

Docking-only 的 `n=0` 表示它与 17 个 MM/GBSA 候选没有已验证主键交集，并不表示没有完成 HTVS 排序。其 1,633 条排序仍保存在 `results/docking_only_ranking.csv`。

## 6. 数据划分与泄漏审查

### 6.1 未发现的直接泄漏

- 17 个训练候选具有 17 个唯一 `canonical_id`；
- 原始 SMILES、RDKit canonical SMILES、InChIKey 和 connectivity key 均为 17 个唯一值；
- 同一化合物不同构象没有作为不同训练行进入训练集和验证集；
- Morgan、描述符和 ADMET 特征不包含目标列；
- 中位数填补和零方差筛选在每个训练折内部拟合；
- 每个候选只有一条 VSW 静态 MM/GBSA 训练标签。

### 6.2 已发现的结构家族泄漏风险

- 17 个候选只有 11 个 Bemis–Murcko 骨架；
- 最大同骨架组包含 4 个候选；
- 4 对候选的 Morgan Tanimoto 相似度不低于 0.7，最大值为 0.855；
- 原始 LOOCV 只留出单个分子，因此同骨架类似物可能留在训练折中，使泛化指标偏乐观。

这不是同一化合物重复进入训练测试的直接泄漏，但属于结构家族层面的划分风险。

### 6.3 已实施修正

Phase 1.5 新增 scaffold-grouped leave-one-out：每次将一个完整 Bemis–Murcko 骨架组作为测试集，该骨架的其他分子不会留在训练侧。旧 LOOCV 结果不删除，作为第一版 baseline 保留。

### 6.4 标签一致性风险

当前 17 个训练标签均来自 `VSW.csv` 的静态 MM/GBSA 分数，内部没有混入 MD 帧均值。但 `screening_records.csv` 的 `stage=MMGBSA` 还包含 IN-2 和 HIT 两个 MD 体系的 1,000 帧均值。两类数值计算协议和聚合方式不同，仅靠 `stage` 字段不足以区分。

修正方案：在 Dataset v0.2 增加 `score_type`、`protocol_id`、`aggregation`、`unit` 和 `pose_or_system_id`，在模型入口按协议显式筛选。

## 7. Phase 1.5 严格 benchmark

| 模型 | 协议 | n | Spearman | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---|---:|---:|---:|---:|---:|
| Model 0 Docking-only | 无共同评价集 | 0 | — | — | — | — |
| Model 1 Random Forest | scaffold-grouped LOGO | 17 | 0.1397 | 0.7189 | 1.36 | 0.40 |
| Model 2 XGBoost | scaffold-grouped LOGO | 17 | 0.5319 | 0.7781 | 1.36 | 0.40 |
| Model 3 LightGBM | scaffold-grouped LOGO | 17 | 0.5984 | 0.7877 | 1.36 | 0.40 |

定义：真实 hits 为 MM/GBSA 最优的 Top 5；hit recovery 为预测 Top 5 找回真实 Top 5 的比例；top-k enrichment 为实际找回数量除以随机排序的期望找回数量。17 个候选中随机 Top 5 的期望重叠为 `25/17`，当前三个模型均找回 2 个，因此 enrichment 为 1.36。

## 8. 当前限制

1. 样本量只有 17，任何指标置信区间都很宽，模型间差异不能解释为稳定胜负。
2. 标签是计算 MM/GBSA，不是生物活性真值。
3. 17 个候选来自已经筛选后的 Top hits，缺少大规模中等分子和负样本，存在选择偏差。
4. Docking-only 与 ML 模型尚不能在相同候选集合上公平比较。
5. ADMET 目前只有端点总和，丢失了具体风险类型及概率信息。
6. 尚未进行独立外部验证、嵌套模型选择或实验活性验证。

因此，当前结果只能支持“传统 ML 可以学习并重排现有计算候选”的初步证据，不能支持“AI 已提高真实药物发现成功率”的结论。
