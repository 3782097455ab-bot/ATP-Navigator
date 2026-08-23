# ATP-Navigator Dataset Status Report

版本：External Knowledge Expansion 准备版  
审计对象：`data/dataset_v0.2` 及 Phase 2–4 已有数据资产  
用途：确定可扩展训练边界；不把计算标签解释为真实生物活性

## 1. 当前训练集快照

| 项目 | 当前值 | 说明 |
|---|---:|---|
| 样本数 | 17 | 17 个身份已核验的独立候选化合物 |
| 唯一 InChIKey | 17 | 无同一化合物多构象作为独立训练样本的问题 |
| Bemis–Murcko scaffold | 11 | 最大 scaffold 组含 4 个样本 |
| 数据列总数 | 1,105 | 16 个身份/来源/标签列 + 1,089 个模型特征 |
| 模型特征数 | 1,089 | Morgan 1,024 + RDKit 11 + Docking 11 + QuickProp 43 |
| 标签数 | 1 | `label_score` |
| 标签范围 | -57.51 至 -33.54 | 均值 -47.93；lower-is-better |

标签类型为 `VSW static MMGBSA dG Bind`，来源为 `作图/作图/2-基于衍生数据库的虚拟筛选/数据/VSW.csv`。这是同一项目计算流程产生的候选排序代理标签，不是 IC50、MIC、Ki、Kd，也不是实验命中标签。当前模型任务仍是“学习并优化已有虚拟筛选候选顺序”。

## 2. 当前特征结构

| 特征组 | 已发现 | 实际使用 | 17/17 完整 | 备注 |
|---|---:|---:|---:|---|
| Morgan fingerprint | 1,024 | 1,024 | 1,024 | radius=2、1024 bit、启用手性 |
| RDKit descriptors | 11 | 11 | 11 | MW、LogP、TPSA、HBD/HBA、可旋转键、芳香环等 |
| Docking | 11 | 11 | 11 | Glide score、gscore、emodel、能量项和 ligand efficiency |
| QuickProp | 51 | 43 | 51 | 8 个全局常量字段保留在 manifest，但不进入 Model 2 |

Morgan 位中有 762 位在 17 个样本上为常量。这不是缺失值，而是小样本与稀疏指纹共同造成的低信息维度；训练折内仍应重新做常量过滤，不能用全数据先筛特征。当前特征数与样本数约为 64:1，因此复杂模型和大规模调参都不合适。

## 3. 缺失与不可直接训练字段

### 3.1 当前 17 样本内部

- SMILES、身份、特征来源、标签来源和 `label_score` 均无缺失。
- 1,089 个实际模型特征在当前 17 样本上完整。
- ADMET 没有进入 `dataset_v0.2` 的 Model 2 输入；`data/admet_features_v0_2.csv` 有 18 行、31 列，其中现有审计记录表明 17 个 VSW 候选可匹配。加入前仍需预注册字段、方向和缺失处理，避免把标签选择信息带入模型。

### 3.2 项目层面的关键缺口

- 没有实测 IC50、MIC、Ki、Kd 或其他生物活性标签。
- 没有实验阴性化合物、重复测量、误差范围和完整 assay 条件。
- 没有独立外部测试集；现有性能来自 scaffold-grouped OOF。
- HTVS 001–003 分片可读，004–006 为不完整下载，因此不能把现有 HTVS 文件称为完整全库。
- 外部记录尚未具备统一的单位、关系符号、靶点 ID、物种、协议、许可和检索日期。
- MD/相互作用信息只覆盖少数体系，不能作为 17 个候选的完整训练特征矩阵。

这些缺失不通过默认值或推断填补。未知身份、未知单位、未知协议的数据保留原值与缺失状态，但不进入需要相应语义的训练任务。

## 4. 已有可扩展数据资产

| 资产 | 当前规模 | 可扩展用途 | 当前限制 |
|---|---:|---|---|
| `docking_features_v0_2.csv` | 4,373 个 pose/state；1,633 个 compound code；68 列 | 扩展 docking 排序、pose 聚合和协议内弱监督 | 不是所有 HTVS code 都已和最终候选身份闭环 |
| `admet_features_v0_2.csv` | 18 行；31 列 | ADMET 风险特征、候选优先级的辅助证据 | 预测值，不是实验终点；需按字段方向解释 |
| `dataset_v0.2` | 17 个候选 | ATP 项目微调、最终排序层、严格对照 | 规模小且标签仅为静态 MM/GBSA |
| MD/MMGBSA 派生数据 | 2 个体系；各有接触/能量派生记录 | target-aware 案例特征与机制解释 | 覆盖不足，暂不能形成通用监督矩阵 |
| NMR/LC-MS 表征 | 已有样品表征文件 | 确认化学身份、支持后续计算—实验闭环 | 不等于抑制活性证据 |

## 5. 外部扩展字段

外部数据首批应扩展以下信息：

1. 结构：canonical SMILES、InChIKey、Morgan、RDKit 描述符、结构标准化状态。
2. 活性：activity type、原始值、单位、关系符号、assay 类型和条件；只在可换算时生成 molar/pActivity 派生值。
3. 计算：Docking score、协议/软件、受体构象；Binding energy、方法类型和计算协议。
4. 靶点：target key、target name、Protein ID、organism；后续增加序列/同源性映射。
5. 溯源：数据库、源记录 ID、文献/URL、许可、检索日期。

`data/External_Dataset_Format_v1.csv` 的 10 个核心字段为用户指定的 `compound_id`、`smiles`、`target`、`organism`、`activity_type`、`activity_value`、`docking_score`、`binding_energy`、`source` 和 `reference`。为使数值可解释，模板另加以下字段：

| 扩展字段 | 用途 | 导入规则 |
|---|---|---|
| `target_name` | 人类可读靶点名称 | 可空，但建议填写 |
| `protein_id` | UniProt/PDB/其他明确 Protein ID | 可空；缺失会降低迁移可信度并产生警告 |
| `activity_relation` | `=/< />/<=/>=/~` | 活性值存在时检查；截尾值不生成精确回归标签 |
| `activity_unit` | 活性原始单位 | 活性值存在时必填 |
| `assay_type` | biochemical/cell-based 等 assay 语境 | 建议填写；用于任务分层 |
| `docking_protocol` | 软件、模式、受体构象或协议 ID | docking score 存在但协议缺失时产生警告 |
| `binding_energy_type` | MMGBSA/FEP/experimental dG 等 | binding energy 存在但类型缺失时产生警告 |
| `source_record_id` | 来源数据库的稳定记录 ID | 用于重复检查 |
| `license` | 数据复用许可 | 缺失时产生警告，发布前必须核验 |
| `retrieved_date` | 检索日期 | 使用 `YYYY-MM-DD` |

一行可同时保存多个证据，但导入后会展开成 long-form learning records：活性、Docking 和 binding energy 各自拥有独立 `label_family`、`label_direction` 与 `task_key`。

## 6. 训练边界

当前可以训练的是：同一 VSW/MMGBSA 定义下的内部排序模型，以及外部数据接入后按“活性类型 × 靶点 × 物种 × 协议”分层的任务模型。

当前不能做的是：把 IC50、MIC、Ki、Kd、Docking score 和 MM/GBSA 数值直接纵向拼成一个回归标签；把质量浓度 MIC 在缺少分子量/条件时强行转换为摩尔浓度；把不同 docking/MMGBSA 协议的绝对数值当作同一量纲；将公开实验记录称为 ATP-Navigator 已验证活性。

`External_Dataset_Format_v1.csv` 因此只提供空模板，不预填任何虚构记录。导入管线将保留原始证据，并仅对通过单位、结构和任务兼容性检查的记录生成派生训练表。
