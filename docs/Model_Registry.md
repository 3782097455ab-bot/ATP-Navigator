# ATP-Navigator Model Registry

更新时间：2026-08-28

## Phase 14 Full-library Vina Evidence Layer：无模型变更

- 未训练、替换或微调Model v0–v4-alpha；没有Model v5；
- Phase 13保存的24个受保护模型文件在Phase 14前后SHA-256完全一致（mismatch=0）；
- 1628个Vina affinity只作为`vina_7p3w_v1`独立计算证据，不写入历史Glide feature，不作为实验或监督label；
- 全库rank、percentile、scaffold rank与Glide/Vina disagreement均为派生审计结果，不登记为模型性能提升；
- Decision Engine评分逻辑和历史候选面板未修改。

## Multi-Backend Workflow（2026-08-27）：无模型变更

- Model v3仍是正式监督排序模型；Model v0/v1/v2/v3/v4-alpha及两轮Release v1实验模型不重训、不覆盖。
- 原24模型artifact hash核验不变；冻结Decision Engine评分代码/权重不变。17历史候选重放的综合分数最大差异0。
- Vina输出只进入独立`vina_affinity`证据，不当作Glide score输入旧模型；跨工具、版本、协议、来源批次的数值不混合归一化。
- 新任务图、预算分层与恢复不是新监督模型；没有Model v5或新的活性标签。官方1IEP测试仅证明计算执行，不证明ATP候选预测能力。

## Data Release v1 shadow实验（2026-08-26，未晋升生产）

用户在Phase12后新增授权数据接入与测试。`models/experiments/release_v1_shadow_001/`与`release_v1_shadow_replace_atp_002/`保留两轮独立产物：每轮5个分assay的RF（Morgan1024+16描述符，ATP IC50 pActivity；128树、深度4、leaf2、seed42）及1个内部LightGBM shadow。

外部49记录/39结构/6 assay；2样本任务不拟合。内部仍17样本、原11 scaffold、相同MMGBSA标签和v3超参数。直接叠加10特征：Spearman0.762255、RMSE4.955995、NDCG5 0.774392；替换旧5个ATP相关特征后：0.754902、4.940735、0.777429。两者EF5均1.36、恢复2/5；原v3为0.769608、4.887704、0.778232。没有性能提升证据，未替换Model v0-v4-alpha或Decision Engine。详见对应results目录及接入报告。

局限：极小样本、单论文内scaffold验证、化学空间距离、源结构重建仍需最终人工核查；内部没有新的实验活性标签。不能将shadow命名为已验证正式Model v5。

## Phase 12维护记录（非新模型）

真实RDKit计算和共享Evidence Registry接入冻结Model v3/明确的v2-A fallback及原四分量决策；没有训练、修改权重或替换历史模型。24个models文件SHA256保持不变。新增启发式acquisition planner不登记为监督模型，其输出不是生物活性概率或实测成本节约。商业adapter因本机工具/协议缺失未完成真实环境验证。17候选原排名复核及1633候选缺失门控见`results/phase12/`；未产生新的生物学性能指标。

## Phase 11维护记录（非新模型）

Model v0–v4-alpha所有历史模型保持不变。17候选工作区演示核验models目录24个文件hash全部一致，无训练。新增可选LLM路由适配器仅用于提议工作区工具，尚未配置key/模型及真实调用，不能登记为已验证的预测模型。输入工程v1.1增加字段保护、身份检查和跨进程确定性；没有改权重或模型参数。没有新增药效性能、实验成功率或成本节约指标。

登记原则：每个监督模型版本必须保留目的、特征、标签、训练数据、算法、评价协议、指标、文件和限制。Future model在实际训练并验证前不得预登记为“已完成”。

## Model v0 — Docking Ranking

| 项目 | 登记内容 |
|---|---|
| 目的 | 作为传统虚拟筛选原始评分对照，对候选按Glide docking score排序 |
| 输入特征 | Glide docking score；当前共同17候选比较使用1个字段 |
| 标签定义 | 无训练标签；直接计算排序。评价时与静态MM/GBSA顺序比较 |
| 训练数据 | 不训练；初始HTVS排序覆盖1,633个compound code，后续身份桥接后可在17候选共同集合比较 |
| 算法 | 无拟合；lower-is-better直接排序 |
| 评价协议 | 17候选same-population direct ranking；不是scaffold模型训练 |
| 指标 | Spearman -0.5319；NDCG@5 0.2747；Top-5 enrichment 0.68；Hit recovery 0.20 |
| 模型文件 | 无模型文件；结果见`results/docking_only_ranking.csv`和后续比较表 |
| 限制 | Docking与静态MM/GBSA不同量纲，RMSE 40.2317仅为形式对照；不是实验活性评价 |

## Model v1 — Legacy P1 LightGBM Baseline

| 项目 | 登记内容 |
|---|---|
| 目的 | 检验传统ML能否学习并重排已有静态MM/GBSA候选 |
| 输入特征 | Morgan1024 + RDKit10 + ADMET_SUM，共1,035项 |
| 标签定义 | VSW静态MM/GBSA dG Bind，lower-is-better；计算标签，不是生物活性 |
| 训练数据 | Dataset v0.2中的17个身份确认候选、11个Bemis–Murcko scaffold |
| 算法 | LightGBM regression；历史RF和XGBoost为并行baseline，不属于统一Model v1定义 |
| 评价协议 | scaffold-grouped leave-one-out OOF |
| 指标 | Spearman 0.5984；RMSE 6.7001；NDCG@5 0.7877；Top-5 enrichment 1.36；Hit recovery 0.40 |
| 模型文件 | `models/lightgbm_mmgbsa_baseline.joblib` |
| 主要结果 | `results/baseline_comparison.csv`、`results/phase15_predictions.json` |
| 限制 | 只有17个样本；ADMET只使用预测端点聚合值；无独立测试或实验活性 |

## Model v2 — External Knowledge Enhanced Model

| 项目 | 登记内容 |
|---|---|
| 目的 | 检验外部抗菌和ATP synthase知识能否作为辅助prior增强内部静态MM/GBSA排序 |
| 输入特征 | Model 2的1,089项结构/Docking/QuickProp特征 + 4个外部任务prior，共1,093项 |
| 标签定义 | 内部Task C仍为静态MM/GBSA；外部Task A为分organism MIC；Task B为分assay/organism/unit的ATP IC50。不同标签不合并 |
| 训练数据 | Dataset v1.0外部任务视图 + Dataset v0.2内部17候选；外部结构与内部结构重叠为0 |
| 算法 | 外部任务和内部Task C均使用固定参数LightGBM regression；当前统一Model v2指v2-B |
| 评价协议 | 外部任务scaffold GroupKFold；内部17候选Leave-One-Scaffold-Group-Out |
| 指标 | Spearman 0.7574；RMSE 4.9226；NDCG@5 0.7744；Top-5 enrichment 1.36；Hit recovery 0.40 |
| 模型文件 | `models/model_v2/model_v2_b_external_enhanced.joblib`；外部子模型保存在同目录 |
| 主要结果 | `results/model_v2/internal_model_comparison.csv`、`external_task_metrics.csv`、`external_priors_internal.csv` |
| 限制 | 外部domain shift；AB ATP IC50子任务仅10个化合物/3个scaffold且OOF Spearman为负；Top-k未改善 |

### Model v2保留消融

`Model v2-A` 为Morgan1024 + RDKit11 structure-only消融，共1,035项；其内部指标为Spearman 0.6299、RMSE 6.8280、NDCG@5 0.8285、Top-5 enrichment 2.04、Hit recovery 0.60。17个样本下不能据此认定其稳定优于v2-B。

## Model v3 — Feature-enhanced External Knowledge Ranking

| 项目 | 登记内容 |
|---|---|
| 目的 | 在Model v2外部prior基础上加入增强结构、化学空间相似性和完整ADMET端点，提高候选计算排序能力 |
| 输入特征 | Morgan1024；RDKit16；chemical similarity/scaffold 2；Docking11；QuickProp43；ADMET28；external priors4；总计1,128项 |
| 标签定义 | Dataset v0.2静态MM/GBSA，lower-is-better；静态MM/GBSA没有进入输入特征 |
| 训练数据 | 17个内部候选、11个scaffold；相似性参考为55个去重直接ATP assay结构，与内部canonical SMILES重叠为0 |
| 算法 | 固定参数LightGBM regression；不做小样本超参数搜索 |
| 评价协议 | 11折Leave-One-Scaffold-Group-Out OOF |
| 指标 | Spearman 0.7696；RMSE 4.8877；NDCG@5 0.7782；Top-5 enrichment 1.36；Hit recovery 0.40 |
| 模型文件 | `models/model_v3/model.joblib`；配置与特征见同目录`training_config.json`、`feature_list.json` |
| 主要结果 | `results/model_v3/model_v3_comparison.csv`、`model_v3_oof_predictions.csv`、`candidate_ranking.csv` |
| 限制 | 相比v2仅轻微改善整体相关性；Top-k未改善；Model v1 NDCG@5仍略高；无实验或独立测试集；MD内部覆盖1/17而未入模 |

## 其他保留模型与实验

- Random Forest baseline：`models/random_forest_mmgbsa_baseline.joblib`；
- XGBoost baseline：`models/xgboost_mmgbsa_baseline.joblib`；
- intermediate enhanced ranking v1.0：`models/lightgbm_enhanced_v1.joblib`，1,089特征，Spearman 0.7525；
- Model v2-A structure-only；
- Model v2 Task A/B organism/assay-specific外部子模型；
- Phase 4 LightGBM ranker/LambdaMART和XGBoost ranker实验结果保存在`results/phase4_*`，未被选为统一v0–v3版本。

## Phase 5 Decision Engine（非监督模型）

Decision Engine 不登记为Model v4。它没有训练标签、模型拟合或新性能指标，只根据`scoring_config.json`透明组合Model v3、Docking、静态MM/GBSA、外部prior、相似性、描述符和预测ADMET。当前Final Score不能作为未来训练标签，否则会造成自我循环标签。

## Phase 6A Robustness & Benchmark Validation（非监督模型）

| 项目 | 登记内容 |
|---|---|
| 目的 | 检查Phase 5 Decision Engine对预设权重变化和分量移除的敏感性，并建立只验证不训练的外部benchmark接口 |
| 输入 | `results/final_candidate_ranking.csv`中的17候选及Binding、ATP target、Antibacterial、Drug-likeness四分量；Dataset v1.0仅用于外部精确结构重叠审计 |
| 标签定义 | 无训练标签；不把Final Score、外部prior或内部计算证据视为实验标签 |
| 方法 | default+A-D五套固定权重；Spearman/Kendall排名相关；Top 3/Top 5出现频率；Binding only、Binding+ATP、完整方案三组消融 |
| 评价结果 | A-D最低两两Spearman 0.4583、最低Kendall tau 0.3235；default/A/C/D Top 1为Hit2，B Top 1为Hit13；A-D中始终Top 3和始终Top 5的候选均只有1个 |
| External benchmark | Dataset v1.0外部Layer 1/2与17候选精确canonical SMILES重叠为0；当前可评价benchmark为0，未生成相关性指标 |
| 代码和结果 | `src/phase6a_robustness.py`、`results/phase6A/`、`docs/Phase6A_Robustness_Report.md`、`docs/Phase6A_Limitation_Report.md` |
| 模型变化 | 无；Model v0-v3文件、参数和历史结果均保持不变；没有Model v4 |
| 限制 | 仅17个已筛选候选；场景相关性不是实验准确率；分量存在计算证据相关性；无独立实验验证 |

Phase 6A的场景分数、稳定性和消融结果不得作为未来监督标签，也不得登记为模型性能提升。

## Model v4-alpha — External Knowledge Enhanced Training Experiment

Model v4-alpha 是 Phase 7 的首轮外部知识增强实验，不登记为最终 Model v4，也不替代 Model v3。

| 项目 | 登记内容 |
|---|---|
| 目的 | 验证 Dataset v2.0 的外部抗菌与 ATP synthase 实验知识能否通过独立子任务预测先验，增强内部候选静态 MM/GBSA 排序 |
| Task A | Antibacterial MIC regression；仅精确正值 MIC、统一为 μg/mL，目标为 log10(MIC)，不同物种作为显式条件特征；3,396 个结构-物种样本、2,263 个结构、832 个 scaffold |
| Task B | ATP synthase target regression/ranking；按 activity type、organism species、unit 分为 7 个独立 stratum，4 个达到至少 8 个结构和 3 个 scaffold 的训练门槛；不同端点和单位不合并 |
| Task C | 内部 17 候选排序；保留 Model v3 的 1,128 个特征，新增 1 个 Task A 与 4 个 Task B预测及其等权 rank-percentile ensemble，共 1,134 个特征 |
| 标签定义 | Task A 为实验 MIC；Task B 为各同质 stratum 内实验 activity；Task C 仍为内部静态 MM/GBSA。MIC、IC50、百分比和 MM/GBSA 从未合并为同一 label |
| 数据 | `data/dataset_v2.0/ATP_Navigator_external_dataset_v1.csv`，8,820 行、4,338 个 canonical structures；其中 Task A 6,663、Task B 77、Benchmark 2,080。Benchmark 全部排除训练 |
| 特征与权重 | Morgan1024 + RDKit descriptors；Task A 加 organism one-hot。source level 与 confidence 仅作 sample weight，不作为结构特征；Task A A/B/C=1.0/1.0/0.5，Task B A/B/C=1.0/0.8/0.5 |
| 算法 | 固定参数 LightGBM regression；外部子模型与内部 ranker 分别保存，不进行小样本超参数搜索 |
| 评价协议 | Task A 5-fold scaffold GroupKFold；Task B 每个 stratum 3–5 fold scaffold GroupKFold；Task C 11-fold Leave-One-Scaffold-Group-Out |
| Task A 指标 | 正式 A/B high-confidence 切片：n=3,395，RMSE 0.8015 log10 μg/mL，Spearman 0.7464；没有预注册活性阈值，classification accuracy 标记 not applicable |
| Task B 指标 | 4 个 stratum 的 Spearman 分别为 0.6170、-0.3283、0.7037、0.0838；各指标只在本 stratum 内解释，禁止跨单位汇总为统一 IC50 性能 |
| Task C 指标 | Spearman 0.7549；RMSE 4.9268；NDCG@5 0.7774；Top-5 enrichment 1.36；Hit recovery 0.40 |
| 与 Model v3 比较 | Model v3 为 0.7696 / 4.8877 / 0.7782 / 1.36 / 0.40；v4-alpha 没有提高 Spearman、RMSE、NDCG 或 Top-k，因此不能宣称外部知识已带来性能提升 |
| 模型文件 | `models/model_v4_alpha/`；含 Task A、4 个 Task B 子模型、Task C ranker、`training_config.json`和`feature_list.json` |
| 主要结果 | `results/model_v4_alpha/`、`docs/Model_v4_alpha_Report.md` |
| Decision Engine 接入 | 仅生成 shadow ranking，不覆盖 Phase 5；实验 MIC、ATP enzyme 与毒性仍为 unknown |
| 限制 | Task C 只有 17 个候选；Task B stratum 仅 8–25 个样本；没有独立前瞻测试；source level 为提供文件标注、未逐条回源；预测先验不是内部实验结果 |

## Phase 9 Collaborative Decision Agent（非监督模型）

| 项目 | 登记内容 |
|---|---|
| 目的 | 把研究者意图、现有模型、计算证据和实验预算转化为可审计候选优先级与下一实验计划 |
| 输入 | Phase 5四分量、Model v3/v4-alpha scaffold OOF、compound/scaffold身份、Hit3历史证据与配置化研究意图 |
| 标签定义 | 无新训练标签；ATP enzyme、MIC和实验毒性均保持unknown |
| 方法 | profile条件化；受约束Dirichlet Monte Carlo 20,000次；rank acceptability；Pareto；反事实解释；模型分歧；实验信息价值代理 |
| 输出 | `results/phase9_decision_agent/`中的稳健排名、Pareto、模型分歧、解释、实验面板、evidence ledger和agent trace |
| 结果 | balanced稳健领导者Hit2；冻结面板为Hit2、Hit1、Hit5、Hit13、Hit3、Hit17；这些是决策结果，不是活性验证 |
| 配置/代码 | `config/decision_agent_v1.json`、`src/research_decision_agent.py`、`run_decision_agent.py` |
| 模型变化 | 无；不登记为Model v5，不修改或重训Model v0-v4-alpha |
| 限制 | 权重抽样量化偏好不确定性而非活性概率；无独立实验标签；当前不能证明命中率提升 |

Agent版本只有在输入工具、决策规则、意图schema或审计协议发生变化时升级；监督模型版本仍按下述规则独立登记。

## Phase 10 Integrated Decision Workflow（非监督模型）

| 项目 | 登记内容 |
|---|---|
| 目的 | 将虚拟筛选候选输入自动转化为结构特征、冻结模型输出、多目标决策、稳健排名、解释和工作流自评 |
| 模型调用 | 1128个冻结特征完整时调用Model v3；否则对有效SMILES仅调用Model v2-A structure-only fallback；同时调用4个保留的外部知识prior模型 |
| 训练 | 无；不修改Model v0-v4-alpha，不更新参数或标签 |
| 研究模式 | balanced、binding_focused、atp_mechanism_focused、experimental_validation_focused |
| 评价 | 结构/模型/决策覆盖、排名完整性、unknown完整性、分数语义、来源、model hash、确定性复跑；Demo 10/10 checks passed |
| 跨模式结果 | balanced和binding-focused首位Hit2；ATP mechanism-focused首位Hit5；experimental validation-focused首位Hit1；最低两两Spearman 0.4681 |
| 代码/配置 | `src/input_processor.py`、`src/navigator_pipeline.py`、`src/explanation_generator.py`、`src/workflow_evaluator.py`、`configs/research_profiles.json` |
| 限制 | 自评是工作流完整性，不是生物活性准确率；实验ATP/MIC/毒性均unknown；批次相对分数不可解释为成功概率 |

Phase 10不登记为Model v5。其`model_score`仍是静态MM/GBSA计算任务预测，Decision score不得回流为监督标签。

## 新模型登记规则

未来只有满足以下条件才能新增版本号：

1. 明确训练目标和标签语义；
2. 训练数据版本固定且有来源hash；
3. canonical SMILES去重并采用scaffold-aware划分；
4. 与v0–v3在相同可比集合和协议下评价；
5. 保存模型、参数、feature list、OOF/独立测试预测和限制；
6. 同步更新本文、Current System Status、Data Registry和Development History。
# Phase 15登记（非模型版本）

Phase 15没有新增Model v5，也没有重新训练Model v0–v4-alpha。Acquisition Engine是透明、配置化的证据获取启发式：其输出是下一份计算证据的优先级，不是活性预测模型；VOI proxy、consensus、uncertainty和Hybrid score不得登记为监督label或生物活性概率。

## Phase 16登记（非模型版本）

Phase 16没有新增Model v5。RDKit生成器、cheap screening和generated acquisition是配置化结构生成/证据获取规则，不是监督活性模型。Generated structures、Vina scores、novelty、SA-like proxy和综合priority均禁止作为伪实验label回流训练。
