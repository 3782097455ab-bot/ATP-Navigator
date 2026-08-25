# ATP-Navigator Development History

审计日期：2026-08-23

审计范围：Git 提交历史，以及仓库中的 `docs/`、`src/`、`models/`、`results/`、数据版本元数据和模型评价表。本文记录的是可由现有文件证明的开发历史，不把策划书中的未来计划当作已完成工作。

## 审计结论与历史边界

当前 Git 历史不能逐次还原 Phase 0 到 Model v2 的开发过程。提交 `6b78660` 在 2026-08-23 一次性导入了 118 个项目文件，其中已经包含 Dataset v0.1/v0.2/v1.0、baseline、enhanced ranking v1.0、Model v2、Phase 4 排序实验及其报告。因此：

- Git 可以证明这些文件在首次项目导入时已经存在；
- Git 不能证明这些阶段各自的准确编码日期、训练日期或提交顺序；
- 文件内部明确写有 `2026-08-22` 的报告，可以把该日期记录为文档更新时间；
- Dataset v1.0 元数据明确记录 `created_at=2026-08-22T18:26:34.881Z`；
- 没有内部时间戳的阶段，其开发日期记为 `unknown`，只保留 Git 导入日期；
- Model v3 有独立提交，因此其实现和入库时间可以由 Git 确认。

本文 Phase 0–4 是面向整个项目历史的总结性分段，不完全等同于旧文件名中的 Phase 编号。

## 后续维护记录格式

每次重大开发完成后，必须在本文追加一条已完成记录，至少包括：日期、开发阶段、目标、新增文件、修改文件、使用数据、实现功能、模型变化、性能变化和当前限制。只有已经生成并核验的代码、数据、模型或文档才能登记；未来计划继续保留在Current System Status的未完成任务中。

## 模型名称映射

项目早期和当前比较表使用过不同命名，必须区分：

| 历史名称 | 当前历史文档中的含义 | 主要特征 |
|---|---|---|
| Phase 1 Model 1 | Random Forest baseline | Morgan1024 + RDKit10 + ADMET_SUM |
| Phase 1 Model 2 | XGBoost baseline | Morgan1024 + RDKit10 + ADMET_SUM |
| Phase 1 Model 3 / Legacy P1 LightGBM | 当前统一比较中的 Model v1 | Morgan1024 + RDKit10 + ADMET_SUM，共 1,035 项 |
| `lightgbm_enhanced_v1.0` | baseline 后的中间增强版本；在 `phase3_model_comparison.csv` 中曾命名为 Model 2 | Morgan1024 + RDKit11 + Docking11 + QuickProp43，共 1,089 项 |
| `ATP-Navigator_Model_v2.0` 的 v2-B | 当前统一比较中的 Model v2 | 上述 1,089 项 + 4 个外部任务先验，共 1,093 项 |
| `ATP-Navigator_Model_v3.0` | 当前统一比较中的 Model v3 | 结构、相似性、Docking、QuickProp、ADMET 与外部先验，共 1,128 项 |

# 项目总体演化

```text
真实计算化学项目资产
        ↓
文件与化合物身份资产化
        ↓
17 个内部候选的计算排序 baseline
        ↓
Dataset v1.0 三层外部知识注册表
        ↓
任务隔离的 Model v2 外部先验
        ↓
Model v3 结构与证据增强排序
```

整个开发链的监督目标始终需要区分：内部排序模型的标签是同协议静态 MM/GBSA 计算分数，不是真实抗菌活性。MIC、IC50、Docking、静态 MM/GBSA 和 MD/MMGBSA 没有被混合作为一个标签。

## Phase 0：原始科研项目基础

### 可确认的科研资产

- 靶点：鲍曼不动杆菌 F1F0-ATP synthase；现有 MD 系统登记的蛋白结构标识为 7P3W。
- Schrödinger 虚拟筛选：原始资产包含 HTVS 分片、VSW 候选表和 Maestro 结构/属性记录。
- 可解析 HTVS：4,373 条构象或变体记录，对应 1,633 个来源 compound code；只来自当前可读的 001、002、003 分片。
- VSW 候选：17 个具有 SMILES 和静态 MM/GBSA 分数的候选。
- MD/MMGBSA：IN-2 与 HIT 两个体系各有 1,000 帧衍生 MM/GBSA 数据；两套原始 XTC 均为未完成下载片段。
- Hit 资产：存在 Top-1 至 Top-5、HIT/Hit3、ATP-Top1-MD2、编号 466 表征等历史名称和结构/展示文件。
- 化学表征：编号 466 存在两份 1H NMR 和一份 LC-MS PDF。Phase 0 初始审计时，466 与 HIT/Top 候选之间尚未建立可审计映射；后续 compound mapping 才将 `Hit3`、`Top-3`、`466`、`ATP-Top1-MD2` 映射到同一 canonical ID，并标记为 confirmed。

### 当时未具备的内容

- 没有 AI 模型；
- 没有真实生物活性训练标签；
- 没有从原始库到 HTVS/SP/XP/MMGBSA 的完整 compound-level workflow 表；
- MD 原始轨迹不完整；
- 部分原始/衍生文件被审计为 incomplete、corrupted 或 unknown。

Phase 0 的原始科研工作完成日期未记录在 Git 中，记为 `unknown (pre-Git)`。

## Phase 1：数据资产化

### 做了什么

第一步只读扫描 `表征/`、`运行/`、`作图/`，建立 Dataset v0.1 文件级资产层。审计报告记录 159 个原始文件，总大小 2,838,985,130 字节；状态为 complete 11、incomplete 7、corrupted 5、derived 128、unknown 8。

建立了四张核心表：

- `data/raw_manifest.csv`：路径、文件类型、大小、SHA-256、模块和完整性状态；
- `data/molecules.csv`：canonical ID、历史别名、结构来源、SMILES 和身份置信度；
- `data/screening_records.csv`：HTVS、MMGBSA 和 ADMET 计算记录；
- `data/systems.csv`：IN-2、HIT 两个 MD 系统及轨迹状态。

随后增量建立 `compound_mapping_v1.csv` 和 Dataset v0.2：

- 17 个内部候选按 canonical SMILES、InChIKey 和 compound ID 去重；
- 形成 11 个 Bemis–Murcko scaffold；
- 将 VSW.csv 静态 MM/GBSA 与 VSW.maegz 中相同化学身份的 Docking/QuickProp 记录连接；
- 生成 `samples.csv`、`feature_manifest.csv` 和 `dataset_metadata.json`；
- 对 Hit3、Top-3、466、ATP-Top1-MD2 等历史别名建立置信度分级映射。

### 新增的主要文件

- `DATA_AUDIT_REPORT.md`
- `data/raw_manifest.csv`
- `data/molecules.csv`
- `data/screening_records.csv`
- `data/systems.csv`
- `data/compound_mapping_v1.csv`
- `data/dataset_v0.2/samples.csv`
- `data/dataset_v0.2/feature_manifest.csv`
- `docs/data_dictionary.md`
- `src/build_dataset_v0_1.mjs`
- `src/build_phase2_assets.mjs`
- `src/feature_pipeline.py`
- `src/feature_pipeline_v2.py`

### 解决的问题

- 原始文件从“按文件夹人工理解”转为可检索、带 hash 的数据资产；
- 重复压缩包、衍生图片和不完整轨迹不再被误当成独立训练样本；
- 同一化合物不同构象/别名可以在 compound level 聚合；
- 静态 MM/GBSA 与 MD/MMGBSA 的来源和协议得到区分；
- 后续模型可以从固定的 17 个身份确认候选和明确标签协议启动。

### 仍未解决的问题

- 缺少完整实验生物活性；
- 只有 17 个统一静态 MM/GBSA 标签；
- 两个 MD 体系不足以形成分子级监督训练集；
- Dataset v0.1 的初始表不等于完整科研 workflow。

`DATA_AUDIT_REPORT.md`、Baseline/Feature Engineering 报告记录的更新时间为 2026-08-22；相关文件直到 2026-08-23 才通过 `6b78660` 一次性进入 Git，阶段内部提交历史缺失。

## Phase 2：Baseline 模型

### 输入和标签

初始 ML baseline 使用 17 个内部候选：

- Morgan fingerprint：radius=2、1,024 bit、包含手性；
- RDKit10：MolWt、LogP、TPSA、HBD、HBA、可旋转键、FractionCSP3、重原子数、环数、形式电荷；
- ADMET_SUM：27 个二元预测端点的源聚合值；
- 总特征数：1,035。

监督标签为 VSW.csv 的静态 MM/GBSA dG Bind，lower-is-better。IN-2/HIT 的 MD/MMGBSA 均值没有混入该标签。

### 模型

- Model 0：HTVS/Docking 原始排序；初始阶段因缺少与 17 个候选的已验证 ID bridge，不能在共同集合上评价；
- Random Forest；
- XGBoost regression；
- LightGBM regression。

早期使用 17 折 leave-one-molecule-out。数据审查发现 17 个候选只有 11 个 scaffold，最大 scaffold 组含 4 个样本；这不是同一化合物重复泄漏，但随机留单分子会造成结构家族泄漏风险。因此 Phase 1.5 保留旧结果，同时新增 scaffold-grouped leave-one-out benchmark。

### 严格 benchmark 结果

| 模型 | Spearman | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---:|---:|---:|---:|
| Random Forest | 0.1397 | 0.7189 | 1.36 | 0.40 |
| XGBoost | 0.5319 | 0.7781 | 1.36 | 0.40 |
| LightGBM / 当前 Model v1 | 0.5984 | 0.7877 | 1.36 | 0.40 |

这一阶段证明传统 ML 能学习并重排已有计算候选，但不能证明预测真实活性。17 个样本使模型间差异高度不稳定。

### Baseline 后的中间增强版本

`lightgbm_enhanced_v1.0` 在相同 17 候选上增加 RDKit 第 11 个描述符、11 个核验 Docking 字段和 43 个完整非恒定 QuickProp 字段，总计 1,089 个特征。scaffold OOF 结果为 Spearman 0.7525、RMSE 4.8462、NDCG@5 0.7774、Top-5 enrichment 1.36、Hit recovery 0.40。

该版本建立了首个完整的候选输入 → 特征提取 → LightGBM → priority score 管线，并生成 SHAP feature importance。它是 Model v2 的直接内部对照，但不是当前统一命名中的 external-knowledge Model v2。

### 主要文件

- `src/baseline_train.py`
- `src/evaluation.py`
- `src/benchmark_phase15.py`
- `src/phase3_ranking.py`
- `models/random_forest_mmgbsa_baseline.joblib`
- `models/xgboost_mmgbsa_baseline.joblib`
- `models/lightgbm_mmgbsa_baseline.joblib`
- `models/lightgbm_enhanced_v1.joblib`
- `results/baseline_comparison.csv`
- `results/phase3_model_comparison.csv`
- `results/feature_importance.csv`
- `docs/Baseline_Report.md`
- `docs/Phase3_Report.md`

上述报告内部日期为 2026-08-22；对应 Git 记录仍只有 2026-08-23 的批量导入，具体训练时间无法从 Git 单独确认。

## Phase 3：External Knowledge Enhancement

### 新增数据

公开数据库审计对象原始规模为 6,777 行、2,313 个唯一 compound ID。Dataset v1.0 在去除 35 条精确重复记录和两个冲突 ID 的 24 条记录后，形成 6,754 行三层证据注册表：

| 层 | 行数 | 含义 |
|---|---:|---|
| Layer 1 | 6,355 | Gram-negative antibacterial MIC；用于一般抗菌化学空间/表型知识 |
| Layer 2 | 363 | ATP synthase specific evidence；包含直接 ATP assay、ATP 系列 MIC、ETC、细胞毒性和注释记录，不能视为同一标签 |
| Layer 3 | 36 | 内部 Docking、静态 MM/GBSA 和 MD/MMGBSA 证据记录 |

Dataset v1.0 元数据明确记录创建时间为 2026-08-22T18:26:34.881Z。数据来源置信度描述的是溯源质量，不代表活性已由团队实验确认。

### 为什么需要外部知识

内部主任务只有 17 个静态 MM/GBSA 样本，不能稳定训练复杂模型。外部数据用于学习一般抗菌化学空间和 ATP 合酶抑制相关结构规律，再以辅助预测先验连接内部排序任务，而不是把外部数值直接拼成内部标签。

### 如何避免标签混乱

Model v2 将任务分开：

- Task A：按 organism 分开的 Gram-negative whole-cell MIC regression；
- Task B：按 organism、target、activity type、unit、assay/source 隔离的 ATP synthase IC50 ranking/regression；
- Task C：17 个内部候选的静态 MM/GBSA ranking。

控制措施包括：

- 训练前按 RDKit canonical SMILES 去重；
- 同一结构的重复实验取同一任务内 log 标签中位数；
- 外部数据与内部 17 个结构检查重叠，本次为 0；
- 外部任务使用 scaffold group split；内部 Task C 使用 11 折 Leave-One-Scaffold-Group-Out；
- MIC、IC50 和 MM/GBSA 保持不同标签空间；
- 外部模型预测只作为 Task C 的 4 个辅助 prior features。

### Model v2 结果

| 模型 | 特征数 | Spearman | RMSE | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---:|---:|---:|---:|---:|---:|
| 中间增强版 `lightgbm_enhanced_v1.0` | 1,089 | 0.7525 | 4.8462 | 0.7774 | 1.36 | 0.40 |
| Model v2-A structure-only | 1,035 | 0.6299 | 6.8280 | 0.8285 | 2.04 | 0.60 |
| Model v2-B external enhanced / 当前 Model v2 | 1,093 | 0.7574 | 4.9226 | 0.7744 | 1.36 | 0.40 |

Model v2-B 的 Spearman 比中间增强版小幅增加，但 RMSE、NDCG@5 和 Top-k 没有改善。Model v2-A 的 Top-5 指标较高，但只有 17 个样本，不能据此判定稳定优胜。

### 主要文件

- `data/dataset_v1.0/ATP_Navigator_Dataset_v1.csv`
- `data/dataset_v1.0/dataset_metadata.json`
- `docs/Dataset_Audit_v1.md`
- `docs/Label_Policy.md`
- `src/model_v2_pipeline.py`
- `models/model_v2/`
- `results/model_v2/`
- `docs/Model_v2_Report.md`

Model v2 文件没有独立 Git 提交，而是在 `6b78660` 中批量导入。因此 Model v2 的准确开发/训练时间为 `unknown`；只能确认 Dataset v1.0 的元数据时间和 2026-08-23 的 Git 入库时间。

## Phase 4：Model v3

### 新增特征

Model v3 在当前 Model v2-B 的外部先验基础上建立 1,128 项特征：

| 特征组 | 数量 |
|---|---:|
| Morgan fingerprint | 1,024 |
| Enhanced RDKit descriptors | 16 |
| Chemical similarity/scaffold | 2 |
| Docking | 11 |
| 完整非恒定 QuickProp | 43 |
| ADMET endpoints | 28 |
| External knowledge priors | 4 |

新增的结构描述包括分子量、精确分子量、LogP、TPSA、HBD/HBA、可旋转键、芳香/脂肪/饱和环、总环数、重原子/总原子数、FractionCSP3、形式电荷和摩尔折射率。

chemical space 特征使用 55 个去重的、来源可追溯但未逐条内部复核的直接 ATP assay 参考结构。它们与内部 17 个 canonical SMILES 的精确重叠为 0；内部候选对参考集的最大 Morgan-Tanimoto 相似度为 0.3014。

`binding_feature_table.csv` 汇总 17 个内部候选和 IN-2 参考物的 Docking、静态 MM/GBSA、MD/MMGBSA 与 MD interaction 证据。MD 只覆盖 IN-2 和 Hit3，内部训练候选覆盖为 1/17，因此 MD 特征没有进入 Model v3，也没有进行缺失值填补。静态 MM/GBSA 始终只作为监督标签。

### 模型变化

- 算法仍为固定参数 LightGBM regression；
- 未进行小样本超参数搜索；
- 使用与 Model v2 同类的 11 折 scaffold LOGO OOF 评价；
- 新增 chemical similarity、scaffold coverage、完整 ADMET endpoint 和扩展 RDKit descriptors；
- 保留 4 个 Model v2 外部任务先验；
- 最终全数据拟合模型只用于生成当前 candidate ranking，不用于性能统计。

### 性能变化

| 模型 | Spearman | RMSE | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---:|---:|---:|---:|---:|
| Model v0 Docking | -0.5319 | 40.2317* | 0.2747 | 0.68 | 0.20 |
| Model v1 baseline LightGBM | 0.5984 | 6.7001 | 0.7877 | 1.36 | 0.40 |
| Model v2 external enhanced | 0.7574 | 4.9226 | 0.7744 | 1.36 | 0.40 |
| Model v3 feature enhanced | 0.7696 | 4.8877 | 0.7782 | 1.36 | 0.40 |

`*` Docking score 与 MM/GBSA 是不同量纲，Model v0 RMSE 仅作形式对照。

Model v3 相比 Model v2：Spearman +0.0123，RMSE 改善 0.0349，NDCG@5 +0.0038；Top-5 enrichment 和 hit recovery 没有变化。Model v1 的 NDCG@5 仍高于 Model v3。现有结果只能记录为小样本 OOF 下的轻微整体排序变化，不能宣称稳定性能提升。

### 局限

- 内部监督样本仍为 17；
- 没有独立外部测试集或前瞻性候选集；
- 没有真实 MIC/IC50 实验标签用于内部模型验证；
- ADMET 是预测端点，不是团队实验结果；
- 外部 Dataset v1.0 尚未逐条回源复核；
- MD 动态证据覆盖不足且原始轨迹不完整；
- Top-k 指标没有随 v2 → v3 提升。

### Git 证据和文件

Model v3 由独立提交 `e0a0ce5` 于 2026-08-23T16:29:41+08:00 加入，`ac06dc4` 只修正报告格式。新增内容包括：

- `src/model_v3_pipeline.py`
- `data/model_v3/chemical_space_analysis.csv`
- `data/model_v3/binding_feature_table.csv`
- `data/model_v3/training_table.csv`
- `models/model_v3/model.joblib`
- `models/model_v3/training_config.json`
- `models/model_v3/feature_list.json`
- `results/model_v3/model_v3_comparison.csv`
- `results/model_v3/model_v3_oof_predictions.csv`
- `results/model_v3/candidate_ranking.csv`
- `docs/Model_v3_Report.md`

## Phase 5：ATP-Navigator Intelligent Decision System

### 日期

2026-08-23；主体提交：`61d3b41`。

### 目标

在不修改Model v0–v3的前提下，将已有Model v3、Docking、静态MM/GBSA、外部ATP/抗菌prior、结构相似性、RDKit描述符和预测ADMET转换为透明的多目标候选决策排序。

### 新增文件

- `src/decision_engine.py`
- `scoring_config.json`
- `results/final_candidate_ranking.csv`
- `docs/Decision_Engine_Report.md`
- `docs/Candidate_Explanation_Report.md`
- `docs/Current_System_Status.md`
- `docs/Model_Registry.md`
- `docs/Data_Registry.md`

### 修改文件

- `docs/ATP_Navigator_Development_History.md`：追加本条已完成记录和维护格式；
- `docs/Model_Evolution_Table.csv`：追加Phase 5决策层记录。

### 使用数据

- `results/model_v3/candidate_ranking.csv`：Model v3当前17候选预测；
- `data/dataset_v0.2/samples.csv`：compound ID、结构描述符、Docking和静态MM/GBSA；
- `results/model_v2/external_priors_internal.csv`：AB whole-cell MIC、PA/Mtb/AB ATP IC50外部模型prior；
- `data/model_v3/chemical_space_analysis.csv`：直接ATP assay参考相似性；
- `data/admet_features_v0_2.csv`：27个预测ADMET风险端点和endpoint sum。

上述5个输入文件的SHA-256已写入`docs/Decision_Engine_Report.md`。

### 实现功能

- 将lower-is-better原始计算值转换为0–100、higher-is-better的当前批次rank percentile；
- 透明计算Binding、ATP target、Antibacterial和Drug-likeness四个分量；
- 按公开公式计算Final Score：0.45×Binding + 0.25×ATP target + 0.15×Antibacterial + 0.15×Drug-likeness；
- 所有最终权重、子权重、方向、描述符阈值和缺失策略写入`scoring_config.json`；
- AB ATP IC50 prior保留原值但权重为0，因为其Model v2外部子任务样本少且scaffold OOF Spearman为负；
- 实验MIC、ATP enzyme inhibition和toxicity全部标记为`unknown`，没有填补；
- 生成Top 5候选逐项解释；
- 提供已有compound ID查询JSON和新SMILES请求JSON接口；新SMILES缺少上游计算证据时返回`score=null`，不虚构分数；
- 相同输入重复运行得到相同ranking和两份报告SHA-256。

### 模型变化

无。Phase 5没有训练Model v4，也没有修改Model v0、v1、v2或v3。Decision Engine是可配置规则层，不是监督模型。

### 性能变化

无新的监督性能指标。Phase 5没有新增真实标签，不能报告新的Spearman、RMSE或NDCG提升。当前综合决策Top 1为`ATP-SMI-C93E6EC67CDB (Hit2)`，Final Score 73.9071；该值是当前17候选批次内的相对规则分数，不是成功概率或实验活性。

### 当前限制

- 权重是透明人工决策规则，尚未通过前瞻性实验优化；
- Model v3 prediction与静态MM/GBSA相关，Binding分量不是独立证据加和；
- ATP和抗菌分量来自外部模型/相似性，存在domain shift；
- 分位数依赖当前17候选批次，不能跨批次直接比较；
- 所有候选confidence为60/100的`medium_computational_only`；实验验证贡献为0；
- Final Score禁止回流为未来监督训练标签，避免自我循环标签。

## Phase 6A：Robustness & Benchmark Validation Module

### 日期

2026-08-23；主体提交：`2ab74a3`。

### 开发阶段

Phase 6A — Decision Engine稳健性与benchmark可用性验证。

### 目标

在不修改Model v0-v3、不重新训练监督模型的前提下，检查Phase 5 Decision Engine对预设权重变化和决策分量移除的敏感性，并建立严格只用于验证的external benchmark接口。

### 新增文件

- `src/phase6a_robustness.py`
- `results/phase6A/weight_sensitivity_results.csv`
- `results/phase6A/ranking_matrix.csv`
- `results/phase6A/ranking_stability_matrix.csv`
- `results/phase6A/top_candidate_consistency.csv`
- `results/phase6A/decision_ablation.csv`
- `results/phase6A/benchmark_results.csv`
- `results/phase6A/benchmark_report.md`
- `docs/Phase6A_Robustness_Report.md`
- `docs/Phase6A_Limitation_Report.md`

### 修改文件

- `docs/Current_System_Status.md`
- `docs/Model_Registry.md`
- `docs/Data_Registry.md`
- `docs/ATP_Navigator_Development_History.md`：追加本条已完成记录。

### 使用数据

- `results/final_candidate_ranking.csv`：17个内部候选的Phase 5四分量、默认Final Score和身份；
- `scoring_config.json`：Phase 5冻结默认权重和评分语义；
- `data/dataset_v1.0/ATP_Navigator_Dataset_v1.csv`：仅用于外部Layer 1/2与17候选的精确canonical SMILES重叠审计，不用于训练。

### 实现功能

- 对default及A-D五套透明权重重新计算17候选分数和排名；
- 生成25组场景对的Spearman和Kendall tau稳定性矩阵；
- 统计各候选在A-D四场景中的Top 3/Top 5出现频率、平均排名和排名范围；
- 完成Binding only、Binding + ATP、完整ATP-Navigator三组决策消融；
- 建立可选`data/external/curated/phase6a_benchmark.csv`验证接口，只有实验来源、精确结构匹配且endpoint/unit/direction单一时才允许计算相关性；
- 两次重复运行的7个结果文件和2份报告SHA-256均保持一致；
- 校验默认场景与Phase 5分数/排名完全一致，稳定性矩阵对称，完整消融与默认公式一致。

### 模型变化

无。没有修改或重新训练Model v0、v1、v2、v3，没有创建Model v4。Phase 6A是验证模块，不是监督模型。

### 性能变化

无新的监督性能指标，也没有真实活性性能提升声明。稳健性结果为：

- default、A、C、D场景Top 1均为`ATP-SMI-C93E6EC67CDB (Hit2)`；B场景Top 1为`ATP-SMI-5B36D3E11A3B (Hit13)`；
- A-D四场景最低两两Spearman为0.4583，最低Kendall tau为0.3235；
- `ATP-SMI-9DA3213A09E8 (Hit1)`是A-D中唯一始终进入Top 3、也唯一始终进入Top 5的候选；
- Binding only相对完整方案Spearman为0.6205、Kendall tau为0.4502；Binding + ATP分别为0.8971和0.7353；
- 当前可评价external benchmark数量为0，相关性指标保持空值。

这些数字衡量决策规则稳定性，不衡量实验活性准确率。

### 当前限制

- 只有17个经过预筛选的内部候选；
- 分量间存在计算证据相关性，不是独立证据；
- A-D只是预注册的有限权重场景，不能覆盖所有权重空间；
- 外部Layer 1/2与内部候选精确结构重叠为0；
- 没有内部MIC、ATP enzyme inhibition、实验毒性或独立前瞻性结果；
- benchmark状态为`not_evaluable`，不得描述为外部验证通过。

## Phase 6B：External Benchmark Pipeline

### 日期

2026-08-23；主体提交：`180a97d`。

### 开发阶段

Phase 6B — 公开ATP synthase inhibitor外部数据导入与严格验证准备。

### 目标

建立只用于验证的External Benchmark Pipeline，在不修改Model v0-v3、不修改Decision Engine评分逻辑且不训练模型的前提下，支持公开ATP synthase inhibitor记录的标准化、结构去重、Morgan fingerprint计算和严格评分门控。

### 新增文件

- `src/external_benchmark.py`
- `results/phase6B/standardized_benchmark_compounds.csv`
- `results/phase6B/benchmark_ranking.csv`
- `results/phase6B/benchmark_metrics.csv`
- `docs/Phase6B_External_Validation_Report.md`

### 修改文件

- `docs/Current_System_Status.md`
- `docs/Data_Registry.md`
- `docs/ATP_Navigator_Development_History.md`：追加本条已完成记录。

### 使用数据

- `data/dataset_v1.0/ATP_Navigator_Dataset_v1.csv`中的Layer 2，共363条公开ATP synthase相关记录；
- `results/final_candidate_ranking.csv`及Phase 5 Decision Engine现有17候选评分，仅用于精确结构匹配和原始评分调用；
- Dataset v1.0 Layer 2结构集合，用于检测Model v2外部知识训练结构重叠。

公开activity没有进入训练，也没有进入Decision Engine评分公式。

### 实现功能

- 支持字段`compound_id, SMILES, target, organism, activity_type, activity_value, reference`，并支持可选unit/source/confidence字段；
- 使用RDKit生成isomeric canonical SMILES，记录缺失或无效结构；
- 按canonical SMILES去重，同时保留来源compound ID、target、organism、activity type、unit和reference集合；
- 为每个唯一结构计算radius 2、2048 bit Morgan fingerprint，并保存512字符hex和on-bit count；
- 调用未修改的Phase 5 Decision Engine；新结构缺少上游计算证据时保持unscored；
- 对Model v2外部知识训练结构进行重叠标记，并从独立验证指标中排除；
- 只有训练不重叠、精确数值、且target/organism/activity type/unit/direction单一的stratum才允许计算Spearman和Kendall；
- 重复运行3个结果文件和报告得到相同SHA-256。

### 模型变化

无。没有修改或重新训练Model v0、v1、v2、v3，没有创建Model v4；Decision Engine代码、权重和评分逻辑均未修改。

### 性能变化

无新的性能指标。实际运行结果为：

- 输入363条，363条SMILES均可由RDKit解析；
- 去重后109个唯一结构，合并254条重复结构记录；
- 109/109结构均与Model v2外部知识训练结构重叠；
- 0个结构具备完整Decision Engine证据，`benchmark_ranking.csv`只有表头；
- `benchmark_metrics.csv`记录`status=empty`，Spearman和Kendall为空；
- 0个成功评价metric stratum。

这些结果是可用性和独立性审计，不是外部验证通过或模型性能下降。

### 当前限制

- 现有公开Layer 2已经参与Model v2外部知识构建，不是完全独立测试集；
- 外部新分子缺少Docking、静态MM/GBSA、Model v3和完整预测ADMET等Decision Engine必需证据；
- Layer 2混合MIC、IC50、细胞毒性、Activity和Inhibition，必须继续按端点和协议分层；
- 当前没有可计算外部验证相关性的已评分独立候选；
- 不能用Morgan fingerprint或公开activity直接替代Decision Engine缺失分量。

# Phase 7 — External Knowledge Enhanced Training Experiment

日期：2026-08-24

## 目标

在不修改Model v0-v3和Phase 5 Decision Engine正式输出的前提下，首次按Dataset v2.0规范分别建立抗菌MIC、ATP synthase target和内部候选排序任务，验证外部知识预测先验是否改善Model v3。

## 新增文件

- `data/dataset_v2.0/ATP_Navigator_external_dataset_v1.csv`
- `data/dataset_v2.0/dataset_metadata.json`
- `src/model_v4_alpha_pipeline.py`
- `models/model_v4_alpha/`：Task A模型、4个Task B分层模型、Task C模型、训练配置和feature list
- `results/model_v4_alpha/`：数据审计、任务路由、训练视图、OOF预测、外部prior、模型比较和shadow candidate ranking
- `docs/ATP_Navigator_Model_Input_Spec.md`
- `docs/ATP_Navigator_Data_Dictionary_v1.md`
- `docs/Dataset_QC_Report_external_source.md`
- `docs/Source_Quality_System.md`
- `docs/Model_v4_alpha_Report.md`

## 修改文件

- `docs/Current_System_Status.md`
- `docs/Model_Registry.md`
- `docs/Data_Registry.md`
- `docs/ATP_Navigator_Development_History.md`：追加本条已完成记录。

## 使用数据

- Dataset v2.0输入8,820行、4,338个RDKit canonical structures；Task A 6,663行、Task B 77行、Benchmark 2,080行；
- 8,573条exact value、239条censored value、8条range value；
- 内部Dataset v0.2的17个候选、11个scaffold和静态MM/GBSA计算标签；
- Model v3的1,128个已有特征与Phase 5四分量评分，仅作为保留基线与shadow决策输入。

`Dataset_QC_Report_external_source.md`描述的是早期6,777行主库，不能替代当前8,820行输入审计；Phase 7另行生成`dataset_audit.json`。source level和reference沿用提供文件标注，本阶段未逐条打开原论文或数据库复核。

## 实现功能

- 按Task A、Task B、Task C严格路由，MIC、不同IC50端点/单位、百分比和静态MM/GBSA不合并；
- 按canonical SMILES与Bemis–Murcko scaffold隔离划分，防止同结构/同scaffold泄漏；
- Task A以Morgan1024、RDKit descriptors和organism one-hot建立MIC回归，source level和confidence只作样本权重；
- Task B按activity type、organism species、unit建立独立模型，只有至少8个结构且3个scaffold的stratum训练；
- Task C保留Model v3全部特征，新增Task A/B外部知识预测先验；
- 2,080条Benchmark数据完全排除训练；
- 保存输入SHA-256、feature list、training config、OOF预测和small-data状态；
- 生成不覆盖Phase 5的Decision Engine shadow ranking，缺失MIC、ATP enzyme和毒性实验继续标记unknown。

## 模型变化

新增`Model v4-alpha`实验版本；Model v0-v3文件、配置和历史结果未修改。v4-alpha不是最终Model v4，也没有替代当前正式Model v3。

## 性能变化

- Task A正式A/B high-confidence切片：n=3,395，scaffold GroupKFold RMSE 0.8015 log10 μg/mL，Spearman 0.7464；classification accuracy因无预注册阈值而标记not applicable；
- Task B有4个可训练stratum，Spearman分别为0.6170、-0.3283、0.7037、0.0838，不能跨endpoint/unit汇总解释；
- 内部Task C：Model v4-alpha Spearman 0.7549、RMSE 4.9268、NDCG@5 0.7774、Top-5 enrichment 1.36、Hit recovery 0.40；
- 相同17候选协议下Model v3为0.7696、4.8877、0.7782、1.36、0.40。v4-alpha未改善相关性、误差、NDCG或Top-k，不能宣称外部知识已带来性能提升；
- shadow Decision ranking相对Phase 5的Spearman为0.7721、Kendall为0.6029、Top3重叠2/3、Top5重叠4/5；这些是排序变化，不是实验准确率。

## 当前限制

- Task C只有17个已筛选候选，且没有独立前瞻测试；
- Task B每个同质stratum只有8–25个样本，部分分层出现负或接近零的OOF相关；
- 外部模型输出是跨域计算prior，不是内部候选的MIC或ATP enzyme实验；
- censored/range activity本轮排除，尚未使用删失回归；
- Dataset v2.0与既有外部知识来源可能有内容重叠，不能作为独立外部验证；
- 当前最缺A. baumannii同一ATP synthase亚型、同一assay和同一unit的高质量实验数据，以及内部17候选真实MIC/ATP enzyme/毒性数据。

# Phase 8 — Data Acquisition Intelligence

日期：2026-08-24

## 目标

在Model v4-alpha未超过Model v3后，不继续增加模型复杂度，而是从现有HTVS资产中建立下一批可执行的结构导出、同协议MM/GBSA和实验数据回填任务，直接扩大内部Task C标签并降低Top-hit选择偏差。

## 新增文件

- `src/data_acquisition_planner.py`
- `results/phase8_data_acquisition/htvs_pool_audit.csv`
- `results/phase8_data_acquisition/mmgbsa_acquisition_queue.csv`
- `results/phase8_data_acquisition/data_requirements_priority.csv`
- `results/phase8_data_acquisition/acquisition_summary.json`
- `data/templates/phase8_mmgbsa_return_template.csv`
- `data/templates/phase8_experimental_activity_template.csv`
- `docs/Phase8_Data_Strengthening_Plan.md`

## 修改文件

- `docs/Current_System_Status.md`
- `docs/Data_Registry.md`
- `docs/ATP_Navigator_Development_History.md`：追加本条已完成记录。

## 使用数据

- `data/docking_features_v0_2.csv`：4,373个HTVS pose、1,633个canonical HTVS ID、3个Schrödinger源文件；
- `data/compound_mapping_v1.csv`与内部17候选：用于排除1个已知映射重叠；
- `data/molecules.csv`：核验HTVS ID的SMILES覆盖，当前为0/1,633；
- Model v3 training table和Phase 5 ranking：只用于生成17候选实验空白模板，没有训练或重新评分。

## 实现功能

- 按compound ID选择可追溯最佳pose，保留source file、title、variant、pose index及pose/variant计数；
- 对Docking、E-model、ligand efficiency和QuickProp完整性进行质量门控，得到1,632个eligible候选；
- 建立三个互补数据获取臂：20个exploitation、20个descriptor-space diversity、20个score calibration；
- 建立P0首批24个和P1扩展36个队列；
- 主动纳入中等和较弱Docking校准分子，避免继续只给Top hits补标签；
- 建立空白MM/GBSA与实验activity回填模板，字段包括结构、协议、单位、上下界、重复和QC；
- 质量检查确认60个队列ID唯一、源文件存在、已知内部映射未混入、所有MM/GBSA和实验值保持空白。

## 模型变化

无。没有新增Model v5，没有修改或重新训练Model v0-v4-alpha，没有改变Decision Engine。

## 性能变化

无。本阶段没有产生新的模型性能指标。60个候选是数据获取优先级，不是活性预测、候选成功概率或验证结果。

## 当前限制

- 1,633个HTVS ID当前均无法从`molecules.csv`直接连接SMILES；
- descriptor diversity不是结构/scaffold diversity，必须在源pose导出SDF/SMILES后重新审计；
- MM/GBSA仍是计算标签，不能替代MIC、ATP enzyme或毒性实验；
- 下一轮训练必须等待P0结构QC与同协议MM/GBSA回填通过，pending/failed任务不得当作数值标签。

# Phase 8.1–8.2 — Maestro Structure Recovery and Structure-aware Acquisition

日期：2026-08-25

## 目标

核验用户已提供的Schrödinger原始文件能否直接恢复HTVS结构；在不修改原文件、不训练模型和不生成标签的前提下，建立可追溯结构资产，并用真实Morgan fingerprint与scaffold信息增量升级Phase 8数据获取队列。

## 新增文件

- `src/maestro_structure_extractor.py`
- `src/structure_aware_acquisition.py`
- `data/htvs_structures_v0_1.csv`
- `data/htvs_best_pose_structures_v0_1.sdf`
- `data/templates/phase8_mmgbsa_return_template_v2.csv`
- `results/phase8_data_acquisition/maestro_source_audit.csv`
- `results/phase8_data_acquisition/htvs_pose_structure_audit.csv`
- `results/phase8_data_acquisition/known_structure_validation.csv`
- `results/phase8_data_acquisition/selected_structure_manifest_v0_1.csv`
- `results/phase8_data_acquisition/selected_structures_v0_1.sdf`
- `results/phase8_data_acquisition/p0_structures_v0_1.sdf`
- `results/phase8_data_acquisition/mmgbsa_acquisition_queue_v2.csv`
- `results/phase8_data_acquisition/selected_structures_v0_2.sdf`
- `results/phase8_data_acquisition/p0_structures_v0_2.sdf`
- `results/phase8_data_acquisition/queue_v1_v2_comparison.csv`
- `results/phase8_data_acquisition/structure_extraction_summary.json`
- `results/phase8_data_acquisition/structure_aware_acquisition_summary.json`
- `docs/Phase8_Structure_Extraction_Report.md`
- `docs/Phase8_Structure_Aware_Acquisition_Report.md`

## 修改文件

- `docs/Current_System_Status.md`
- `docs/Data_Registry.md`
- `docs/ATP_Navigator_Development_History.md`：追加本条已完成记录。

## 使用数据

- 3个Schrödinger HTVS Maestro源文件：001 plain Maestro、002 gzip Maestro、003 plain Maestro；输入文件只读，保存各自SHA-256；
- `data/docking_features_v0_2.csv`：4,373个Docking pose身份和计算属性；
- `results/phase8_data_acquisition/htvs_pool_audit.csv`及v1队列：保留Phase 8.1基准与来源追溯；
- `data/model_v3/training_table.csv`中的17个内部候选结构：仅用于结构相似性参照，不使用MM/GBSA标签训练。

## 实现功能

- 通过RDKit Maestro supplier从文件句柄/gzip流解析源文件，绕过Windows中文路径限制；
- 匹配4,372/4,373个pose；唯一失败pose为compound 74371的一条bad stereo bond构象，已保留失败审计；
- 为1,633/1,633个compound生成canonical isomeric SMILES、Murcko scaffold、formula、formal charge及最佳3D pose SDF，共565个scaffold；
- 用Hit13/compound 91074验证内部—HTVS身份桥接，exact isomeric SMILES和connectivity均匹配；
- 为v1 60个候选及P0 24个候选生成可直接交接的SDF；
- 建立v2三个20候选选择臂：exploitation、local structure bridge、scaffold-score exploration；每臂P0 8、P1 12；
- v2 60个候选覆盖57个scaffold，P0 24个覆盖24个scaffold；与v1重叠24个，新增36个；
- 结构相似桥接臂对内部候选的Morgan相似度中位数为0.5702，探索臂为0.1941；
- v2模板的MM/GBSA结果、协议、计算状态和实验字段保持空白；
- 对结构CSV、全库/队列SDF、v2队列和模板重复运行并比较SHA-256，核心输出全部一致。

## 模型变化

无。没有训练、修改或覆盖Model v0-v4-alpha，也没有改变Decision Engine权重或评分逻辑。

## 性能变化

无模型性能变化。本阶段提升的是结构覆盖、队列化学空间设计和计算任务可执行性，不得表述为模型精度提升。

## 当前限制

- 新的MM/GBSA值尚未计算，v2队列不是新监督数据；
- 1个pose的Maestro立体键标记无法由当前RDKit解析，但不影响该compound的最佳有效pose和compound级覆盖；
- Morgan相似性反映二维结构邻近，不等于ATP synthase抑制活性；
- 下一步应先按冻结协议完成P0 24个同协议静态MM/GBSA并回填QC，再决定是否扩展P1；
- MIC、ATP enzyme inhibition、毒性、选择性等真实实验数据仍未产生，不能从已有文件中推导或替代。

# Phase 9 — Researcher-in-the-loop Collaborative Decision Agent

日期：2026-08-26

## 目标

重新审视原始39页Schrödinger研究汇报、项目策划、比赛通知和各项评分标准，确定项目最终选题；检索科学智能体、多参数决策和分子主动学习原始论文；在不重训历史模型、不制造实验标签的前提下，把已有模型与证据转化为研究者协作型候选决策Agent。

## 新增文件

- `src/research_decision_agent.py`
- `run_decision_agent.py`
- `config/decision_agent_v1.json`
- `tests/test_research_decision_agent.py`
- `results/phase9_decision_agent/`全部决策、解释、实验面板和审计产物
- `docs/Phase9_Collaborative_Decision_Agent_Report.md`
- `docs/Phase9_Literature_and_Architecture_Report.md`
- `docs/ATP_Navigator_Project_Strategy_Master_Brief.md`

## 修改文件

- `README.md`
- `data/literature/references.csv`
- `docs/Current_System_Status.md`
- `docs/Model_Registry.md`
- `docs/Data_Registry.md`
- `docs/ATP_Navigator_Development_History.md`

## 使用数据

- Phase 5的17候选四分量和正式综合排名；
- Model v3与Model v4-alpha严格scaffold OOF预测；
- 内部compound/scaffold身份、Hit3历史MD与化学表征状态；
- 原始PPT中Schrödinger/MD/MMGBSA流程和候选历史；
- 比赛通知、赛道评分、虚拟筛选单项奖与代码提交规则；
- 6篇原始方法论文，仅作架构依据，不导入训练数据。

## 实现功能

- 明确最终定位为“虚拟筛选后、湿实验前”的研究者协作型AI候选优先级系统；
- 支持balanced、binding_first、target_mechanism与translational_balance四种意图profile；
- 每个profile进行20,000次受约束Dirichlet权重抽样并计算rank acceptability；
- 增加Pareto front、反事实解释、Model v3/v4-alpha分歧和证据相关性警告；
- 建立预算感知下一实验面板和evidence ledger/agent trace；
- balanced结果的稳健领导者为Hit2；冻结六候选面板为Hit2、Hit1、Hit5、Hit13、Hit3、Hit17；
- 7项单元测试通过，覆盖排名完整性、人工确认、unknown实验状态、面板唯一性、Pareto有效性、模型不变和权重归一化。

## 模型变化

无。Model v0-v4-alpha和Phase 5 Decision Engine均未修改或重训；Phase 9不登记为Model v5。

## 性能变化

无新的真实活性性能指标。Agent产生的是决策稳健性、解释和实验计划；P(Top-k)不是活性概率。实验结果回填前不能宣称命中率、成本或模型准确率提高。

## 当前限制

- 17个候选的监督目标仍为静态MM/GBSA；
- ATP enzyme、MIC和实验毒性全部unknown；
- 权重抽样量化决策偏好，不是预测误差校准；
- 下一步必须冻结并执行同protocol候选面板，之后才可比较Docking、人工、固定权重和Agent策略。

# Git 历史审计

| Commit | 时间 | 可确认变化 |
|---|---|---|
| `b8a2697` | 2026-08-23T13:19:13+08:00 | GitHub 初始 README 和 `.gitignore`；没有项目代码、模型或结果。 |
| `6b78660` | 2026-08-23T13:47:54+08:00 | 一次性导入 118 个 ATP-Navigator 文件，覆盖 Phase 0 数据审计到 Model v2/Phase 4 实验。无法据此拆分早期阶段日期。 |
| `be5d05b` | 2026-08-23T14:27:24+08:00 | 合并 GitHub 初始仓库状态；没有新增 `docs/src/models/results` 文件。 |
| `52f6679` | 2026-08-23T15:05:35+08:00 | 新增团队外部数据上传区、文献记录区和比赛提交目录；不改变已有模型与结果。 |
| `e0a0ce5` | 2026-08-23T16:29:41+08:00 | 新增完整 Model v3 代码、数据表、模型文件、OOF 结果和报告。 |
| `ac06dc4` | 2026-08-23T16:30:39+08:00 | 只调整 Model v3 报告和代码模板中的 Markdown 格式。 |
| `48745bd` | 2026-08-23 | 新增Development History和Model Evolution Table，首次系统整理项目历史。 |
| `61d3b41` | 2026-08-23 | 新增Phase 5 Decision Engine、透明评分配置、综合排序、候选解释和三份长期注册文档。 |
| `c80d3b2` | 2026-08-23 | 追加Phase 5开发历史和模型演化记录。 |
| `2ab74a3` | 2026-08-23 | 新增Phase 6A权重敏感性、排名稳定性、Top-k一致性、决策消融和external benchmark可用性验证。 |
| `a2a1a88` | 2026-08-23 | 追加Phase 6A真实开发历史记录。 |
| `180a97d` | 2026-08-23 | 新增Phase 6B公开ATP数据标准化、Morgan2048、严格评分门控和外部验证empty状态记录。 |

## `docs/src/models/results` 目录变化

| Commit 后状态 | docs | src | models | results | 解释 |
|---|---:|---:|---:|---:|---|
| `b8a2697` | 0 | 0 | 0 | 0 | 只有 GitHub 初始化文件。 |
| `6b78660` | 15 | 21 | 13 | 50 | 早期所有阶段一次性导入。 |
| `be5d05b` | 15 | 21 | 13 | 50 | 合并，不改变四个目录。 |
| `52f6679` | 15 | 21 | 13 | 50 | 只新增 data/competition 协作结构。 |
| `e0a0ce5` | 16 | 22 | 16 | 54 | Model v3 新增 1 份报告、1 个 pipeline、3 个模型版本文件和 4 个结果文件。 |
| `ac06dc4` | 16 | 22 | 16 | 54 | 文件数不变，仅格式修正。 |
| `48745bd` | 18 | 22 | 16 | 54 | 新增2份历史审计文档。 |
| `61d3b41` | 23 | 23 | 16 | 55 | 新增Decision Engine、综合排序及5份Phase 5/维护文档；历史模型目录不变。 |
| `c80d3b2` | 23 | 23 | 16 | 55 | 文件数不变，只更新Phase 5历史记录。 |
| `2ab74a3` | 25 | 24 | 16 | 62 | 新增Phase 6A代码、2份报告和7个结果文件；模型目录不变。 |
| `a2a1a88` | 25 | 24 | 16 | 62 | 文件数不变，只更新Phase 6A历史记录。 |
| `180a97d` | 26 | 25 | 16 | 65 | 新增Phase 6B代码、1份报告和3个结果文件；模型目录不变。 |

## 当前可确认的项目状态

- 数据层：Dataset v0.1、v0.2、v1.0 和 Model v3 派生训练表均存在；
- 模型层：RF、XGBoost、baseline LightGBM、enhanced LightGBM v1.0、Model v2-A/v2-B、Model v3 均有保存产物；
- 评价层：Spearman、RMSE、NDCG@5、Top-k enrichment、hit recovery 均有落盘结果；
- 决策层：透明四分量Final Score、缺失实验unknown标记、Top候选解释和JSON接口已运行；
- 验证层：Phase 6A权重敏感性、Spearman/Kendall稳定性、Top-k一致性和消融已运行；external benchmark接口已建立但当前不可评价；
- 外部验证层：Phase 6B标准化和Morgan计算已完成；现有公开集合因训练重叠和计算证据缺失而保持ranking/metrics empty；
- 可复现性：主要 pipeline、feature list、training config、输入 hash 和 OOF 预测已保存；
- 未完成：真实生物活性验证、完整原始 MD 轨迹、独立前瞻性测试和更大规模的同协议内部 MM/GBSA 标签。

该历史只描述仓库中已经存在的工作，不把实验验证、完整软件平台或真实新药发现写成已完成成果。
