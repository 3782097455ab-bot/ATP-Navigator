# ATP-Navigator Data Registry

更新时间：2026-08-28

## Phase 14：HTVS-1633冻结7P3W Vina证据层

| 数据资产 | 来源与规模 | 文件位置 | 证据/标签类型 | 可用于训练 | 限制 |
|---|---|---|---|---|---|
| Full-library Vina ranking | 1633候选；1628真实Vina成功、5明确失败 | `results/phase14/full_library_vina_ranking.csv`、`full_library_qc_summary.json` | `vina_affinity`独立计算证据 | 当前否 | Vina不等于Glide，不是ATP/MIC/毒性实验标签 |
| Phase 14 Evidence Registry export | 1628候选×3记录=4884条 | `results/phase14/evidence_registry_export.csv`、`evidence_registry_summary.csv` | 真实工具输出、docking bundle和pose QC | 否 | 只有成功作业登记数值；5个failed无数值证据 |
| Failure audit | 5候选，均为Vina `insufficient memory` | `results/phase14/failed_candidate_audit.csv/json` | 运行失败与provenance QC | 否 | 技术上可恢复，但本阶段未自动重试 |
| Scaffold/chemical-space audit | 1628成功结构；564 scaffolds；928 clusters | `results/phase14/vina_scaffold_analysis.csv`、`full_library_vina_ranking.csv` | 结构分层与派生rank | 否 | scaffold/cluster不代表活性分类 |
| Glide/Vina disagreement | 1628 matched candidates | `results/phase14/glide_vina_protocol_disagreement.csv`、`glide_vina_protocol_metrics.json` | 协议比较派生值 | 否 | Spearman/Kendall不是实验性能；两协议字段严格隔离 |
| Internal reference mapping | Hit1–Hit17+IN-2共18结构查询；exact match 1 | `results/phase14/internal17_global_position.csv` | 身份映射与全库位置 | 否 | 仅Hit13可确认映射；Hit3/IN-2等保持unknown |

Phase 14没有产生新的监督标签。MIC、ATP activity、细胞毒性、静态MM/GBSA、MD/MMGBSA、Glide和Vina继续按endpoint/protocol/provenance隔离。

## Multi-Backend Workflow证据（2026-08-27）

- 同一个`workspace_local/workspace.sqlite3`新增workflow_run/workflow_node/workflow_job_link及计算—决策—面板—实验关联表；旧候选/证据/会话表继续使用。
- 四个验收项目新增254条登记：49条真实工具输出、85条历史计算证据、120条冻结模型输出。不是254条新实验或训练样本。
- 官方Vina v1.2.7示例的1IEP受体与伊马替尼SDF下载到`workspace_local/official_vina_smoke/`；出处/文件hash见`results/multibackend/validation_a4b4c0a3/official_smoke_sources.json`。仅软件测试，禁止作为ATP靶点验证或训练标签。
- 实际Vina affinity 1条（-12.478 kcal/mol），原生pose/命令/stdout/stderr/receipt在本地artifact/job档案；不是内部7P3W结果。3内部候选只做了允许的结构处理，商业数值未产生。
- 17候选导入85条既有计算证据并重放冻结决策；来源协议不完整，仍标注historical_result，不充作新计算验证。
- 所有新证据保留工具/版本/backend/protocol/run/job/artifact hash；unknown实验字段不补值。实验反馈为empty，无训练数据变更。
- 版本化结果在`results/multibackend/`；工具/许可最新摘要在`results/system_capabilities.json`，历次探测快照保留。没有上传原始大型MD或本地会话数据库。

## Data Release v1增量登记（2026-08-26）

- 原件：`D:/tiaozhansai/ATP_Navigator_Data_Release_v1`；独立副本与审计：`data/external/releases/release_v1_624c8b2309f4/`。
- 18文件清单hash/大小校验通过；106实体结构标识/分子式/MW检查通过。49条直接ATP记录、39结构、6 assay通过本轮机器QC，资格为条件性pilot，不代表本轮逐条重绘验证全部原文结构。
- 其余分区：辅助229、参考46、测量隔离115、bridge隔离120、结构参考28。总587，与原四表总量一致，是质量重建而非587条全新独立实验。
- 全部分区接入共享knowledge_record；source hash、assay、endpoint、organism、unit、DOI隔离。外部测量不能赋为内部候选标签。Research Session已能检索新记录。
- 五篇原文：`data/literature/papers/atp_release_v1/`全文XML/文本；元数据`release_v1_papers*.json`，阅读笔记`Release_v1_Reading_Notes.md`；全文不默认上传Git。
- 两轮实验与化学空间分析：`results/release_v1_shadow_001/`、`release_v1_shadow_replace_atp_002/`。1633候选/39参考检索与预算40队列：`results/release_v1_acquisition/`，仅待计算，不代表已执行或已验证更优。

## Phase 12新增资产（2026-08-26）

| 资产 | 规模/位置 | 来源与边界 |
|---|---|---|
| 计算任务/证据共享库 | `workspace_local/workspace.sqlite3` | 与Phase11 sessions共库；artifact按SHA256存档，本地忽略；CSV仅为导出视图 |
| 真实RDKit计算 | 17内部候选与1633个HTVS候选；`results/phase12/` | 结构质控、Morgan1024、scaffold、描述符；不是新的结合或实验标签 |
| 历史结合与性质证据 | 原17候选、HTVS最佳pose表 | 历史provenance和不完整协议保留；不冒充新算结果 |
| ATP target expansion | 87条：7隔离、80待复核 | Downloads原表只读归档；target annotation和来源审查；当前禁止自动训练 |
| negative SAR | 352条 | endpoint segregation、censoring、论文来源冲突标记；不能把MIC/ETC/细胞毒性合为ATP标签 |
| ATP structure reference | 28条 | 结构知识层，待来源复核；不产生候选结合分数 |
| chemical-space bridge | 120条 | unverified retrieval pool，禁止训练及内部候选实验赋值 |
| 协议与系统能力 | 各运行目录JSON；`results/system_capabilities.json` | 找到7P3W-A.pdb，未找到确认grid；RDKit可执行，Schrödinger未发现 |

原始四表共587条，QC导出在`results/phase12/internal_17_run2/knowledge_qc/`。所有原始文件保持不变。数据问题归类为数据语义一致性、target annotation、endpoint segregation与provenance QC。当前真实实验反馈仍为0。

登记原则：数据可用于训练不等于数据是真实活性。每个训练任务必须按来源、身份、target、organism、activity type、unit和计算/实验协议生成独立视图。

## Phase 11新增资产（2026-08-26）

| 资产 | 规模/位置 | 来源与使用边界 |
|---|---|---|
| 研究会话 | `workspace_local/`；本地忽略 | 用户文本、候选输入快照、确认和工具产物；不是活性数据 |
| 实验回填接口/模板 | `data/templates/phase11_feedback_template.csv`；17行身份、结果空白 | `data/experimental/incoming/`接真实数据；`feedback_store/`保存审核版本，当前真实实验0条 |
| 来源知识卡 | 6张；`data/literature/phase11_knowledge_cards.json` | 原始研究/官方结构数据库，带核验范围；仅检索/方法上下文 |
| Abaucin补充表 | 6张分子表21,764行；测量8,404行/8,281唯一结构，作者预测13,360行 | DOI10.1038/s41589-023-01349-8官网；`data/external/source_cache/abaucin_2023/`；本地保留，不训练、不再分发待许可复核 |
| 公开表审计 | `results/phase11_public_evidence/` | 来源hash、各表规模/重叠、17内部结构相似性；非实验性能 |
| Phase11演示 | `results/phase11_workspace_demo_v1_1/` | 既有17候选；没有新增实验，空反馈评价明确empty；此前初版演示保留 |

实验快照以Task A MIC、Task B ATP_IC50、Task C MMGBSA、CC50分离，进一步按菌株/靶点/单位/模式/协议分层。仅具名人工审查的精确development读数进入潜在训练视图；holdout/benchmark及其重叠结构不能训练。数据具备格式不代表足以训练或证明真实实验；自动训练与模型发布均未启用。

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
| Phase 6A robustness results | Phase 5四分量的固定权重扰动、排名相关、Top-k一致性和消融 | sensitivity 85 rows；ranking 17 rows；stability 25 pairs；consistency 17 rows；ablation 51 rows | `results/phase6A/` | scenario/ablation权重、score、rank、Spearman、Kendall、Top 3/5频率 | 验证派生结果；无新标签 | 否，不得作为训练label | 仅17个内部候选；衡量规则敏感性而非实验准确率 |
| Phase 6A benchmark status | Dataset v1.0外部Layer 1/2与17内部候选精确结构重叠审计 | 3 audit rows；当前0个可评价benchmark | `results/phase6A/benchmark_results.csv`、`benchmark_report.md` | source、外部规模、匹配数、evaluable、status、reason | 数据可用性审计 | 否；未来独立文件只用于验证 | 外部Layer 1/2精确结构重叠为0；相关性为空，不代表验证通过 |
| Phase 6B standardized ATP benchmark | Dataset v1.0 Layer 2公开ATP synthase相关记录，经RDKit标准化和canonical SMILES去重 | 363 source records；363 valid structure records；109 unique structures | `results/phase6B/standardized_benchmark_compounds.csv` | structure ID、来源ID、canonical SMILES、端点集合、reference、Morgan2048、训练重叠、scoring status | 混合MIC/IC50/细胞毒性/其他端点；未合并 | 否；只用于验证准备 | 109/109均与Model v2外部知识训练结构重叠；无完整Decision Engine证据 |
| Phase 6B external ranking | 未改变的Phase 5 Decision Engine对符合条件外部结构的严格评分出口 | 当前0 rows，只有表头 | `results/phase6B/benchmark_ranking.csv` | benchmark rank、compound、activity stratum、ATP-Navigator score、confidence、independence | 决策分数与外部实验记录并列，不形成训练label | 否，只验证 | 当前可评分结构为0；状态empty，不得描述为排名结果已验证 |
| Phase 6B external metrics | 仅对训练不重叠、精确数值、同target/organism/activity type/unit/direction的已评分stratum计算 | 当前1 status row；0 evaluated strata | `results/phase6B/benchmark_metrics.csv` | n、Spearman、Kendall、status、reason | 外部验证metric | 否，只验证 | 当前相关性为空；公开Layer 2参与过Model v2知识训练且外部分子无完整决策证据 |
| Dataset v2.0 原始标准输入 | 用户提供的外部知识标准表；Phase 7 独立执行结构和schema审计 | 8,820 rows；4,341 source compound IDs；4,338 canonical structures | `data/dataset_v2.0/ATP_Navigator_external_dataset_v1.csv` | compound、SMILES、target、organism、activity、unit、reference、source level、confidence、task type | Task A MIC、Task B ATP activity、Benchmark binding records | 是，但只能按任务、端点、物种和单位建立隔离视图 | Task A 6,663、Task B 77、Benchmark 2,080；exact 8,573、censored 239、range 8；43个结构跨task；Benchmark禁止进入本轮训练；来源等级未逐条回源核实 |
| Dataset v2.0 Task A view | Dataset v2.0 Antibacterial 中精确正值 MIC，经 canonical structure×organism species 聚合 | 3,396 structure-species samples；2,263 structures；832 scaffolds | `results/model_v4_alpha/task_a_training_view.csv` | canonical structure、organism、log10 MIC、source/confidence weight、scaffold | log10 MIC μg/mL，lower-is-better | 是，仅Task A | 排除截尾/范围和非MIC；classification阈值未预注册；source A仅82个聚合样本；不是ATP专项标签 |
| Dataset v2.0 Task B view | Dataset v2.0 ATP_target A/B来源的精确正值实验记录 | 76 aggregated samples；7 endpoint-organism-unit strata；4 trained strata | `results/model_v4_alpha/task_b_training_view.csv` | activity type、organism、unit、log10 activity、source/confidence weight、scaffold | 每个stratum独立的ATP target activity | 是，仅同质stratum | 单层只有3–25个样本；4层可训练、3层small-data；不同单位、IC50与百分比禁止合并 |
| Model v4-alpha external priors | Task A与4个Task B子模型对内部17候选的预测 | 17 candidates；1个Task A预测、4个Task B预测和1个rank ensemble | `results/model_v4_alpha/external_priors_internal.csv` | endpoint-specific prediction、within-batch percentile、ensemble rank | 模型预测特征 | 可作Task C辅助输入，不可作实验label | 内部结构与Dataset v2.0 exact overlap为0；跨域预测；不同单位只做批次rank percentile后等权，不合并数值 |
| Model v4-alpha Task C training/output | Model v3训练表 + Dataset v2.0预测先验 | 17 candidates；11 scaffolds；1,134 features | `results/model_v4_alpha/internal_oof_predictions.csv`、`candidate_ranking.csv` | Model v3特征、外部prior、静态MM/GBSA label、OOF prediction | 静态MM/GBSA计算标签 | 是，仅复现v4-alpha实验 | v4-alpha未优于v3；无独立测试和真实活性；不得将Decision Engine分数回流训练 |
| Model v4-alpha Decision shadow ranking | 未改变权重的Phase 5公式接入v4-alpha预测分量 | 17 candidates | `results/model_v4_alpha/decision_engine_candidate_ranking.csv` | 四分量、shadow final score/rank、unknown实验状态 | 决策派生结果 | 否 | 不覆盖Phase 5；分数为当前17候选批次内相对优先级，不是活性或成功概率 |
| Phase 8 HTVS pool audit | `docking_features_v0_2.csv`的4,373个pose按canonical HTVS ID选择最佳pose并连接source file | 1,633 compounds；1,632 eligible；1个已知内部映射被排除 | `results/phase8_data_acquisition/htvs_pool_audit.csv` | compound/pose身份、Docking、QuickProp、source trace、完整性、选择状态 | 无新增标签 | 否；仅用于数据获取规划 | 0/1,633可直接连接SMILES；结构导出前只能做descriptor-space而非Morgan/scaffold多样性 |
| Phase 8 MM/GBSA acquisition queue | HTVS pool中按exploitation、descriptor diversity、score calibration三臂确定性选择 | 60 unique candidates；P0 24、P1 36；每臂20 | `results/phase8_data_acquisition/mmgbsa_acquisition_queue.csv` | source pose、选择臂、wave、Docking/QuickProp、下一动作、pending状态 | 当前无MM/GBSA标签 | 否；真实回填和QC后才可训练 | 是数据生产优先级，不是活性排名；必须先从Schrödinger源pose导出结构，再用冻结同协议MM/GBSA |
| Phase 8 return templates | Phase 8候选队列与当前17内部候选的空白回填接口 | MM/GBSA 60 rows；实验activity 17 rows | `data/templates/phase8_mmgbsa_return_template.csv`、`phase8_experimental_activity_template.csv` | 结构QC、protocol、dG Bind；strain/target/assay/value/bounds/unit/replicate/QC | 全部pending/blank | 否；通过协议和QC门控后按任务接入 | 没有填充预测或假实验值；MM/GBSA、MIC、ATP enzyme和毒性仍须分离 |
| HTVS Maestro structures v0.1 | 3个Schrödinger HTVS Maestro源文件只读解析，并与Docking pose身份严格匹配 | 4,373 docking rows；4,372 parsed poses；1 failed pose；1,633 compound best poses；565 scaffolds | `data/htvs_structures_v0_1.csv`、`data/htvs_best_pose_structures_v0_1.sdf` | canonical SMILES、scaffold、formula、charge、pose identity、source、SHA-256、3D coordinates | 结构与计算输入，不是标签 | 可用于结构特征、相似性、scaffold拆分和后续计算输入 | 1个pose因bad stereo bond无法解析但该compound有其他有效pose；Maestro来源哈希和失败记录已保存；不能据此生成活性标签 |
| Phase 8.1 structure extraction audit | Maestro解析、Docking匹配、已知内部结构桥接和所选结构清单 | 3 source files；4,373 pose audit rows；1 known bridge；60 v1 selected structures | `results/phase8_data_acquisition/maestro_source_audit.csv`、`htvs_pose_structure_audit.csv`、`known_structure_validation.csv`、`selected_structure_manifest_v0_1.csv` | source hash、parse/match status、identity、exact/connectivity validation | QC与追溯，无标签 | 否；用于审计 | Hit13/91074为唯一已知桥接且exact/connectivity均匹配；原始文件未修改 |
| Phase 8.2 structure-aware MM/GBSA queue | HTVS结构表、Morgan2048、Murcko scaffold、Docking/QuickProp与内部17候选结构 | 60 unique candidates；57 scaffolds；P0 24/P1 36；与v1重叠24、新增36 | `results/phase8_data_acquisition/mmgbsa_acquisition_queue_v2.csv`、`selected_structures_v0_2.sdf`、`p0_structures_v0_2.sdf` | exploitation、local structure bridge、scaffold-score exploration、similarity、source pose、wave、priority | 当前无MM/GBSA或实验标签 | 否；真实同协议结果QC后方可进入Task C | 排除唯一内部重叠91074；三个选择臂各20，P0各8；是数据生产计划，不是活性排名 |
| Phase 8.2 MM/GBSA return template | v2结构队列的空白计算回填接口 | 60 rows | `data/templates/phase8_mmgbsa_return_template_v2.csv` | structure file/record、protocol、protein、software、dG Bind、status、date、operator、notes | 全部结果字段blank | 否；QC通过后按冻结协议接入 | 不含预测填充值；必须保存协议、结构和计算状态；pending/failed不得转为数值标签 |
| External incoming | 团队未来上传 | 当前0条提交记录 | `data/external/incoming/` | manifest约定来源、引用、许可、状态等 | unknown直到审计 | 否，审计前禁止训练 | 需要来源、许可、结构、单位、重复项和标签语义检查 |
| Literature registry | 团队论文和数据库来源记录 | 当前仅表头 | `data/literature/references.csv` | title、authors、DOI、URL、target、organism、linked dataset、status | 文献元数据 | 不直接训练 | 不保存未授权全文；需人工筛选和复核 |

## Phase 9 新增派生资产

| 数据名称 | 来源 | 数据规模 | 文件位置 | 标签类型 | 可用于训练 | 限制 |
|---|---|---:|---|---|---|---|
| Agent方法论文登记 | 6篇原始研究论文的出版社/PubMed元数据核验 | 6 records | `data/literature/references.csv` | 文献元数据 | 否 | 仅用于架构依据；未导入分子/活性记录；ChemScreener靶点为WDR5且不是ATP验证 |
| Phase 9稳健排名 | Phase 5四分量与声明权重分布 | 17 candidates × 4 profiles × 20,000 weight draws的汇总 | `results/phase9_decision_agent/robust_rankings.csv` | 决策派生结果 | 否 | P(Top-k)是权重条件频率，不是活性概率 |
| Phase 9 Pareto/反事实/模型分歧 | 17候选现有计算分量与Model v3/v4-alpha OOF | 17 candidate-level records per table | `results/phase9_decision_agent/` | 解释与审计派生值 | 否 | 没有新实验标签；模型分歧不表示任一模型正确 |
| Phase 9冻结实验面板 | 稳健排名、信息价值代理、scaffold多样性、Hit3历史证据 | 6 candidates | `results/phase9_decision_agent/next_experiment_panel.csv` | 实验计划，结果均unknown | 否 | 较低优先候选不是预定义阴性；需同protocol真实实验 |
| Phase 9证据账本与轨迹 | Agent每个输入、规则和输出状态 | 17 evidence rows + 1 JSON trace | `results/phase9_decision_agent/evidence_ledger.csv`、`agent_trace.json` | 数据血缘/运行日志 | 否 | 用于复现和审计，不得回流为监督label |

原Literature registry“当前仅表头”的历史状态由本节取代：截至2026-08-26已登记6篇架构方法论文。

## Phase 10 新增工作流资产

| 数据名称 | 来源 | 数据规模 | 文件位置 | 标签类型 | 可用于训练 | 限制 |
|---|---|---:|---|---|---|---|
| Processed candidate table | Phase 10 demo输入、RDKit、冻结模型工具 | 17 rows；17个Model v3完整输入 | `results/processed_candidate_table.csv`、`results/demo/processed_candidate_table.csv` | 特征与计算预测 | 否，当前为工作流输入/派生表 | `model_score`预测静态MM/GBSA排序；ATP/MIC/毒性均unknown |
| Final navigation report | 四分量Decision Engine与所选profile | 17 candidates | `results/final_navigation_report.csv`、`results/demo/candidate_ranking.csv` | 决策派生分数 | 否 | 批次相对；P(Top-k)不是活性概率；不能回流为label |
| Profile comparison | 同一17候选在4个冻结研究模式下的排序 | 68 rows | `results/phase10_workflow/profile_comparison.csv` | 决策敏感性 | 否 | 模式差异反映研发目标变化，不表示模型失效或活性差异 |
| Profile rank stability | 4×4 profile pair | 16 rows | `results/phase10_workflow/profile_rank_stability.csv` | Spearman/Kendall决策稳定性 | 否 | 不是预测性能；最低非对角Spearman 0.4681 |
| Top candidate consistency | 17 candidates × 4 profiles汇总 | 17 rows | `results/phase10_workflow/top_candidate_consistency.csv` | 跨模式出现频率 | 否 | Top3/Top5次数不是实验命中频率 |
| Workflow validation | 结构、模型、决策、unknown、语义、来源、hash与复跑检查 | Demo 10 checks；10/10 pass | `results/demo/workflow_validation.csv`、`.json` | 工程/科研完整性审计 | 否 | 不评价生物活性准确率或实验成功率 |
| Phase 10 demo input | Dataset v0.2/Model v3已存在的17候选特征重组 | 17 candidates | `results/demo/demo_input.csv` | 演示输入 | 否，不是新数据 | 未新增或修改任何实验/监督标签 |

## 标签使用规则

- Classification：Dataset v1.0不直接提供统一二元标签；阈值必须按特定organism/assay预注册。
- Ranking：内部主任务只使用同协议静态MM/GBSA；Docking是独立baseline。
- Regression：只有精确有限数值、同target/assay/unit且身份去重的任务视图可以回归。
- 禁止混合：MIC、IC50、Ki、Kd、Inhibition%、Docking、静态MM/GBSA、MD/MMGBSA不得作为同一个回归列。
- Phase 5 Final Score：只用于当前候选决策，不是活性真值，也不是新的监督标签。
- Phase 6A scenario/ablation score：只用于稳健性验证，不是新标签，不得回流训练。
- External benchmark：只接受候选级精确结构匹配、实验来源可追溯且endpoint/organism/unit/assay一致的数据；验证集不得进入训练或权重选择。
- Phase 6B：Morgan fingerprint是结构处理产物，不是活性标签；MIC、IC50、细胞毒性、Activity和Inhibition必须分层，训练重叠数据不得报告为独立验证。
- Phase 7：Task A MIC、Task B分层ATP activity与Task C静态MM/GBSA分别建模；Benchmark 2,080条不参与训练；source level/confidence只用于sample weighting；外部预测只能作为prior，不能改写为内部实验标签。
- Phase 8：acquisition queue只决定下一批结构导出和同协议MM/GBSA计算顺序；pending/failed计算不得写为数值；P0审计通过前不启动下一轮训练。
- Phase 13：`vina_7p3w_v1` affinity和pose只属于开放工具链的平行计算证据；不得写入Model v3的Glide字段，不得当作ATP/MIC/毒性实验标签。

## Phase 13新增计算资产

| 数据名称 | 来源 | 数据规模 | 文件位置 | 标签类型 | 可用于训练 | 限制 |
|---|---|---:|---|---|---|---|
| 7P3W Vina冻结协议 | 原PPT、VSW.maegz、ATP.pdb、ATP-Ref.pdb、SIteMap.pdb | 1个协议、3份结构资产 | `configs/projects/ab_atp_synthase/vina_7p3w_v1/` | 计算协议/来源元数据 | 否 | 从历史位点派生但不与Glide等价；受体为历史prepared PDB的Meeko转换 |
| 5候选项目门控 | IN-2、Hit1/2/3/5 | 5/5真实成功 | `results/phase13/validation_5_results.json` | Vina计算证据 | 否 | 不是实验活性；IN-2为reference，不是内部17之一 |
| 内部17候选Vina结果 | 冻结内部结构、`vina_7p3w_v1` | 17 affinity、17 pose、17 pose QC；成功17/失败0 | `results/phase13/internal_17_results.json`、`poses/` | 同协议开放对接证据 | 当前否 | 只能同cohort排序；不得替代Glide/Model v3输入 |
| Phase 13 Evidence Registry导出 | 真实工具、历史冻结证据和冻结决策快照 | 309 records；其中18个Vina affinity | `results/phase13/evidence_registry_export.csv` | 混合来源但逐条协议隔离 | 否 | 309不是实验数据；IN-2加17内部候选共18个Vina数值 |
| Open-toolchain shadow analysis | Vina、历史Glide、静态MM/GBSA、Model v3 rank | 17 candidates | `results/phase13/open_toolchain_shadow_analysis.csv` | 描述性rank comparison | 否 | n=17；不是biological validation，不判断后端真实准确性 |

## 新数据登记规则

## Phase 14.1新增/更新资产

| 数据名称 | 来源 | 数据规模 | 文件位置 | 标签类型 | 可用于训练 | 限制 |
|---|---|---:|---|---|---|---|
| Phase 14.1最终Vina证据 | Phase 14中5个`insufficient memory`技术失败，在冻结`vina_7p3w_v1`下以2并发显式重试 | 1633 success；0 failed；4899 Registry records | `results/phase14/` | 真实计算工具证据 | 当前否 | 不等同Glide，不是生物活性或实验标签；重试前审计保存在`audit/history/` |
| Hit1–Hit17 + IN-2身份审计 | 冻结内部ranking、candidate manifest、HTVS结构表、compound mapping | 18 queries；1 exact canonical；17 unresolved | `results/phase14_1/internal17_identity_audit.csv`、`docs/internal17_identity_audit.md` | identity/provenance QC | 否 | related mapping不得升级为exact；Hit3别名不能证明其属于HTVS-1633 |

## Phase 15新增派生资产

| 数据名称 | 来源 | 数据规模 | 文件位置 | 标签类型 | 可用于训练 | 限制 |
|---|---|---:|---|---|---|---|
| Protocol robustness | 1633个冻结Vina rank与历史Glide rank | 1633 rows | `results/phase15/protocol_robustness.csv` | 计算协议一致性派生值 | 否 | consensus不等于activity |
| Uncertainty decomposition | 协议、目标代理、证据完整性、scaffold/cluster；model uncertainty当前不可用 | 1633 rows | `results/phase15/uncertainty_decomposition.csv` | 决策不确定性派生值 | 否 | model uncertainty为NaN，不填假值 |
| VOI proxy | boundary、disagreement、novelty、missing evidence、relative cost | 1633 rows | `results/phase15/voi_proxy.csv` | acquisition heuristic | 否 | 不是真实经济价值、活性概率或实验label |
| Acquisition panel v1 | 配置化六类选择规则 | 60 unique candidates | `results/phase15/acquisition_panel_v1.csv` | 下一步计算计划 | 否 | 建议获取MM/GBSA证据，不是实验候选有效性声明 |
| Budget simulation | 10种策略×5种预算 | 50 rows | `results/phase15/budget_simulation.csv` | 工程/决策模拟 | 否 | 不输出biological hit rate或expected activity gain |

## Phase 16新增生成资产

| 数据名称 | 来源 | 数据规模 | 文件位置 | 标签类型 | 可用于训练 | 限制 |
|---|---|---:|---|---|---|---|
| Generated Candidate Registry | IN-2/Hit3 + RDKit受控R-group枚举 | 360 unique | `results/phase16/generated_candidate_registry.csv` | 生成结构与provenance | 否 | Hit3 HTVS identity unresolved；chemical validity不等于activity/feasibility |
| Generation QC | 400 raw生成尝试 | 400 rows；40 duplicate rejection | `results/phase16/generation_qc.csv` | QC审计 | 否 | 每条rejection显式记录 |
| Generated chemical space | Morgan/Tanimoto/Murcko对parent与HTVS-1633比较 | 360 rows | `results/phase16/generated_chemical_space.csv` | 结构派生值 | 否 | novelty不等于活性或专利新颖性 |
| Generated Vina evidence | 120个cheap-screened结构，冻结`vina_7p3w_v1` | 120 success | `results/phase16/generated_vina_results.csv` | 真实计算证据 | 否 | 与historical1633隔离；不是实验label |
| Generated acquisition panel | 六分量透明评分 | 30 candidates | `results/phase16/generated_acquisition_panel_v1.csv` | 下一步MM/GBSA计划 | 否 | 不是活性候选声明，不回流训练 |

## Phase 17新增审计资产

| 数据名称 | 来源 | 数据规模 | 文件位置 | 标签类型 | 可用于训练 | 限制 |
|---|---|---:|---|---|---|---|
| Phase 17 candidate pool | Phase15 historical panel + Phase16 generated panel | 90 unique：60 historical + 30 generated | `results/phase17/phase17_candidate_pool.csv` | 计算计划/身份来源 | 否 | generated与HTVS身份严格隔离 |
| High-cost qualification panel | IN-2 + 5个历史类别候选 + 2个生成候选 | 8 candidates | `results/phase17/phase17_high_cost_panel.csv` | 资格验证计划 | 否 | 不表示活性；IN-2不可被替换 |
| Open-MM/GBSA execution audit | 后端能力门控和8个终态任务 | 8 blocked；0 numerical evidence | `results/phase17/open_mmgbsa_results.csv` | 计算执行/QC状态 | 否 | 空DeltaG不得填充；blocked不是实验阴性或计算失败值 |
| Phase 17 downstream placeholders | 三协议、parent-child、shadow decision、next20 schema | 4个not_available + 1个not_generated状态表 | `results/phase17/` | 状态/接口合同 | 否 | 无高成本证据时禁止计算伪相关性或排名变化 |

## Phase 18A界面资产（2026-08-28）

| 数据名称 | 来源 | 规模 | 文件位置 | 标签类型 | 可训练 | 限制 |
|---|---|---:|---|---|---|---|
| Unified candidate view | Phase14 HTVS + Phase16 generated + internal17 | 2010身份记录 | 运行时只读视图 | 无 | 否 | 三种身份域不猜测合并 |
| Unified evidence matrix | 已登记结构/计算/知识/反馈状态 | 2010行 | 运行时只读视图 | 证据状态 | 否 | unknown/missing/not_applicable不等于0 |
| Phase18A UI screenshots | 本地真实应用浏览器验收 | 8张 | `results/phase18a/screenshots/` | 无 | 否 | 展示证据，不是科学结果 |
| Generation request | 用户确认后的任务请求 | 当前0或按使用产生 | `workspace_local/phase18a/requests/` | 工作流状态 | 否 | 不执行计算、不覆盖Phase16 |

## Phase 18B产品与协作资产（2026-08-30）

| 数据名称 | 来源 | 规模 | 文件位置 | 标签类型 | 可训练 | 限制 |
|---|---|---:|---|---|---|---|
| Research sessions and plans | 本地研究者对话、结构化意图与显式确认 | 按使用产生 | `workspace_local/collaboration.sqlite3` | 产品审计状态 | 否 | 不属于科学label；不得作为活性真值 |
| Collaboration records | 评论、投票、最终人类决定和证据快照hash | 按使用产生 | `workspace_local/collaboration.sqlite3` | 人类审查/决定 | 否 | 投票不修改AI分数；最终决定不自动训练 |
| Versioned action artifacts | 经确认的acquisition/generation/export请求 | 按计划版本 | `workspace_local/phase18b/plans/` | 工作流产物 | 否 | acquisition score不是活性概率 |
| Phase18B UI screenshots | 本地真实浏览器验收 | 8张 | `results/phase18b/screenshots/` | 无 | 否 | 仅证明产品流程可见，不是科学结果 |
| Registered pose view | Phase14/16与内部Registry pose的运行时只读视图 | 按可用pose | 不复制原pose | 计算结构证据视图 | 否 | Vina pose不等于实验构象或MM/GBSA trajectory pose |

## Public release与成员数据接入资产（2026-08-30）

| 数据名称 | 来源 | 规模 | 文件位置 | 标签类型 | 可训练 | 限制 |
|---|---|---:|---|---|---|---|
| Member2 GN MIC审计表 | 成员2原始Excel（保持不变） | 310行；310可解析；19唯一结构 | `data/external/integrated/member2_gn_mic_audit.csv` | MIC endpoint记录与QC字段 | 暂否 | 19个结构均与External v2重叠；37个重复行；需endpoint/provenance复核后按任务使用 |
| Member2候选增量表 | 上述审计后排除严格重复/既有严格assay | 273候选增量行 | `data/external/integrated/member2_gn_mic_increment.csv` | MIC候选增量 | 暂否 | 严格来源键与语义键结果不同；不得自动并入统一label |
| External Benchmark Registry v1 | 成员3 Part2已审计Excel | 26 metadata entries | `data/external/integrated/benchmark_registry_v1.csv` | benchmark目录元数据 | 否 | 0条已执行；不是训练记录；Part1实验benchmark为pending |
| Public 3D demonstration asset | Phase14登记Vina rank-1 pose与冻结7P3W e/g受体 | 1 candidate pose + 1 receptor | `data/cloud_demo/` | 真实计算结构展示 | 否 | 只读、hash固定；不是实验构象或MM/GBSA pose |

## Phase 17.1真实高成本证据与后处理资产（2026-08-31）

| 数据名称 | 来源 | 规模 | 文件位置 | 标签类型 | 可训练 | 限制 |
|---|---|---:|---|---|---|---|
| Open MM/GBSA Pilot30 | 冻结`open_mmgbsa_7p3w_v2`真实WSL工具链 | 30/30 success；30 deltaG + 30 uncertainty Registry records | `results/phase17_1/pilot30_results.csv`、共享Evidence Registry | 计算物理证据 | 当前否 | 不是实验结合能、活性标签或历史Prime/MMGBSA等价物 |
| Three-protocol comparison | exact-ID历史Glide、冻结Vina、open MM/GBSA | 30候选；24个三协议exact matched | `results/phase17_1/three_protocol_comparison.csv` | 排名一致性派生值 | 否 | 三种raw value不可当作同一种绝对能量；6个Glide缺失不填充 |
| Protocol disagreement | within-protocol finite-cohort percentile rank | 30候选；24个三协议可计算 | `results/phase17_1/protocol_disagreement.csv` | 计算协议分歧 | 否 | consensus/disagreement不是生物活性或正确性判断 |
| Evidence impact shadow run | 加入open MM/GBSA前后证据完整性与shadow rank | 30候选；24个rank-change可比较 | `results/phase17_1/evidence_impact.csv` | 更新证据影子决策 | 否 | 不覆盖冻结Decision Engine；与internal17无exact ID重叠 |
| Strict post-analysis audit | NaN分类、finite n、相关性和Phase15信息覆盖 | 1 JSON + 1报告 | `results/phase17_1/post_analysis.json`、`docs/Phase17_1_Final_Report.md` | QC/统计审计 | 否 | JSON缺失为null并保留status/reason；未启动60扩展 |

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

## Competition Release Candidate RC1数据资产（2026-08-31）

| 数据名称 | 来源 | 规模 | 文件位置 | 标签类型 | 可训练 | 限制 |
|---|---|---:|---|---|---|---|
| Member data manifest | 三位成员工作簿、说明文件、BindingDB上传文件及仓库archive | 文件/工作表级清单 | `results/release_candidate/member_data_integration/member_data_manifest.csv` | provenance/QC | 否 | row-level eligibility优先；BindingDB上传TSV与ZIP内文件hash完全一致 |
| Member1 ATP literature QC | `Member1_ATP_inhibitor_week1.xlsx` | 39 rows；15个有效结构行；8 unique | `results/release_candidate/member_data_integration/member1_qc.csv` | ATP相关文献线索 | 当前否 | 多数为定性、范围、placeholder结构或待回源记录；0条精确可训练记录 |
| Member2 GN MIC QC | `Member2_GN_antibacterial_week1.xlsx` | 310 rows；19 unique；270行通过row-level shadow eligibility，聚合为266个结构-语境样本 | `results/release_candidate/member_data_integration/member2_qc.csv` | whole-cell MIC | 仅Task-A shadow | 19个结构全部已在External v2；不能解释为ATP合酶活性 |
| Member3 BindingDB Part1 QC | 上传TSV，与仓库ZIP成员byte-identical | 93,712 raw；96,195 endpoint rows；47,190 unique valid structures | `results/release_candidate/member_data_integration/member3_part1_qc.csv` | Ki/IC50/Kd/EC50分层结合记录 | 当前ATP任务否；general external validation | 直接ATP synthase记录0；SERCA、Na/K ATPase及其他ATPase不等于ATP synthase |
| Member3 Part2 benchmark registry | 26条公开benchmark metadata | 26 catalog entries | `results/release_candidate/member_data_integration/benchmark_registry.csv` | metadata/catalog | 否 | 0个benchmark被声称已运行 |
| RC Decision Run | Phase17.1 Glide/Vina/open MM/GBSA版本化后处理 | 30 candidates；24三协议完整 | `results/release_candidate/decision_runs/competition_rc_decision_v1.csv` | 更新证据shadow决策 | 否 | 不覆盖历史Decision；实验ATP/MIC/毒性均unknown |

## IN-2 / 7P3W统一参考工作流资产（2026-09-03）

| 数据名称 | 来源 | 规模 | 文件位置 | 标签类型 | 可训练 | 限制 |
|---|---|---:|---|---|---|---|
| Reconstructed IN-2 libraries | 冻结RDKit scaffold-preserving R-group枚举配置 | 100 / 1,000 / 100,000 unique | `workspace_local/library_generation/`；版本化hash见run manifest | 生成结构与provenance | 否 | 不等于历史2024 Auto_Enum库；大型派生表不上传Git |
| Open physicochemical filter results | 冻结`open_physchem_structural_filter_v1` | 7 / 62 / 7,265 pass | `runs/in2-7p3w-*-reference-v1/filtering/` | 规则/QC派生值 | 否 | RDKit规则不等于QuickProp；warning不等于阴性标签 |
| Development Vina evidence | 冻结`vina_7p3w_v1`真实执行与缓存 | 62/62 success；62 pose-QC pass | `runs/in2-7p3w-development-reference-v1/docking/`、共享Registry | 计算docking证据 | 否 | 不等于Glide或实验活性；55新执行、7缓存复用 |
| Reconstructed-candidate Open MM/GBSA | 冻结`open_mmgbsa_7p3w_v2` | 2/2 success；各50 frames | `runs/in2-7p3w-development-reference-v1/mmgbsa/`、共享Registry | 高成本计算证据 | 否 | 不等于Prime MM/GBSA或实验结合能；省略膜环境 |
| Computational candidate panel | Vina + Open MM/GBSA evidence gate、冻结先验与透明权重 | 2 candidates | `runs/in2-7p3w-development-reference-v1/decision/candidate_panel.csv` | 实验前计算优先级 | 否 | ADMET和实验endpoint unknown；小样本且协议分歧明显 |
