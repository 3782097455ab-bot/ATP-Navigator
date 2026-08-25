# ATP-Navigator Data Registry

更新时间：2026-08-26

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
