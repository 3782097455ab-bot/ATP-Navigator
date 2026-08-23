# ATP-Navigator Model Upgrade Strategy

版本：v2.0 数据扩展架构  
目标：持续吸收公开药物发现数据，并在不混淆证据语义的前提下优化鲍曼不动杆菌 F1F0-ATP 合酶候选排序

## 1. 三种方案比较

| 方案 | 做法 | 优点 | 主要风险 | 当前定位 |
|---|---|---|---|---|
| A：仅内部数据 | 继续用 17 个 `dataset_v0.2` 候选训练与验证 | 与当前 VSW/MMGBSA 任务最一致；可复现；baseline 清晰 | 样本太少，性能和 SHAP 不稳定，化学空间窄 | 必须永久保留为对照组 |
| B：外部预训练 + ATP 微调 | 先学习公开结构—活性/计算规律，再将外部模型输出作为 ATP 排序的辅助先验，最后只用内部标签完成排序层拟合 | 最符合当前数据规模与比赛叙事；能利用外部信息，同时保留 ATP 靶点与内部协议的决定权 | 域偏移、靶点差异、单位/协议混杂；树模型不能简单照搬“权重微调”概念 | 当前推荐主路线 |
| C：多任务学习 | 对 IC50、MIC、Ki、Kd、Docking、MMGBSA 等设置不同任务头或任务路由，共享结构表征 | 长期可同时利用异质标签，理论上减少错误混合 | 需要更大且任务覆盖均衡的数据；验证与解释复杂；当前比赛周期内收益不确定 | 作为 v2.x 后续研究，不作为当前主线 |

## 2. 推荐：方案 B 的保守实现

比赛阶段采用“B-lite：外部辅助先验 + ATP 内部排序层”，而不是把外部记录直接追加到内部回归表。

1. 外部任务分层：按 `activity_type × target × organism × assay/protocol` 建立可比较记录；Docking/MMGBSA 还需按计算协议分层。
2. 外部模型：使用 Morgan + RDKit 描述符训练传统机器学习模型。实验活性只在单位可换算、关系符号明确时生成 pActivity；MIC 与生化 Ki/Kd/IC50 保持不同任务。
3. 外部先验：对 ATP 候选输出一个带来源说明的 `external_prior_score`。该分数是辅助特征，不是真实活性结论。
4. ATP 微调层：在 `dataset_v0.2` 的现有 Morgan、RDKit、Docking、QuickProp 特征上增量加入外部先验，仍以内部静态 MM/GBSA 排序为目标。
5. 公平评估：Model 0 Docking-only、现有 LightGBM baseline、Model 2 enhanced 与 B-lite 使用相同 17 个样本、相同 scaffold-grouped OOF 和相同指标。旧结果不覆盖。

传统树模型不存在与深度网络完全等价的通用“预训练权重—微调”机制。因此本项目把方案 B 实现为可审计的 stacked/auxiliary-prior 方案：外部模型学习外部任务，内部模型学习 ATP 项目排序，两层标签不直接混合。

## 3. 数据兼容性规则

### 3.1 活性标准化

- 始终保存原始 `activity_value`、`activity_unit` 和 `activity_relation`。
- 对 `M/mM/uM/nM/pM` 且关系为精确值的记录，可生成 `pActivity = -log10(activity in mol/L)`。
- `<`、`>` 等截尾值不当作精确回归标签；可在未来用区间损失或排序约束处理。
- 质量浓度 MIC 不在缺少可靠分子量和 assay 条件时转换为摩尔浓度。
- IC50、MIC、Ki、Kd 分别保留任务类型；不因都能转换为 pActivity 就默认互换。

### 3.2 计算评分标准化

- Docking score 与 binding energy 保留原始方向、软件、协议和受体构象。
- 不跨协议直接比较绝对值；首选协议内 rank/percentile 或 query-level 标准化。
- MM/GBSA 仍属于 computational evidence，不能替代生物活性。

### 3.3 靶点迁移优先级

外部数据按以下顺序进入迁移实验：

1. 鲍曼不动杆菌 F1F0-ATP 合酶同靶点记录；
2. 细菌 ATP 合酶同源靶点，且 Protein ID/序列关系可核验；
3. 更广泛 ATP 合酶或相关复合体，仅作为较低权重辅助先验；
4. 无靶点或靶点不明数据只用于无监督结构空间分析，不进入监督排序。

## 4. 评估设计

- 内部主评估：保持 scaffold-grouped OOF；报告 Spearman、RMSE、NDCG@5、Top-k enrichment 和 hit recovery。
- 外部评估：优先 time/source split；同一 canonical structure 及近重复 scaffold 不跨训练测试。
- 迁移消融：A、A + external prior、A + target-near prior 分开比较，避免把数据量提升误当成靶点知识提升。
- 不以训练集排名、full-fit SHAP 或外部数据上的单一随机切分作为比赛性能结论。
- 在 17 样本上报告折间分布或 bootstrap 区间；没有稳定 Top-k 改善时如实保留 Model 2。

## 5. 决策门槛

方案 B 进入正式比赛模型前至少满足：

- 外部记录有可解析结构、来源、reference、target 和 organism；
- 活性记录有单位与关系符号，计算记录有协议或被标记为协议未知；
- 结构去重与 scaffold 泄漏检查通过；
- 外部任务有足够样本与 scaffold 支持独立验证；
- 在预注册的内部 OOF 评估中，NDCG@5 或 Top-k enrichment 有稳定改善，且整体 Spearman 不出现不可接受退化。

若不满足，方案 A/Model 2 继续作为正式模型；外部扩展只作为架构与数据准备成果展示。

## 6. 实施顺序

1. 使用 `External_Dataset_Format_v1.csv` 收集公开记录，不预先混合标签。
2. 通过 `data_import_pipeline.py` 完成格式、结构、单位、重复和溯源检查。
3. 生成 versioned normalized records、公共结构特征、long-form learning records 和训练就绪性清单。
4. 先训练相互独立的传统机器学习任务 baseline；达到门槛后生成 external prior。
5. 将 prior 作为单一新增特征加入 ATP 内部排序层，和现有 Model 2 公平比较。
6. 数据量与任务覆盖显著扩大后，再评估方案 C；当前不开发 GNN、Transformer 或复杂多任务网络。
