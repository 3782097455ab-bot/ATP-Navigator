# ATP-Navigator Model v2 Report

## 1. 版本定位

ATP-Navigator Model v2 是对现有 baseline 和 enhanced LightGBM v1.0 的增量升级。旧模型、旧结果和 Dataset v0.2 均未被覆盖。

本版本的目标是检验：外部抗菌与 ATP 合酶抑制知识能否作为辅助先验，增强内部候选的 MM/GBSA 排序。它不预测真实生物活性，也不把计算分数解释为实验活性。

## 2. 数据变化与任务隔离

输入为 `ATP_Navigator_Dataset_v1.csv`（6,754 行）以及内部 Dataset v0.2（17 个身份确认且具有静态 MM/GBSA 标签的化合物）。训练前使用 RDKit 重新生成带手性的 canonical SMILES，并在每个任务内部按 canonical SMILES 去重；同一化合物的重复测量取 log 标签中位数。外部任务与内部 17 个结构无重叠。

| 任务 | 训练定义 | 可用原始记录 | 去重化合物 | 骨架数 | 标签 |
|---|---|---:|---:|---:|---|
| Task A-AB | *A. baumannii* MIC | 2,780 | 738 | 329 | log10(MIC, ug/mL) |
| Task A-E. coli | *E. coli* MIC | 1,200 | 798 | 297 | log10(MIC, ug/mL) |
| Task A-PA | *P. aeruginosa* MIC | 1,196 | 806 | 257 | log10(MIC, ug/mL) |
| Task A-KP | *K. pneumoniae* MIC | 1,178 | 973 | 300 | log10(MIC, ug/mL) |
| Task B-PA 2024 | 同一文献、靶点、assay 和单位的 ATP synthesis IC50 | 17 | 17 | 12 | log10(IC50, ug/mL) |
| Task B-Mtb | ChEMBL 中同一靶点、organism、activity type 和单位的 IC50 | 17 | 17 | 7 | log10(IC50, nM) |
| Task B-AB 2025 | 同一文献、靶点、assay 和单位的 ATP synthesis IC50 | 10 | 10 | 3 | log10(IC50, ng/mL) |
| Task C | 内部候选静态 MM/GBSA 排序 | 17 | 17 | 11 | MM/GBSA，lower-is-better |

Dataset v1.0 中其余 Layer 2 数据没有强行并入 Task B：不同实验终点、单位、靶点或 assay 条件的数据保持隔离。Layer 3 的 docking、MD MM/GBSA 与静态 MM/GBSA 也没有被合并为一个标签。

## 3. 模型结构

### 3.1 保留的对照组

- Model 0：原始 Glide docking score 直接排序，不拟合模型。
- Legacy P1 LightGBM：原有 Morgan1024、RDKit10 与 ADMET_SUM baseline。
- Model 2：原有 Morgan1024、RDKit11、已验证 docking 字段及完整非恒定 QuickProp 字段的 enhanced LightGBM v1.0。

### 3.2 新增模型

- Model v2-A：Morgan fingerprint（radius=2，1,024 bit，包含手性）加 11 个 RDKit 描述符，共 1,035 个结构特征。只在内部 Task C 上训练，是结构-only 消融对照。
- Model v2-B：保留 Model 2 的 1,089 个特征，增加 4 个外部模型预测先验，共 1,093 个特征。四个先验分别来自 *A. baumannii* MIC、PA ATP IC50、Mtb ATP IC50 与 AB ATP IC50 子任务。

外部 MIC/IC50 预测值只作为 Task C 的辅助特征，不作为 Task C 标签，也不与 MM/GBSA 做数值拼接。E. coli、PA 和 KP 的普通 MIC 模型被训练和评估，但由于与内部 AB 靶点任务的直接相关性不足，未加入 v2-B。

## 4. 参数与训练协议

统一使用 LightGBM regression：`n_estimators=160`、`learning_rate=0.03`、`num_leaves=7`、`max_depth=3`、`min_child_samples=2`、`colsample_bytree=0.45`、`reg_alpha=0.1`、`reg_lambda=1.0`、`random_state=42`。本轮不做超参数搜索，避免在小样本上追逐偶然最优值。

外部 Task A/B 使用按 Bemis–Murcko scaffold 分组的 5 折交叉验证；AB 2025 子任务仅有 3 个骨架，因此使用 3 折。内部 Task C 使用 Leave-One-Scaffold-Group-Out，共 11 折。所有指标均基于 out-of-fold 预测计算。

泄漏控制包括：

- 先按 RDKit canonical SMILES 去重，再划分数据；
- 同一 scaffold 不同时进入训练折和验证折；
- 外部数据与内部 17 个结构进行交集检查，本次交集为 0；
- MIC、IC50 和 MM/GBSA 始终属于独立标签空间；
- 外部先验模型不使用 Task C 的 MM/GBSA 标签。

## 5. 训练结果

### 5.1 外部 Task A/B 的 scaffold OOF 结果

| 子任务 | Spearman | RMSE | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---:|---:|---:|---:|---:|
| A-AB MIC | 0.6747 | 0.6077 | 0.9227 | 29.52 | 0.20 |
| A-E. coli MIC | 0.7282 | 0.8304 | 0.8135 | 0.00 | 0.00 |
| A-PA MIC | 0.6652 | 0.7116 | 0.9726 | 96.72 | 0.60 |
| A-KP MIC | 0.6751 | 0.7874 | 0.8535 | 0.00 | 0.00 |
| B-PA ATP IC50 | 0.6385 | 0.4600 | 0.7891 | 2.04 | 0.60 |
| B-Mtb ATP IC50 | 0.6887 | 0.6815 | 0.7965 | 2.04 | 0.60 |
| B-AB ATP IC50 | -0.6930 | 0.2556 | 0.3709 | 0.40 | 0.20 |

外部 RMSE 均处于各自的 log10 标签尺度，不可跨单位直接比较。Top-5 enrichment 以随机命中期望为分母，因此会随任务样本数显著变化，也不宜跨不同规模数据集直接比较。AB ATP IC50 子任务只有 10 个化合物和 3 个骨架，其负 Spearman 表明该先验当前不稳定，不能视为已获得可泛化的 AB ATP 活性模型。

### 5.2 内部 Task C 公平比较

| 模型 | 特征数 | Spearman | RMSE | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---:|---:|---:|---:|---:|---:|
| Model 0 Docking only | 1 | -0.5319 | 40.2317 | 0.2747 | 0.68 | 0.20 |
| Legacy P1 LightGBM | 1,035 | 0.5984 | 6.7001 | 0.7877 | 1.36 | 0.40 |
| Model 2 enhanced v1.0 | 1,089 | 0.7525 | 4.8462 | 0.7774 | 1.36 | 0.40 |
| Model v2-A structure-only | 1,035 | 0.6299 | 6.8280 | **0.8285** | **2.04** | **0.60** |
| Model v2-B external enhanced | 1,093 | **0.7574** | 4.9226 | 0.7744 | 1.36 | 0.40 |

Model v2-B 相比旧 Model 2 的 Spearman 由 0.7525 小幅提高到 0.7574，但 RMSE 从 4.8462 变为 4.9226，NDCG@5 从 0.7774 变为 0.7744，Top-5 enrichment 与 hit recovery 未提升。因此，本轮只能说明外部先验在整体相关性上提供了轻微增量信号，不能证明其改善了头部候选识别。

Model v2-A 的整体相关性和 RMSE 弱于 Model 2，但 NDCG@5、Top-5 enrichment 和 hit recovery 更高。该结果提示结构-only 表征可能对当前头部候选有帮助，不过 17 个样本下单个化合物即可明显改变指标，不能据此宣称稳定优于旧模型。

Docking-only 的 RMSE 是 Glide score 与 MM/GBSA 两种不同量纲数值的直接差，只有形式上的对照意义，不应解释为可校准预测误差。

## 6. 当前结论

Model v2 已实现外部知识与内部排序的标签隔离式连接，并保留了旧模型作为对照。工程目标已完成：可以独立训练 Task A、Task B 和 Task C；可以在无结构重叠条件下生成外部先验；可以用统一的 scaffold OOF 协议比较内部模型。

性能结论较克制：v2-B 尚未改善 Top-k 排序，不能替代 Model 2；v2-A 的 Top-5 表现值得在新增内部标签后复核。目前建议同时保留 Model 2、v2-A 和 v2-B，不选定单一“最终模型”。

## 7. 局限性

- Task C 只有 17 个静态 MM/GBSA 样本和 11 个 scaffold，指标方差很大，尚无独立外部测试集。
- Task B 的三个可比 assay 子集仅有 17、17、10 个化合物；尤其 AB 子任务只有 3 个 scaffold。
- Dataset v1.0 的外部记录仍受原始来源、实验条件和结构标准化质量约束；本版本未把 `label_confidence` 当作真实活性保证。
- 外部普通抗菌活性、跨物种 ATP 抑制与 AB F1Fo-ATP 合酶内部候选之间存在 domain shift。
- 内部目标仍是计算 MM/GBSA 排序，不是 MIC、IC50、抑菌圈或生物学命中标签。
- 当前未进行超参数优化、概率校准、适用域评估或重复 scaffold split 稳健性分析。

## 8. 下一步

1. 优先补充可确认结构与同 assay 条件的 AB ATP synthase inhibitor 数据，特别是具有更多 scaffold 的 IC50 数据。
2. 扩展内部静态 MM/GBSA 样本，并保留相同 docking、QuickProp 和结构字段，重新评估 Top-k 稳健性。
3. 对 scaffold split 做多随机种子或 repeated grouped split，报告均值、标准差和置信区间。
4. 将外部先验逐一消融，尤其验证当前表现不稳定的 AB ATP IC50 先验是否应降权或暂时移除。
5. 获得实验活性后另建独立生物活性任务，绝不回填或改写当前 MM/GBSA 标签。

## 9. 可复现入口

- 只读审计：`.venv/Scripts/python.exe src/model_v2_pipeline.py audit`
- 训练：`.venv/Scripts/python.exe src/model_v2_pipeline.py train`
- 固化结果表：使用 `src/build_model_v2_tables.mjs` 从 `results/model_v2/model_v2_payload.json` 生成 CSV。

训练产物位于 `models/model_v2/`，结果位于 `results/model_v2/`。JSON payload 记录输入文件 SHA-256、软件版本、参数、任务审计、OOF 预测和全部指标。
