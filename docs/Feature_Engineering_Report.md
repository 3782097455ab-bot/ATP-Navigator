# ATP-Navigator Feature Engineering v0.2

更新日期：2026-08-22  
定位：为“虚拟筛选后候选排序优化”建立增量特征层；不预测、也不声称预测真实生物活性。

## 1. Phase 1 管线审查

原 `src/feature_pipeline.py` 已实现 Morgan radius=2、1024 bit、手性编码，以及 MW、LogP、TPSA、HBD、HBA、可旋转键、Fraction Csp3、重原子数、总环数和形式电荷。任务指定的七项核心描述符中，唯一缺项是芳香环数；`desc_ring_count` 是总环数，不能替代芳香环数。

原管线可以识别 QuickProp 列，但 Dataset v0.1 的两张输入表并未保存这些列，因此 Phase 1 实际 QuickProp 特征数为 0。原 LightGBM 也不是“纯 Morgan”模型：其历史输入为 Morgan1024 + RDKit10 + ADMET 聚合总分，共 1,035 项。该事实决定 Phase 2 必须把历史结果单列为 `Legacy_P1_LightGBM`，不能把它重新描述成新的 Model 1 消融组。

原管线固定写入 `results/feature_matrix.csv` 等文件。v0.2 使用新文件名，未覆盖这些 Phase 1 输出。

## 2. v0.2 数据覆盖

| 信息块 | 已结构化数量 | 当前用途 | 关键限制 |
|---|---:|---|---|
| 具有来源 SMILES 的分子 | 18 / 1,659 | Morgan、RDKit 描述符 | 其中 17 个有静态 MM/GBSA 标签 |
| HTVS pose/状态记录 | 4,373 | Docking、QuickProp 特征 | 对应 1,633 个 compound code |
| Docking/QuickProp compound | 1,633 | 取最佳 pose 整行并生成组内统计 | 与 17 个 MM/GBSA 候选仅有 1 个 confirmed 桥接 |
| ADMET | 18 行、27 个二元预测端点 | 风险证据或规则特征 | 是预测结果，不是实验毒性标签 |
| 静态 VSW MM/GBSA | 17 个分子 | 当前排序监督标签 | 样本极小，且存在前序筛选选择偏差 |
| MD/MMGBSA | 2 个体系 | 后段证据层 | 不能把帧作为独立分子样本 |

当前两个数据域仍基本不连通：HTVS 域有丰富 Docking/QuickProp 但大多缺少可用 SMILES 和静态 MM/GBSA 映射；17 个候选域有 Morgan、描述符、ADMET、MM/GBSA，但只有 Hit13/code 91074 对应已核验 HTVS pose。1 个共同样本不能形成排序集合，由此 Model 3 暂不能公平训练或评价。

## 3. 分子描述符

`src/feature_pipeline_v2.py` 增量提供以下显式白名单：

- 核心七项：`desc_mol_wt`、`desc_logp`、`desc_tpsa`、`desc_hbd`、`desc_hba`、`desc_rotatable_bonds`、`desc_aromatic_ring_count`；
- 为兼容 Phase 1 保留：`desc_fraction_csp3`、`desc_heavy_atom_count`、`desc_ring_count`、`desc_formal_charge`。

管线直接使用来源 SMILES，不静默中和电荷或改变立体化学。缺失或无法解析的 SMILES 保持缺失，不由名称、分子量或行顺序推断结构。

## 4. Docking 与 QuickProp

`data/docking_features_v0_2.csv` 保留 4,373 条 pose/状态级记录及来源文件，结构化字段包括：

- Glide：docking score、gscore、emodel、energy、evdw、ecoul、einternal、eff-state penalty；
- ligand efficiency：原始、SA 和 LN 三种字段；
- QuickProp：51 个来源字段，包括 MW、PSA/SASA、体积、HBD/HBA、QPlogP、QPlogS、QPlogHERG、Caco-2、MDCK、logBB、logKp、口服吸收、Rule of Five/Three、代谢位点等。

compound 级默认策略不是逐列取最优值，而是选择最低 `glide_docking_score` 对应的完整记录，保证 Glide、emodel、ligand efficiency 和 QuickProp 来自同一个实际状态。同时增加 pose 数、Docking 中位数、标准差和 Top-2 分差。这样避免产生来源中不存在的“拼接构象”。

风险控制：同一 compound code 最多有多条质子化/构象/pose 记录，划分必须按 compound 或更严格的结构主键分组；若目标本身是 Docking score，emodel、gscore 和 ligand efficiency 不能被表述成独立证据。

## 5. ADMET 可用字段

`data/admet_features_v0_2.csv` 保存 27 个二元端点及来源工作簿的端点总和。17 个 VSW/MMGBSA 候选均可通过完全一致的来源 SMILES连接；另有 1 条 ADMET-only 结构，未推断其历史名称。

在 17 个候选中，16 / 27 个端点为常量；存在变化的 11 个端点为 Avian、Biodegradation、Liver Injury I、Liver Injury II、hERG Blockers、NR-ER、NR-TR、Skin Sensitisation、SR-ARE、SR-MMP 和 SR-p53。模型内需在每个训练折移除常量列。

端点总和是 27 个端点的确定性组合。正式消融时应二选一：使用独立端点，或仅使用聚合总分；不能把二者同时当作互相独立的信息增量。ADMET 只作为预测证据，不作为实验安全性真值。

## 6. Morgan 1024 / 2048

v0.2 同时生成 radius=2、启用手性的 1024 bit 和 2048 bit 特征。18 个有 SMILES 的分子统计为：

| 指标 | 1024 bit | 2048 bit |
|---|---:|---:|
| 平均开启位 | 51.56 | 51.94 |
| 平均密度 | 5.03% | 2.54% |
| 平均未折叠环境数 | 52.33 | 52.33 |
| 估计平均折叠碰撞率 | 1.47% | 0.74% |

2048 bit 降低了哈希碰撞，但样本维度翻倍、有效新增信息有限。当前默认实验仍使用 1024 bit 以保持 Phase 1 可比性；2048 bit 只作为使用相同 scaffold-grouped 划分的探索性消融，不能根据同一 17 条数据上的单次最高指标定型。

## 7. v0.2 输出与使用边界

新增输出：

- `data/docking_features_v0_2.csv`
- `data/admet_features_v0_2.csv`
- `results/feature_matrix_v2_morgan1024.csv`
- `results/feature_matrix_v2_morgan2048.csv`
- 对应 coverage、metadata 和 Morgan 比较 JSON

`feature_pipeline_v2.py` 以 `morgan`、`descriptors`、`docking`、`quickprop`、`admet` 五个显式特征块返回白名单。`score_MMGBSA` 只作为当前计算排序标签，任何 `score_*` 标签列均不由动态列扫描自动进入模型。

现阶段正确的能力声明是：建立了可追溯的 AI 排序特征接口，并释放了已有 Docking、QuickProp 和 ADMET 数据；尚未证明新增特征能提高排序性能，也没有建立真实活性模型。
