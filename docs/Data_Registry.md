# ATP-Navigator Data Registry

更新时间：2026-08-23

登记原则：数据可用于训练不等于数据是真实活性。每个训练任务必须按来源、身份、target、organism、activity type、unit和计算/实验协议生成独立视图。

## 数据资产登记表

| 数据名称 | 来源 | 数据规模 | 文件位置 | 主要字段 | 标签类型 | 可用于训练 | 数据限制 |
|---|---|---:|---|---|---|---|---|
| 原始科研资产清单 | 工作区`表征/`、`运行/`、`作图/`只读扫描 | 159文件；2,838,985,130 bytes | `data/raw_manifest.csv` | 文件名、路径、类型、大小、hash、模块、状态 | 无统一标签 | 不能整体直接训练 | complete 11、incomplete 7、corrupted 5、derived 128、unknown 8；含大型和不完整文件 |
| Molecules v0.1 | HTVS/VSW/ADMET/MD及结构文件中可提取身份 | 1,659 records | `data/molecules.csv` | canonical_id、alias、structure_file、SMILES、source、confidence | 无活性标签 | 可作身份连接和结构输入 | 部分记录仅有别名或结构文件；confidence不代表活性 |
| Screening records v0.1 | HTVS、VSW静态MM/GBSA、MD/MMGBSA均值、ADMET | 4,410 records | `data/screening_records.csv` | canonical_id、stage、score、source_file | 多种计算证据 | 仅按stage/protocol拆分后使用 | 同一个score列包含不同计算语义；不能跨协议直接合并 |
| MD systems | IN-2与HIT/Hit3系统 | 2 systems | `data/systems.csv` | system_id、ligand_id、protein、trajectory_status、source | MD系统元数据 | 不可作为通用分子监督集 | 两套XTC均为incomplete；只有两个配体 |
| HTVS Docking/QuickProp v0.2 | 3个当前可读Schrödinger HTVS分片 | 4,373 pose/variant rows；1,633 compound codes | `data/docking_features_v0_2.csv` | Glide、ligand efficiency、QuickProp、source | HTVS计算评分 | 可作Docking代理/排序任务；需按compound分组 | 004–006不完整；pose不能当独立化合物随机划分 |
| ADMET features v0.2 | `作图/.../ADMET.xlsx`预测工作表 | 18 compounds；27 binary endpoints + sum | `data/admet_features_v0_2.csv` | endpoint flags、endpoint_sum、source | 预测ADMET | 可作候选特征 | 不是实验毒性或临床安全性；只有18条 |
| Compound mapping v1 | molecules、systems、VSW、MD、表征和HTVS历史别名 | 1,744 mapping rows excluding header | `data/compound_mapping_v1.csv` | canonical_id、original_name、source、confidence | 身份映射 | 可用于连接；仅confirmed进入严格训练 | probable/unknown不能强制映射；不是标签 |
| Dataset v0.2 | VSW.csv标签与VSW.maegz核验结构/属性 | 17 compounds；11 scaffolds；1,089 Model 2 features | `data/dataset_v0.2/` | identity、source、static MM/GBSA、Morgan、RDKit、Docking、QuickProp | 静态MM/GBSA计算标签 | 是，仅用于同协议计算排序 | 17个已筛选Top candidates；选择偏差；无实验活性 |
| 公开数据库原始输入 | 用户提供`ATP-Navigator公开训练数据库.csv`及说明 | 6,777 rows；2,313 unique source compound IDs | 原始CSV未版本化；hash与审计见`docs/Dataset_Audit_v1.md` | 18个源字段，包括SMILES、target、organism、activity | MIC、IC50、Activity、Inhibition等 | 审计和任务过滤后可使用 | 来源说明未被视为独立质量证明；存在重复、比较符、范围和身份冲突 |
| Dataset v1.0 | 审计后的公开数据 + 内部计算证据 | 6,754 rows；2,329 unique compound IDs | `data/dataset_v1.0/ATP_Navigator_Dataset_v1.csv` | compound、SMILES、target、protein、organism、activity、unit、layer、source、reference、confidence | 分层实验/计算证据 | 是，但必须建立独立task view | Layer1=6,355、Layer2=363、Layer3=36；禁止把MIC/IC50/Docking/MMGBSA合成同一label |
| External knowledge priors | Model v2隔离外部子模型对内部17候选的预测 | 17 compounds × 4 priors | `results/model_v2/external_priors_internal.csv` | AB MIC、PA ATP IC50、Mtb ATP IC50、AB ATP IC50 prior | 模型预测特征 | 可作辅助输入，不可作实验标签 | 跨物种/assay domain shift；AB ATP prior不稳定 |
| Chemical space analysis v3 | 17内部候选与55个去重直接ATP assay参考结构 | 17 analysis rows | `data/model_v3/chemical_space_analysis.csv` | compound、scaffold、similarity、nearest reference、source | 结构相似性，无监督标签 | 可作相似性特征 | 参考来源可追溯但未逐条内部复核；最大相似度0.3014 |
| Binding feature table v3 | Dataset v0.2、systems、MD/MMGBSA和interaction audit | 18 compounds；MD覆盖IN-2与Hit3 | `data/model_v3/binding_feature_table.csv` | Docking、static MMGBSA、MD/MMGBSA summary、contact occupancy | 多种计算证据 | 静态部分可按协议使用；MD当前不进入通用模型 | 内部MD覆盖1/17；IN-2 H-bond源文件含NUL且有corruption flag |
| Model v3 training table | Dataset v0.2 + ADMET + similarity + external priors | 17 rows；1,128 model features + identity/label | `data/model_v3/training_table.csv` | Morgan、RDKit、similarity、Docking、QuickProp、ADMET、priors、label | 静态MM/GBSA计算标签 | 是，仅复现Model v3 | 高维小样本；没有实验标签；不得随机拆同scaffold |
| Phase 5 final ranking | Decision Engine对现有17候选的透明多目标组合 | 17 candidates | `results/final_candidate_ranking.csv` | component scores、final_score、confidence、raw evidence、unknown statuses | 决策规则输出 | 否，不得回流为训练label | 批次相对分数；权重为人工策略；实验均unknown |
| External incoming | 团队未来上传 | 当前0条提交记录 | `data/external/incoming/` | manifest约定来源、引用、许可、状态等 | unknown直到审计 | 否，审计前禁止训练 | 需要来源、许可、结构、单位、重复项和标签语义检查 |
| Literature registry | 团队论文和数据库来源记录 | 当前仅表头 | `data/literature/references.csv` | title、authors、DOI、URL、target、organism、linked dataset、status | 文献元数据 | 不直接训练 | 不保存未授权全文；需人工筛选和复核 |

## 标签使用规则

- Classification：Dataset v1.0不直接提供统一二元标签；阈值必须按特定organism/assay预注册。
- Ranking：内部主任务只使用同协议静态MM/GBSA；Docking是独立baseline。
- Regression：只有精确有限数值、同target/assay/unit且身份去重的任务视图可以回归。
- 禁止混合：MIC、IC50、Ki、Kd、Inhibition%、Docking、静态MM/GBSA、MD/MMGBSA不得作为同一个回归列。
- Phase 5 Final Score：只用于当前候选决策，不是活性真值，也不是新的监督标签。

## 新数据登记规则

每次新增数据必须记录：

1. 数据文件名、版本和SHA-256；
2. 直接来源、reference/DOI、许可和提交人；
3. 记录数、唯一结构数、字段和缺失率；
4. canonical SMILES/InChIKey去重规则；
5. target、organism/strain、assay、activity type和unit；
6. experimental、computational或predicted证据类型；
7. 能否训练以及允许的具体任务；
8. 比较符、范围、重复、冲突、identity和数据泄漏处理；
9. 同步更新本文、Current System Status和Development History。
