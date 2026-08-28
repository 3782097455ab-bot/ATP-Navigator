# ATP-Navigator Current System Status

更新时间：2026-08-28

## Phase 16完成态：可追溯小规模分子扩展

- RDKit围绕IN-2和Hit3各生成200 raw；400 valid、360 unique、40 duplicate rejection、0个HTVS-1633 exact duplicate；
- 360个Generated Registry候选具有完整parent/operation/building-block/attachment/provenance；Hit3的HTVS identity保持unresolved；
- internal diversity=0.5865、74 scaffolds、scaffold retention=0.800、generator collapse=false；
- cheap screening选择120个，冻结`vina_7p3w_v1`真实执行120/120成功并通过pose QC；
- generated acquisition panel=30，评分为Vina+tractability+novelty+diversity+warning+scaffold constraint，不是Vina单目标；
- CReM、REINVENT4、AiZynthFinder均unavailable，未生成模拟结果；未训练或修改历史模型。
- 完整回归测试154/154通过；24个受保护模型文件SHA-256 mismatch=0；Phase 15冻结结果未修改。

主要入口：`results/phase16/generated_candidate_registry.csv`、`results/phase16/generated_acquisition_panel_v1.csv`、`docs/Phase16_Molecule_Expansion_Report.md`。

## Phase 15完成态：预算感知证据获取

- 1633个候选已形成Glide/Vina协议稳健性、五类不确定性、结构空间和证据缺口表；
- 新增random、Vina top、Glide top、consensus top等baseline及5种高级策略和配置化Hybrid；
- 已生成60候选MM/GBSA证据获取面板：15双协议强、15极端分歧、10边界不确定、10结构多样、5中位控制、5历史桥接/可解释；
- budget=10/20/40/60/100均已模拟。Hybrid在相应预算下覆盖10/20/40/60/98个唯一scaffold；
- GNINA状态为unavailable（executable not found），0条shadow score，不阻塞本阶段；
- Research Workspace可只读回答预算、协议冲突和候选删除原因；未训练模型、未修改Decision Engine、未新增实验标签。
- 完整回归测试141/141通过；24个受保护模型文件SHA-256 mismatch=0。

主要入口：`results/phase15/acquisition_panel_v1.csv`、`results/phase15/budget_simulation.csv`、`docs/Phase15_Budget_Aware_Evidence_Acquisition_Report.md`。

## Phase 14.1完成态：HTVS-1633同协议Vina证据层与身份审计

- 冻结`vina_7p3w_v1`已覆盖1633/1633候选终态：1633 success、0 failed、0 running、0 remaining；
- Phase 14原5个`insufficient memory`技术失败经显式授权后，以2并发、完全不改变科学协议的方式只重试这5个，5/5成功；1628个既有结果全部cache hit；
- 1633个成功候选全部通过pose/file QC，形成4899条真实工具证据（vina affinity、docking result bundle、pose QC各1633条）；
- Vina affinity范围-10.553至-5.011 kcal/mol，中位数-8.029；565个Bemis–Murcko scaffold，其中321个singleton，最大scaffold含84个候选；Morgan/Butina结构簇929个；
- Glide/Vina matched subset为1633：Spearman 0.1687、Kendall 0.1127、Top5 overlap 0、Top10 overlap 0；属于协议一致性审计，不是生物活性验证；
- Hit1–Hit17与IN-2的分层身份审计中，仅Hit13为exact canonical；其余17个unresolved。Hit3别名`466`、`ATP-Top1-MD2`等没有可追溯HTVS-1633 ID，不按名称或排名猜测；
- Model v0–v4-alpha共24个受保护文件SHA-256全部不变；未训练模型、未修改Decision Engine、未新增实验标签。

主要入口：`results/phase14/phase14_execution_summary.json`、`results/phase14/full_library_vina_ranking.csv`、`results/phase14_1/internal17_identity_audit.csv`、`docs/internal17_identity_audit.md`。

当前阶段：Multi-Backend Computational Workflow已完成增量实现和小规模软件验证。系统定位：实验前计算证据整合与候选优先级辅助决策。Model v3保持正式监督模型；v0–v4-alpha与既有shadow模型均不重训。

本轮新增三种模式、统一ToolAdapter、持久化DAG、预算分层、进程receipt恢复、按后端/协议/批次隔离证据、会话计算计划/确认/恢复以及进程内API。94项测试通过；原24模型hash不变。Vina在官方1IEP单化合物测试中真实执行成功；该结果不是ATP验证。17内部候选重放历史证据得到6候选，综合分数相对冻结版本最大差异0。Schrödinger已安装于`D:/xuedinge the beginning`，最终产品许可签出未通过；7P3W仍缺历史grid/确认的新协议，因此3候选新商业/开源完整链未完成。详见`Computational_Workflow_Guide.md`与`Tool_Registry.md`。

前次Phase12、Release v1和Windows hash修复已同步GitHub至`c9fce3c`；本轮结果另行提交，不覆盖历史。以下保留2026-08-26检查记录，涉及“未发现安装”等描述只代表当时状态。

补充迭代：Data Release v1已接入并完成两轮隔离shadow实验（用户随后授权的小规模训练，非Phase12重新训练历史模型）。49条ATP观测按6 assay分离，5个assay模型可拟合；原生产模型仍冻结。内部OOF未超过v3，因此不升级生产模型。新知识已接入Research Session只读检索，并产生40个待计算候选队列；与Docking Top40不同14个，尚不能证明该变化更优。69项测试与10项功能核验通过。详见`Data_Release_v1_Integration_and_Experiment_Report.md`。GitHub同步待上传范围确认。

本轮新增共享SQLite计算任务/证据登记、工具与许可探测、协议冻结、预算门控、真实RDKit子进程和恢复入口。17候选完成原冻结决策；1633个HTVS候选完成结构计算和模型调用，但完整决策数0，未强行生成实验面板。Schrödinger未发现，商业计算blocked；不存在新Docking/MMGBSA/QikProp数值。真实实验反馈仍为0。详见`docs/Phase12_Computational_Workspace_Guide.md`及`results/phase12/`。

当前系统定位：面向 ATP synthase 虚拟筛选后实验决策的研究者协作型 AI 候选优先级系统。系统位于 Schrödinger/MD/MMGBSA 与湿实验之间，优化候选取舍和验证资源配置，不替代任何计算或实验环节，也不是通用药物发现平台。

## 1. 当前已有模块

| 模块 | 当前状态 | 主要入口/产物 |
|---|---|---|
| 原始数据审计 | 已完成 v0.1 | `DATA_AUDIT_REPORT.md`、`data/raw_manifest.csv` |
| 化合物身份层 | 已完成初始映射 | `data/molecules.csv`、`data/compound_mapping_v1.csv` |
| 计算证据层 | 已结构化 | `data/screening_records.csv`、`data/docking_features_v0_2.csv`、`data/admet_features_v0_2.csv` |
| 内部训练数据 | Dataset v0.2 | 17 个身份确认候选、11 个 scaffold、静态 MM/GBSA 标签 |
| 外部知识数据 | Dataset v1.0 | 6,754 行三层证据注册表 |
| Baseline | 已保存 | Docking、RF、XGBoost、LightGBM |
| External knowledge model | Model v2 | 分离 MIC/IC50/MMGBSA 任务，以4个预测 prior 连接内部排序 |
| Feature-enhanced ranking | Model v3 | 1,128 特征 LightGBM、11折 scaffold OOF、候选 ranking |
| Target-aware evidence | 案例级可用 | IN-2 与 Hit3 MD interaction/MMGBSA；未进入通用模型 |
| Intelligent Decision Engine | Phase 5 v1.0 已运行 | 透明多目标权重、综合排序、候选解释、JSON接口准备 |
| Robustness validation | Phase 6A v1.0 已运行 | 5套权重方案、排名稳定性、Top-k一致性、决策消融 |
| External benchmark framework | 接口已建立；当前不可评价 | Dataset v1.0外部层重叠检查、独立验证文件规范、无虚构指标 |
| External benchmark import pipeline | Phase 6B v1.0 已运行；当前empty | 标准化、canonical结构去重、Morgan2048、Decision Engine严格评分门控、端点分层metric接口 |
| Dataset v2.0 task router | Phase 7 已运行 | 8,820行按Task A MIC、Task B ATP target、Benchmark严格隔离；Benchmark不训练 |
| External knowledge training experiment | Model v4-alpha 已运行；未替代v3 | Task A MIC模型、4个Task B分层模型、Task C增强排序和Decision Engine shadow ranking |
| Data acquisition intelligence | Phase 8.2 已运行 | 3个Maestro源文件恢复1,633个HTVS结构；Morgan/scaffold重选60个MM/GBSA候选；P0/P1结构包与空白回填模板 |
| Collaborative Decision Agent | Phase 9 v1.0 已运行 | 研究意图profile、20,000次权重抽样、Pareto、反事实解释、模型分歧、实验信息价值和证据追踪 |
| Integrated Decision Workflow | Phase 10 v1.0 已运行 | 标准输入、结构处理、冻结模型门控、四分量决策、研究模式、解释、跨模式稳定性和10项工作流自评 |
| Persistent Research Workspace | Phase 11 已运行 | 会话输入快照、SQLite记录、9个白名单工具、显式确认、恢复、来源检索；离线有限命令模式 |
| Reviewed Feedback Interface | Phase 11 已实现，真实数据empty | 原始证据归档、校验隔离、人工审查、Task A/B/C/CC50分层、冻结排名比较；不自动训练 |
| Public source acquisition | Phase 11 已审计 | abaucin官网补充表：8,404测量行、13,360作者预测行，严格分开；原文数据本地保存、不训练 |
| 团队数据接入 | 目录和登记表已建立 | `data/external/incoming/`、`data/external/curated/` |
| 文献追溯 | 框架已建立 | `data/literature/references.csv` |
| 网页/前端 | 未开发 | 当前不在本阶段范围 |

## 2. 当前模型版本

| 统一版本 | 定义 | 状态 |
|---|---|---|
| Model v0 | Docking-only ranking | 保留、可复现 |
| Model v1 | Legacy P1 LightGBM baseline；Morgan1024 + RDKit10 + ADMET_SUM | 保留、可复现 |
| Model v2 | External knowledge enhanced v2-B；Model 2特征 + 4个外部 prior | 保留、可复现 |
| Model v3 | Structure + similarity + Docking/QuickProp + ADMET + external priors | 当前最新监督排序模型；保留、可复现 |
| Model v4-alpha | Model v3 + Dataset v2.0 Task A/B预测先验 | Phase 7实验版本；真实评估未优于v3，不作为当前正式替代模型 |

Phase 5 Decision Engine 不是新的监督模型，不登记为 Model v4。它读取 Model v3 和已有计算/外部先验，根据 `scoring_config.json` 的人工透明权重形成决策排序。

Phase 6A同样不是Model v4。它不训练模型，只对Phase 5既有四分量执行预设权重扰动、排名相关性、Top-k一致性和消融验证。

Phase 6B不是新模型，也不改变Decision Engine。它导入公开ATP synthase inhibitor记录，完成结构处理后，仅允许已有完整Phase 5计算证据的分子取得原始Decision Engine分数。

Phase 7新增Model v4-alpha实验版本，但正式基线仍保留Model v3。v4-alpha严格分离MIC、ATP target assay和内部静态MM/GBSA标签；其Decision Engine输出仅为shadow ranking，不覆盖Phase 5正式结果。

Phase 8不新增Model v5，也不重新训练任何历史模型。它把现有HTVS候选转化为结构导出与同协议MM/GBSA的数据生产队列，为下一轮扩大内部Task C标签做准备。

Phase 9同样不是Model v5。它将冻结的Model v3/v4-alpha输出、Phase 5四个决策分量、历史Hit3证据和实验预算组织为研究者协作型决策Agent。Agent不生成活性数值；所有ATP enzyme、MIC和实验毒性字段保持unknown。

Phase 10不是Model v5，也没有重新训练任何模型。它把候选CSV、RDKit结构处理、冻结Model v3/Model v2-A降级、外部prior模型、Decision Engine、研究模式、稳健排序、解释和工作流自评串成一次运行流程。完整特征才调用Model v3；证据不足时显式降级，任一必需决策分量缺失时final score保持unknown。

## 3. 当前数据集

| 数据版本/资产 | 规模 | 当前用途 |
|---|---:|---|
| Dataset v0.1 | 1,659 molecule records；4,410 screening records；2 MD systems | 文件、分子和计算证据资产化 |
| Dataset v0.2 | 17 compounds；11 scaffolds；1,089 Model 2 features | 内部静态 MM/GBSA 排序训练与严格评价 |
| Dataset v1.0 | 6,754 rows；2,329 unique compound IDs | 外部抗菌/ATP知识与内部证据的三层注册表 |
| Model v3 chemical space | 17内部候选；55个去重直接ATP assay参考结构 | 相似性和scaffold特征 |
| Model v3 binding table | 18 compounds；MD动态证据覆盖IN-2和Hit3 | 结合证据审计；稀疏MD特征不训练 |
| Phase 5 final ranking | 17 candidates | 多目标决策输出；禁止作为新的活性训练标签 |
| Phase 6A robustness outputs | 17 candidates；5套权重；3套消融 | 验证决策规则对权重和分量选择的敏感性；禁止作为训练标签 |
| Phase 6B standardized external benchmark | 363 input records；109 unique valid structures；Morgan2048 | 外部验证数据准备；109个结构均与Model v2外部知识训练集重叠，不能作为独立训练外验证 |
| Phase 6B ranking/metrics | 0 scored structures；0 ranking rows；0 evaluated strata | 当前明确为empty；不产生虚假分数或验证指标 |
| Dataset v2.0 | 8,820 rows；4,338 canonical structures；Task A 6,663、Task B 77、Benchmark 2,080 | Phase 7分任务外部知识建模；Benchmark完全排除训练 |
| Model v4-alpha Task A | 3,396 structure-species samples；2,263 structures；832 scaffolds | log10 MIC回归；正式A/B high切片Spearman 0.7464、RMSE 0.8015 |
| Model v4-alpha Task B | 76 aggregated samples；7 strata；4 trained strata | 按endpoint、organism、unit独立ATP target ranking；不合并单位 |
| Model v4-alpha Task C | 17 candidates；11 scaffolds；1,134 features | 与Model v3相同scaffold OOF协议比较；未观察到性能提升 |
| Phase 8 HTVS pool | 4,373 poses；1,633 compounds；1,632 eligible | 可追溯source pose的数据获取池；当前0个HTVS ID可直接连接SMILES |
| Phase 8 acquisition queue | 60 candidates；P0 24、P1 36；三选择臂各20 | 待导出结构并补算同协议MM/GBSA；当前标签全部pending |
| Phase 8 return templates | 60个MM/GBSA行；17个内部实验行 | 空白回填接口；禁止用预测填充真实结果 |
| Phase 9 robust decision outputs | 17候选；4个研究意图profile；balanced每个候选20,000次权重评估 | 决策稳健性、Pareto、模型分歧与实验面板；不是训练标签或活性概率 |
| Phase 9 frozen experiment panel | 6候选：Hit2、Hit1、Hit5、Hit13、Hit3、Hit17 | 下一轮同protocol实验建议；当前结果全部unknown |
| Phase 10 processed candidate demo | 17个内部候选；17个Model v3完整输入 | 统一输入、结构和证据表；实验ATP/MIC/毒性全部unknown |
| Phase 10 navigation report | 17候选；4个research profiles；68条profile-candidate比较 | 批次相对决策排序；不作为训练标签或活性概率 |
| Phase 10 workflow validation | 10/10 integrity checks passed；确定性复跑一致 | 验证流程完整性、证据覆盖和模型hash；不评价生物命中率 |

## 4. 当前代码结构

```text
ATP-Navigator/
├─ data/                 数据注册表、版本化数据、外部上传和文献记录
├─ src/                  审计、数据构建、特征、训练、评价和Decision Engine
├─ models/               历史模型与版本化配置
├─ config/               透明Decision Agent配置
├─ configs/              Phase 10研究profile、权重和门控配置
├─ examples/             候选输入模板与一键比赛Demo
├─ tests/                Agent行为与科学边界测试
├─ results/              OOF指标、预测、排序和图表
│  └─ phase6A/           权重敏感性、稳定性、消融和benchmark状态
├─ docs/                 审计、方法、注册表、历史和解释报告
├─ notebooks/            探索性分析入口
├─ competition/          比赛交付整理入口
└─ scoring_config.json   Phase 5公开评分公式与权重
```

关键代码入口：

- `src/feature_pipeline.py`、`src/feature_pipeline_v2.py`
- `src/baseline_train.py`、`src/evaluation.py`
- `src/phase3_ranking.py`
- `src/model_v2_pipeline.py`
- `src/model_v3_pipeline.py`
- `src/decision_engine.py`
- `src/phase6a_robustness.py`
- `src/external_benchmark.py`
- `src/model_v4_alpha_pipeline.py`
- `src/data_acquisition_planner.py`
- `src/maestro_structure_extractor.py`
- `src/structure_aware_acquisition.py`
- `src/data_import_pipeline.py`

## 5. 已完成任务

- 完成原始科研资产只读审计和 SHA-256 manifest；
- 建立 compound ID、别名和结构映射；
- 建立 Dataset v0.1、v0.2、v1.0；
- 完成 RF、XGBoost、LightGBM baseline 和 scaffold-aware benchmark；
- 完成 enhanced ranking v1.0、SHAP解释、Model v2外部知识先验和Model v3增强特征排序；
- 保持 MIC、IC50、Docking、静态 MM/GBSA、MD/MMGBSA 标签隔离；
- 完成 Phase 5 透明多目标评分、缺失实验标记、Top候选解释和JSON接口准备；
- 完成 Phase 6A 默认+A-D权重敏感性、Spearman/Kendall稳定性、Top 3/Top 5一致性和三方案消融；
- 建立只验证不训练的external benchmark接口；确认Dataset v1.0外部Layer 1/2与17候选精确canonical SMILES重叠为0，当前不计算虚假外部指标；
- 完成Phase 6B公开ATP数据标准化、RDKit结构核验、canonical SMILES去重和Morgan2048计算；
- 建立Decision Engine评分门控和独立验证泄漏保护；现有363条Layer 2记录形成109个唯一结构，但可评分结构、ranking和可评价metric均为0，明确记录为empty；
- 完成Dataset v2.0的8,820行独立审计和三任务严格路由，截尾/范围值不静默转数值，2,080条Benchmark记录不用于训练；
- 完成Model v4-alpha：Task A MIC baseline、4个Task B同质分层baseline、Task C外部prior增强排序和不覆盖Phase 5的shadow Decision Engine接入；
- 完成Model v3与v4-alpha同协议比较；v4-alpha未改善内部17候选指标，已作为负结果如实登记；
- 完成Phase 8 HTVS候选池审计：4,373个pose聚合为1,633个compound ID，排除1个已知内部映射，1,632个达到数据获取选择门槛；
- 建立60个候选的MM/GBSA acquisition queue：P0首批24、P1扩展36，exploitation、descriptor diversity、score calibration各20；
- 建立60行MM/GBSA和17行内部生物活性空白回填模板，所有未知结果保持空白；
- 从3个Schrödinger Maestro源文件只读提取4,372/4,373个pose；唯一失败pose已单独审计，其compound仍有有效pose；
- 为全部1,633个HTVS compound建立canonical SMILES、Murcko scaffold与最佳三维pose SDF，共565个唯一scaffold；
- 用Morgan2048和scaffold重建Phase 8.2队列：60个候选覆盖57个scaffold，P0 24个覆盖24个scaffold；与v1重叠24个、新增36个；
- 输出60个v2候选和24个P0的可读SDF，Hit13/91074已知映射的结构与内部结构exact isomeric SMILES及connectivity均匹配；
- 对核心结构表、SDF、v2队列与回填模板完成重复运行hash核验，结果可复现；
- 建立 Development History、Model Registry 和 Data Registry；
- 项目已连接 GitHub，并建立团队新增数据与文献登记入口。

## 6. 未完成任务

- 内部候选 MIC 实验验证；
- 内部候选 ATP enzyme inhibition 实验验证；
- 实验毒性、选择性、溶解度、稳定性和重复性数据；
- 完整的两套原始 MD XTC 轨迹；
- 更多候选的同协议 MD interaction/MMGBSA 特征；
- 更大规模、包含中等和负候选的同协议内部静态 MM/GBSA 数据；
- 独立前瞻性测试集和实验闭环；
- Phase11反馈接口已建立，但真实实验回流、授权重训、模型发布的科学闭环尚未发生；
- 可选LLM意图路由的真实API联调、自然语言意图评测、多人身份认证和用户研究；
- 可与17个内部候选精确对应、且endpoint/unit/assay一致的独立外部benchmark；
- 为独立外部候选补齐按冻结协议生成的Docking、静态MM/GBSA、Model v3输入和预测ADMET等Decision Engine必需证据；
- 先完成P0 24个、再完成P1 36个同协议静态MM/GBSA计算；
- 对公开 Dataset v1.0 逐条回源复核；
- 跨批次可校准的绝对决策分数；
- 网页端、正式服务API和软著交付包。

## 7. 当前系统边界

- Model v3 OOF Spearman 0.7696、RMSE 4.8877、NDCG@5 0.7782、Top-5 enrichment 1.36；只有17个样本，不能视为稳定泛化性能。
- Phase 5 不训练模型，也没有新性能指标。Final Score 是相对当前17候选的决策规则输出，不是活性或成功概率。
- 当前Top候选为 `ATP-SMI-C93E6EC67CDB (Hit2)`，依据是多目标计算证据；MIC、ATP enzyme和实验毒性仍为unknown。
- Model v4-alpha在内部17候选上的Spearman 0.7549、RMSE 4.9268、NDCG@5 0.7774、Top-5 enrichment 1.36、Hit recovery 0.40；对应Model v3为0.7696、4.8877、0.7782、1.36、0.40，因此本轮不能宣称性能提升。
- Task A正式切片Spearman 0.7464、RMSE 0.8015 log10 μg/mL；Task B四个stratum的表现差异大且样本仅8–25个，只能作为small-data baseline。
- Phase 7 shadow Decision Engine Top 1仍为Hit2，但该排序不替代Phase 5，所有内部候选的MIC、ATP enzyme和实验毒性状态仍为unknown。
- Phase 8没有新增性能指标；60个候选只是数据获取队列。Phase 8.2已恢复1,633个结构并完成Morgan/scaffold审计，但尚未产生新的MM/GBSA或实验标签。
- Maestro解析存在1/4,373个pose的异常立体键；该异常已记录，且同一compound有其他有效pose，因此compound级结构覆盖仍为1,633/1,633。
- Phase 6A在default、A、C、D场景中Top 1均为Hit2；ATP权重50%的B场景Top 1变为`ATP-SMI-5B36D3E11A3B (Hit13)`。A-D场景最低两两Spearman为0.4583、最低Kendall tau为0.3235，说明存在明显权重敏感性。
- A-D中只有1个候选始终进入Top 3，也只有1个候选始终进入Top 5；不能宣称Top候选整体高度稳定。
- 当前external benchmark可评价数量为0；该状态是数据可用性审计，不是外部验证通过。
- Phase 6B没有因“有公开activity”就生成评分：现有109个外部唯一结构全部缺少完整Decision Engine证据，且全部与Model v2外部知识训练结构重叠；`benchmark_ranking.csv`只有表头，`benchmark_metrics.csv`状态为`empty`。

## 8. 维护规则

每次重大开发完成后必须同步执行：

1. 更新本文的阶段、模块、模型、数据集和未完成任务；
2. 新模型登记到 `docs/Model_Registry.md`；
3. 新数据登记到 `docs/Data_Registry.md`；
4. 向 `docs/ATP_Navigator_Development_History.md` 追加已完成记录；
5. 保存输入文件hash、配置、OOF/测试结果和限制；
6. 不覆盖历史模型、数据版本和baseline结果；
7. 不把计划、预测值或缺失实验写成已完成成果。

## Phase 17状态更新（2026-08-28）

- 已建立Phase 17无人值守任务schema、atomic checkpoint/cache语义、90候选来源隔离池和8候选资格集合；
- OpenMM 8.6.0与openmmforcefields 0.15.1已在`workspace_local/phase17/deps`非破坏性安装并通过真实导入/平台探测；
- 完整open-MM/GBSA路线仍不可用：OpenFF Toolkit/AmberTools小分子参数化与ParmEd/gmx_MMPBSA分析链缺失；Prime许可不可用且未重复签出；
- 资格门控终态为8 blocked、0 success、0 failed、0数值；30/60候选计算未启动；
- Glide/Vina/open-MMGBSA三协议比较、shadow decision和next20均为not_available；没有用空缺结果生成替代分数；
- Model v0–v4-alpha、Decision Engine、Phase14–16和`vina_7p3w_v1`保持不变，24个模型hash一致；
- 当前新增的不是模型能力或活性证据，而是高成本后端能力审计和科学门控。下一步必须先补齐并审查完整工具链，再从8候选资格验证恢复。

## Phase 13状态更新（2026-08-27）

- 已冻结`vina_7p3w_v1`：历史7P3W e/g受体、VSW精确box、IN-2历史pose和SiteMap证据均有来源hash。
- 已真实完成5候选门控（5/5）和内部17候选Vina docking（17/17），全部parser与pose QC通过；原生pose和日志可追溯。
- 已建立Vina/Glide协议隔离读取、Agent按协议查询、rank disagreement分析和受控暂停/恢复。
- Vina vs历史Glide：Spearman -0.0196、Kendall 0.0000、Top-5 overlap 1/5，仅作方法学比较。
- 24个模型hash不变；未训练模型、未修改Decision Engine、未替换冻结6候选面板。
- Schrödinger四项工具均为installed_but_license_unavailable；商业全流程仍blocked。
- 1633候选未执行，仅生成基于实测时长的计划。开放路线下一关键缺口是经过明确协议和校准的MM/GBSA/ADMET补充，而不是继续堆模型。
- 实验活性状态未改变：MIC、ATP酶抑制和实验毒性仍为unknown。
- 当前完整回归测试：105/105通过（原94项+Phase 13新增11项）。
