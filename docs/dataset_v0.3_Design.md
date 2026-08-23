# ATP-Navigator Dataset v0.3 设计：弱监督排序扩展层

版本：Design 0.3  
更新日期：2026-08-22  
状态：**设计已冻结，数据集尚未物化**  
用途：扩展“虚拟筛选后候选优先级排序”的训练证据；**不是生物活性数据集**。

## 1. 设计结论

Dataset v0.3 不把 Docking、QuickProp 或 MM/GBSA 改称为“真实活性标签”。它将现有计算证据分成两个用途不同的集合：

1. HTVS/Glide 大样本用于低权重弱监督预训练，学习传统筛选产生的相对排序规律；
2. 身份已核验的 17 个 VSW/MM/GBSA 候选继续作为严格的小样本计算排序 benchmark，不与实验活性混同。

当前可读 HTVS 资产并非完整全库：现有 001–003 可读分片已结构化 4,373 条 pose/状态记录、1,633 个 compound code；004–006 是不完整下载文件。因此，v0.3 的“全库版”只有在完整分片恢复并通过 hash/结构计数核验后才能物化。现阶段可以构建的是 readable_shards 试验版，不能把它描述为 HTVS 全库。

## 2. 现有证据与语义边界

### 2.1 Confirmed evidence 的含义

本设计中的 confirmed 只表示**来源、身份或文件链路已核验**，不表示生物活性已确认。

| 证据 | 已核验范围 | 可支持的声明 | 不能支持的声明 |
|---|---:|---|---|
| VSW.csv ↔ VSW.maegz | 17 / 17 个候选，来源 SMILES/compound code/计算记录可对齐 | 17 个候选的身份与静态计算证据可追溯 | 已有真实抑制活性 |
| 可读 HTVS 分片 | 1,633 个 compound code，4,373 条 pose/状态记录 | 这些记录确实存在于当前可读计算输出中 | 已覆盖完整 HTVS 全库；compound code 等于化学结构主键 |
| HTVS ↔ 17 个 MM/GBSA 候选 | 当前可读分片仅 code 91074 可确认桥接 | 该 code 的可读 HTVS 与后段候选记录可追溯 | 其余 16 个候选已在当前 HTVS 分片中找到 |
| NMR/LC-MS 样品 466 | 化学表征文件存在；466 与 Hit3 的映射仍为 probable | 样品 466 有化学表征资产 | 466 已完成生物活性验证；466 可直接作为 Hit3 训练标签 |

### 2.2 Computational evidence

- Glide docking score、gscore、emodel、能量分项和 ligand efficiency；
- 51 个 QuickProp 字段；
- 17 个静态 VSW MM/GBSA dG Bind；
- Hit 与 IN-2 各 1,000 条 MD 构象 MM/GBSA 记录；
- ADMET/QuickProp 等预测输出。

以上均属于计算证据。即使其文件链路已确认，标签语义仍是 computational_ranking_evidence，不是 measured_activity。

## 3. 样本单位

v0.3 同时保留 pose 层和 compound 层，但模型训练默认只使用 compound 层。

### 3.1 Pose 层

每行是一条来源中真实存在的质子化/互变异构/构象/pose 状态：

- compound_code
- variant
- pose_id
- protocol_id
- Glide/QuickProp 原始字段
- source_file
- source_hash

pose 行不被当作独立化合物样本，同一 compound 的所有状态必须进入同一数据划分。

### 3.2 Compound 层

默认选择最低 glide_docking_score 对应的完整 pose 行，同时保存：pose 数、Docking 中位数、标准差和 Top-2 分差。禁止逐列选择“最好值”后拼成来源中不存在的虚拟 pose。

结构身份无法核验时：

- canonical_id 留空；
- compound_code 仅作为 protocol 内部标识；
- Morgan/RDKit 特征留空；
- 不跨文件或跨协议推断同一分子。

## 4. 弱监督标签

### 4.1 标签分层

| evidence_tier | 纳入条件 | weak_label_type | 初始权重 | 用途 |
|---|---|---|---:|---|
| E3_verified_mmgbsa | 17 个身份核验候选，静态 MM/GBSA 可追溯 | static_mmgbsa_rank | 1.00 | 严格 benchmark；嵌套训练折内可用于微调 |
| E2_traceable_htvs | 来自完整、可读分片；compound code 和最佳 pose 可追溯 | within_protocol_docking_rank | 0.35 | 弱监督预训练 |
| E1_partial_or_unknown | 不完整分片、身份冲突、关键字段缺失或文件损坏 | 无 | 0.00 | 隔离区，不训练 |

权重 1.00/0.35 是首轮工程配置，不是科学常数。正式实验必须在训练折内对 0.25/0.35/0.50 做敏感性分析，不能根据同一 17 条测试数据选择权重。

### 4.2 标签计算

对 E2_traceable_htvs：

1. 在同一 protocol_id + shard_id 内，以 compound 最佳 pose 的 Glide docking score 排序；
2. 生成 teacher_percentile，方向统一为数值越大优先级越高；
3. 按预注册分位点生成五级 weak_rank_grade（0–4）；
4. QuickProp 不进入教师标签，只作为输入特征或质量门控，避免模型直接复制由相同字段构造的标签；
5. emodel/gscore/ligand efficiency 与 docking score 高度相关，首版不做加权“多证据真值”。后续若构建 consensus teacher，必须单独做消融。

对 E3_verified_mmgbsa：

1. 仅使用训练折内候选的静态 MM/GBSA 生成相关排序；
2. held-out scaffold 的所有 compound code、结构等价体和 pose 必须从弱监督训练集移除；
3. 17 个候选仍作为计算排序评价集，不称为“阳性/阴性活性样本”。

### 4.3 推荐字段

| 字段 | 含义 |
|---|---|
| dataset_version | 固定为 dataset_v0.3 |
| record_level | pose 或 compound |
| canonical_id | 仅身份确认后填写 |
| compound_code | 来源协议内部编号 |
| variant | 来源状态/构象编号 |
| protocol_id | 评分函数、靶点构象和参数组合标识 |
| query_group | 排序学习的同协议比较组 |
| evidence_tier | E3/E2/E1 |
| identity_confidence | confirmed/probable/unknown |
| weak_label_type | 标签构造方法 |
| teacher_percentile | protocol 内教师排序分位数 |
| weak_rank_grade | 0–4 离散 relevance |
| confidence_weight | 训练样本权重 |
| label_source | 来源文件及字段 |
| label_semantics | 固定说明为计算排序证据 |
| split_group | compound/canonical structure/scaffold 分组键 |
| source_file | 原始文件相对路径 |
| source_hash | 原始文件 SHA-256 |

## 5. 数据泄漏控制

- 禁止 pose 行随机拆分；同一 compound 的全部状态必须同组。
- 结构可用时，优先按 canonical structure/Bemis–Murcko scaffold 划分；结构不可用时至少按 compound code 分组。
- final 17 benchmark 默认冻结为 evaluation-only；如果用于折内微调，必须采用嵌套 scaffold leave-one-group-out。
- 若弱标签由 Docking 构造，模型在该弱标签上的高分只能说明“学会近似 Docking”。只有在独立 MM/GBSA 或未来实验活性上改善，才可声称改善了后段优先级判断。
- 不完整 004–006 分片、.downloading 文件和 probable/unknown 映射不进入训练。
- MD 的 10,000 帧不能当作 10,000 个独立分子样本。

## 6. v0.3 物化门槛

满足以下条件前，文件状态保持 design_only：

1. 恢复 004–006 完整 HTVS 文件并记录 hash；
2. 逐分片核验 Maestro 结构数、compound code 数和可解析率；
3. 明确全库中重复 compound code/variant 的处理；
4. 冻结 protocol_id 和标签分位规则；
5. 建立 held-out 17 候选的去重屏蔽表；
6. 输出 provenance、split audit 和标签分布审计。

现阶段的正确项目表述是：**已完成 Dataset v0.3 弱监督设计与质量门槛，尚未宣称已建立 HTVS 全库训练集。**
