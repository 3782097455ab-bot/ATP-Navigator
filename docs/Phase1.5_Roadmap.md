# ATP-Navigator Phase 1.5 Roadmap

更新日期：2026-08-22

## 1. 增量升级原则

- 保留 Dataset v0.1、Phase 1 代码、已训练模型、LOOCV 指标和排序结果。
- 新数据通过追加表或新版本字段接入，不覆盖原始 CSV。
- 新 benchmark 与旧 baseline 并行保存，所有指标注明数据版本、标签协议和划分协议。
- 在可核验主键、足够样本和可靠标签具备之前，不进入 GNN、Transformer、Agent 或大模型预测。

## 2. 当前起点

已具备：

- 文件级数据溯源与 SHA-256；
- 分子、筛选记录和 MD 体系主表；
- Docking-only 排序；
- Morgan + RDKit 描述符 + ADMET 聚合特征；
- Random Forest、XGBoost、LightGBM；
- LOOCV 和 scaffold-grouped benchmark；
- Spearman、RMSE、NDCG、Top-k recall/enrichment 和 hit recovery。

当前首要瓶颈不是模型复杂度，而是跨阶段身份映射、计算协议字段和实验标签。

## 3. 信息增量候选

| 信息类型 | 当前状态 | 接入需要的数据 | 预计提升的能力 | 近期动作 |
|---|---|---|---|---|
| Morgan fingerprint | 已用于 17 个候选；全库覆盖仅 18/1,659 | 为 HTVS compound code 提供可验证的完整结构或标准化 SMILES；记录盐、质子化和立体化规则 | 学习局部子结构与排序关系；支持化学相似性和适用域判断 | 建立标准化结构表和结构哈希，保留原始 SMILES 与标准化 SMILES两列 |
| RDKit 分子描述符 | 已使用 10 项；覆盖同 Morgan | 完整 SMILES、RDKit 版本、描述符计算配置 | 提供可解释的全局理化趋势；帮助识别分子量、极性、疏水性等偏差 | 扩展为小规模、预注册的描述符集合，避免在 17 个样本上无约束扩维 |
| ADMET 特征 | 当前仅有 27 个二元端点的总和 | 每个端点独立列、概率或置信度、模型/数据库版本、预测时间、canonical ID 映射 | 从单一能量排序扩展为安全性和成药性多目标排序；解释具体风险来源 | 新建 `admet_features_v0_2.csv`，不覆盖当前聚合记录 |
| 蛋白–配体相互作用特征 | 有 docking/MD 结构和展示图，但无统一数值表 | 每个 pose 的 canonical ID、pose ID、残基接触、氢键、疏水、离子、π相互作用、距离/占有率、靶位点残基定义 | 增加靶点特异性，区分相似 Docking 分数但结合模式不同的分子；提供结构解释 | 从可读 HTVS pose 提取 interaction fingerprint，并先在同一 docking 协议内比较 |
| MD/MMGBSA 特征 | 有两个体系、衍生分析和逐帧数据；原始 XTC 不完整 | 完整轨迹、统一模拟协议、更多候选体系、RMSD/RMSF/接触占有率/MMGBSA 均值与波动、system-to-ligand 映射 | 增加动态稳定性与能量波动证据，作为后段重排和不确定性判断 | 先建立 `md_summary_v0_2.csv`；在候选体系数量足够前只作为规则/证据层，不训练独立 MD 模型 |

## 4. 开发顺序

### Step 1：身份桥接

目标：建立 HTVS compound code、VSW SMILES、Top-1~5、HIT MD、IN-2 和 466 表征样品之间的可审计关系。

建议新增：

- `data/compound_identity_bridge_v0_2.csv`
- 字段：`source_namespace`、`source_id`、`canonical_id`、`mapping_method`、`evidence_file`、`confidence`、`review_status`

进入下一步条件：任何跨阶段 join 都必须能回溯到结构一致性或明确来源记录，不能依据文件名和行顺序。

### Step 2：释放现有计算字段

从已验证 HTVS Maestro 记录中增量提取：

- Glide docking score、gscore、emodel、energy；
- QuickProp 字段；
- pose/variant 标识；
- 计算来源与协议标识。

建议新增：

- `data/docking_features_v0_2.csv`
- `data/quickprop_features_v0_2.csv`

不修改 Dataset v0.1 的 `screening_records.csv`，通过 `canonical_id` 和 `record_id` 关联。

### Step 3：统一标签协议

为所有计算分数增加：

- `score_type`
- `protocol_id`
- `aggregation`
- `unit`
- `pose_or_system_id`
- `software_version`

静态 pose MM/GBSA、MD 帧均值和 ADMET 风险总和必须作为不同标签类型管理。

### Step 4：严格 benchmark v1

保留当前 LOOCV 和 Phase 1.5 scaffold-grouped 结果，继续增加：

1. 按 canonical ID 聚合，杜绝构象跨折；
2. scaffold-grouped 或时间/批次外推划分；
3. bootstrap 指标区间；
4. 固定 Top-k 定义和分数方向；
5. Model 0–3 使用完全相同的候选评价集合；
6. 特征消融：Morgan、描述符、ADMET、Docking、相互作用、MD 逐块加入。

只有完成身份桥接后，Model 0 的 Docking 排序才能与 ML 模型进行公平的 Spearman、NDCG、enrichment 和 hit recovery 比较。

### Step 5：可解释证据融合

继续使用 RF、XGBoost、LightGBM，不增加复杂模型。新增：

- permutation importance；
- SHAP 或树模型贡献分解；
- 单候选证据卡：Docking、结构、ADMET、相互作用、MD/MMGBSA；
- 缺失证据和适用域警告。

输出应解释“候选为何上升或下降”，而不是只给一个黑箱分数。

### Step 6：计算–实验闭环准备

当生物活性验证产生后，新增独立实验标签表，至少记录：

- assay 类型；
- 浓度、单位和终点；
- 生物重复和技术重复；
- 阳性/阴性对照；
- 失败与不可判定结果；
- 样品批次与结构确认状态。

实验标签与计算标签并行保存。只有在样本和对照足够时，才启动真实活性排序模型。

## 5. 阶段交付物

| 里程碑 | 交付物 | 完成判据 |
|---|---|---|
| P1.5-A | 身份桥接表 | 17 个 MM/GBSA 候选与可用 Docking/QuickProp 记录建立可审计映射，或明确标记无法映射 |
| P1.5-B | 计算特征 v0.2 | Docking、QuickProp、ADMET 端点级表具备字段字典和协议字段 |
| P1.5-C | 公平 benchmark | Model 0–3 在同一候选集合、同一标签和同一划分协议下比较 |
| P1.5-D | 特征消融 | 每类新增证据的边际贡献有 OOF 指标和不确定性 |
| P1.5-E | 可解释输出 | 每个候选可追溯到特征、来源文件和排序变化原因 |

## 6. 暂不进入的方向

- GNN、Transformer 或分子大模型微调；
- 多 Agent 自动决策；
- 基于 17 个计算标签宣称真实活性预测；
- 在没有统一主键时拼接 Docking、ADMET、MD 或表征结果；
- 用衍生图片、报告页或帧级数据扩充“独立分子样本数”。

Phase 1.5 的成功标准是：让现有 baseline 更可比、更可信、更可解释，并为下一轮信息增量准备稳定接口，而不是追求模型复杂度。
