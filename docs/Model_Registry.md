# ATP-Navigator Model Registry

更新时间：2026-08-23

登记原则：每个监督模型版本必须保留目的、特征、标签、训练数据、算法、评价协议、指标、文件和限制。Future model在实际训练并验证前不得预登记为“已完成”。

## Model v0 — Docking Ranking

| 项目 | 登记内容 |
|---|---|
| 目的 | 作为传统虚拟筛选原始评分对照，对候选按Glide docking score排序 |
| 输入特征 | Glide docking score；当前共同17候选比较使用1个字段 |
| 标签定义 | 无训练标签；直接计算排序。评价时与静态MM/GBSA顺序比较 |
| 训练数据 | 不训练；初始HTVS排序覆盖1,633个compound code，后续身份桥接后可在17候选共同集合比较 |
| 算法 | 无拟合；lower-is-better直接排序 |
| 评价协议 | 17候选same-population direct ranking；不是scaffold模型训练 |
| 指标 | Spearman -0.5319；NDCG@5 0.2747；Top-5 enrichment 0.68；Hit recovery 0.20 |
| 模型文件 | 无模型文件；结果见`results/docking_only_ranking.csv`和后续比较表 |
| 限制 | Docking与静态MM/GBSA不同量纲，RMSE 40.2317仅为形式对照；不是实验活性评价 |

## Model v1 — Legacy P1 LightGBM Baseline

| 项目 | 登记内容 |
|---|---|
| 目的 | 检验传统ML能否学习并重排已有静态MM/GBSA候选 |
| 输入特征 | Morgan1024 + RDKit10 + ADMET_SUM，共1,035项 |
| 标签定义 | VSW静态MM/GBSA dG Bind，lower-is-better；计算标签，不是生物活性 |
| 训练数据 | Dataset v0.2中的17个身份确认候选、11个Bemis–Murcko scaffold |
| 算法 | LightGBM regression；历史RF和XGBoost为并行baseline，不属于统一Model v1定义 |
| 评价协议 | scaffold-grouped leave-one-out OOF |
| 指标 | Spearman 0.5984；RMSE 6.7001；NDCG@5 0.7877；Top-5 enrichment 1.36；Hit recovery 0.40 |
| 模型文件 | `models/lightgbm_mmgbsa_baseline.joblib` |
| 主要结果 | `results/baseline_comparison.csv`、`results/phase15_predictions.json` |
| 限制 | 只有17个样本；ADMET只使用预测端点聚合值；无独立测试或实验活性 |

## Model v2 — External Knowledge Enhanced Model

| 项目 | 登记内容 |
|---|---|
| 目的 | 检验外部抗菌和ATP synthase知识能否作为辅助prior增强内部静态MM/GBSA排序 |
| 输入特征 | Model 2的1,089项结构/Docking/QuickProp特征 + 4个外部任务prior，共1,093项 |
| 标签定义 | 内部Task C仍为静态MM/GBSA；外部Task A为分organism MIC；Task B为分assay/organism/unit的ATP IC50。不同标签不合并 |
| 训练数据 | Dataset v1.0外部任务视图 + Dataset v0.2内部17候选；外部结构与内部结构重叠为0 |
| 算法 | 外部任务和内部Task C均使用固定参数LightGBM regression；当前统一Model v2指v2-B |
| 评价协议 | 外部任务scaffold GroupKFold；内部17候选Leave-One-Scaffold-Group-Out |
| 指标 | Spearman 0.7574；RMSE 4.9226；NDCG@5 0.7744；Top-5 enrichment 1.36；Hit recovery 0.40 |
| 模型文件 | `models/model_v2/model_v2_b_external_enhanced.joblib`；外部子模型保存在同目录 |
| 主要结果 | `results/model_v2/internal_model_comparison.csv`、`external_task_metrics.csv`、`external_priors_internal.csv` |
| 限制 | 外部domain shift；AB ATP IC50子任务仅10个化合物/3个scaffold且OOF Spearman为负；Top-k未改善 |

### Model v2保留消融

`Model v2-A` 为Morgan1024 + RDKit11 structure-only消融，共1,035项；其内部指标为Spearman 0.6299、RMSE 6.8280、NDCG@5 0.8285、Top-5 enrichment 2.04、Hit recovery 0.60。17个样本下不能据此认定其稳定优于v2-B。

## Model v3 — Feature-enhanced External Knowledge Ranking

| 项目 | 登记内容 |
|---|---|
| 目的 | 在Model v2外部prior基础上加入增强结构、化学空间相似性和完整ADMET端点，提高候选计算排序能力 |
| 输入特征 | Morgan1024；RDKit16；chemical similarity/scaffold 2；Docking11；QuickProp43；ADMET28；external priors4；总计1,128项 |
| 标签定义 | Dataset v0.2静态MM/GBSA，lower-is-better；静态MM/GBSA没有进入输入特征 |
| 训练数据 | 17个内部候选、11个scaffold；相似性参考为55个去重直接ATP assay结构，与内部canonical SMILES重叠为0 |
| 算法 | 固定参数LightGBM regression；不做小样本超参数搜索 |
| 评价协议 | 11折Leave-One-Scaffold-Group-Out OOF |
| 指标 | Spearman 0.7696；RMSE 4.8877；NDCG@5 0.7782；Top-5 enrichment 1.36；Hit recovery 0.40 |
| 模型文件 | `models/model_v3/model.joblib`；配置与特征见同目录`training_config.json`、`feature_list.json` |
| 主要结果 | `results/model_v3/model_v3_comparison.csv`、`model_v3_oof_predictions.csv`、`candidate_ranking.csv` |
| 限制 | 相比v2仅轻微改善整体相关性；Top-k未改善；Model v1 NDCG@5仍略高；无实验或独立测试集；MD内部覆盖1/17而未入模 |

## 其他保留模型与实验

- Random Forest baseline：`models/random_forest_mmgbsa_baseline.joblib`；
- XGBoost baseline：`models/xgboost_mmgbsa_baseline.joblib`；
- intermediate enhanced ranking v1.0：`models/lightgbm_enhanced_v1.joblib`，1,089特征，Spearman 0.7525；
- Model v2-A structure-only；
- Model v2 Task A/B organism/assay-specific外部子模型；
- Phase 4 LightGBM ranker/LambdaMART和XGBoost ranker实验结果保存在`results/phase4_*`，未被选为统一v0–v3版本。

## Phase 5 Decision Engine（非监督模型）

Decision Engine 不登记为Model v4。它没有训练标签、模型拟合或新性能指标，只根据`scoring_config.json`透明组合Model v3、Docking、静态MM/GBSA、外部prior、相似性、描述符和预测ADMET。当前Final Score不能作为未来训练标签，否则会造成自我循环标签。

## 新模型登记规则

未来只有满足以下条件才能新增版本号：

1. 明确训练目标和标签语义；
2. 训练数据版本固定且有来源hash；
3. canonical SMILES去重并采用scaffold-aware划分；
4. 与v0–v3在相同可比集合和协议下评价；
5. 保存模型、参数、feature list、OOF/独立测试预测和限制；
6. 同步更新本文、Current System Status、Data Registry和Development History。
