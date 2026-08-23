# ATP-Navigator Model v3 Report

版本：Model v3.0  
任务：Feature-enhanced AI ranking model  
标签语义：同协议静态 MM/GBSA 计算排序，lower-is-better；不是实验活性。

## 1. 新增的 AI 能力

Model v3 在保留 Morgan fingerprint、Docking/QuickProp 和 Model v2 外部知识先验的基础上，新增了更完整的 RDKit 分子大小/原子/环/H-bond/LogP/TPSA/可旋转键描述符、面向可追溯直接 ATP assay 参考集的最大 Morgan-Tanimoto 相似性、scaffold 覆盖标志，以及完整覆盖内部 17 个候选的 ADMET endpoint 特征。

化学空间分析使用 55 个去重后的外部直接 ATP assay 参考结构。其 `label_confidence` 仍是来源可追溯但未逐条内部复核，因此相似性是外部知识特征，不是已确认活性标签。

## 2. 相比 Model v2 的变化

Model v3 相比 Model v2 的 OOF 指标变化：Spearman +0.0123，RMSE -0.0349，NDCG@5 +0.0038，Top-5 enrichment -0.00。本轮实际改善项为：Spearman、RMSE、NDCG@5。由于只有 17 个样本，不能把任何小幅变化解释为稳定泛化提升。

## 3. 使用的数据

- 内部 Dataset v0.2：17 个身份确认候选；11 个 Bemis–Murcko scaffold。
- 训练标签：`MMGBSA_dG_Bind_static`，只作监督标签和评价基准。
- Model v2 外部先验：AB whole-cell MIC、PA ATP IC50、Mtb ATP IC50、AB ATP IC50 四个隔离任务的预测值。
- ADMET：17/17 候选具有完整 endpoint 记录。
- Docking 与完整非恒定 QuickProp：17/17 候选覆盖。
- MD interaction/MMGBSA：内部候选仅 1/17 覆盖，未进入训练。

## 4. 模型结构

模型为 LightGBM regression，沿用 Model v2 的固定参数和 `random_state=42`，不做小样本超参数搜索。评价采用 Leave-One-Scaffold-Group-Out，共 11 折；同一 scaffold 不跨训练与测试。

特征组成：

- `morgan_fingerprint`：1024 个特征
- `enhanced_rdkit_descriptors`：16 个特征
- `chemical_similarity`：2 个特征
- `docking`：11 个特征
- `quickprop_complete_nonconstant`：43 个特征
- `admet`：28 个特征
- `external_knowledge_priors`：4 个特征

总特征数：1128。

静态 MM/GBSA 未进入特征；MD/MMGBSA 和 MD interaction 只写入 `binding_feature_table.csv`，不进行均值填充，也不把“是否做过 MD”作为模型信号。

## 5. 严格评价结果

所有模型均在同一 17 个候选上比较；Model v0/v1/v2 读取既有不可变结果，Model v3 使用同类 scaffold-aware OOF 协议。

| 模型 | 特征数 | Spearman | RMSE | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---:|---:|---:|---:|---:|---:|
| Model v0 | 1 | -0.5319 | 40.2317 | 0.2747 | 0.68 | 0.20 |
| Model v1 | 1035 | 0.5984 | 6.7001 | 0.7877 | 1.36 | 0.40 |
| Model v2 | 1093 | 0.7574 | 4.9226 | 0.7744 | 1.36 | 0.40 |
| Model v3 | 1128 | 0.7696 | 4.8877 | 0.7782 | 1.36 | 0.40 |

Docking-only 的 RMSE 是 Glide score 与 MM/GBSA 的跨量纲差，只保留作形式对照，不能解释为校准误差。其余 RMSE 均是静态 MM/GBSA 标签尺度上的 OOF 误差。

`candidate_ranking.csv` 来自在全部 17 个内部样本上重新拟合的最终模型，用于形成当前候选优先级输出；它不参与上表性能计算。上表 Model v3 指标只来自未见当前 scaffold 的 OOF 预测。

## 6. 限制

- 内部标签只有 17 个样本，单个候选即可显著改变 Top-5 指标。
- 没有独立的前瞻性测试集，也没有生物活性标签；本模型只优化计算候选排序。
- 外部 ATP 参考数据来源可追溯但尚未逐条回源复核，相似性和先验存在 domain shift。
- ADMET endpoint 为预测数据，不是本团队实验测量。
- MD 动态证据只覆盖 IN-2 与 Hit3，原始轨迹仍为不完整下载片段；现有接触导出可作案例证据但不可支持通用 MD 特征模型。
- 本轮没有把静态 MM/GBSA作为输入，因此不存在用标签预测标签的直接泄漏；也没有把缺失 MD 特征静默填充。

## 7. 产物与复现

- `src/model_v3_pipeline.py`
- `data/model_v3/chemical_space_analysis.csv`
- `data/model_v3/binding_feature_table.csv`
- `models/model_v3/model.joblib`
- `models/model_v3/training_config.json`
- `models/model_v3/feature_list.json`
- `results/model_v3/model_v3_comparison.csv`
- `results/model_v3/model_v3_oof_predictions.csv`
- `results/model_v3/candidate_ranking.csv`

当前目录布局下运行：`.venv/Scripts/python.exe src/model_v3_pipeline.py train`。如果仓库与 `表征/运行/作图` 不在同一父目录，使用 `--workspace-root` 显式指定资料工作区。
