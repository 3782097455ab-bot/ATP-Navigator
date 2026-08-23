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

# Git 历史审计

| Commit | 时间 | 可确认变化 |
|---|---|---|
| `b8a2697` | 2026-08-23T13:19:13+08:00 | GitHub 初始 README 和 `.gitignore`；没有项目代码、模型或结果。 |
| `6b78660` | 2026-08-23T13:47:54+08:00 | 一次性导入 118 个 ATP-Navigator 文件，覆盖 Phase 0 数据审计到 Model v2/Phase 4 实验。无法据此拆分早期阶段日期。 |
| `be5d05b` | 2026-08-23T14:27:24+08:00 | 合并 GitHub 初始仓库状态；没有新增 `docs/src/models/results` 文件。 |
| `52f6679` | 2026-08-23T15:05:35+08:00 | 新增团队外部数据上传区、文献记录区和比赛提交目录；不改变已有模型与结果。 |
| `e0a0ce5` | 2026-08-23T16:29:41+08:00 | 新增完整 Model v3 代码、数据表、模型文件、OOF 结果和报告。 |
| `ac06dc4` | 2026-08-23T16:30:39+08:00 | 只调整 Model v3 报告和代码模板中的 Markdown 格式。 |

## `docs/src/models/results` 目录变化

| Commit 后状态 | docs | src | models | results | 解释 |
|---|---:|---:|---:|---:|---|
| `b8a2697` | 0 | 0 | 0 | 0 | 只有 GitHub 初始化文件。 |
| `6b78660` | 15 | 21 | 13 | 50 | 早期所有阶段一次性导入。 |
| `be5d05b` | 15 | 21 | 13 | 50 | 合并，不改变四个目录。 |
| `52f6679` | 15 | 21 | 13 | 50 | 只新增 data/competition 协作结构。 |
| `e0a0ce5` | 16 | 22 | 16 | 54 | Model v3 新增 1 份报告、1 个 pipeline、3 个模型版本文件和 4 个结果文件。 |
| `ac06dc4` | 16 | 22 | 16 | 54 | 文件数不变，仅格式修正。 |

## 当前可确认的项目状态

- 数据层：Dataset v0.1、v0.2、v1.0 和 Model v3 派生训练表均存在；
- 模型层：RF、XGBoost、baseline LightGBM、enhanced LightGBM v1.0、Model v2-A/v2-B、Model v3 均有保存产物；
- 评价层：Spearman、RMSE、NDCG@5、Top-k enrichment、hit recovery 均有落盘结果；
- 可复现性：主要 pipeline、feature list、training config、输入 hash 和 OOF 预测已保存；
- 未完成：真实生物活性验证、完整原始 MD 轨迹、独立前瞻性测试和更大规模的同协议内部 MM/GBSA 标签。

该历史只描述仓库中已经存在的工作，不把实验验证、完整软件平台或真实新药发现写成已完成成果。
