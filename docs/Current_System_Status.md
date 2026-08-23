# ATP-Navigator Current System Status

更新时间：2026-08-23

当前阶段：Phase 6B — External Benchmark Pipeline

当前系统定位：基于鲍曼不动杆菌 F1F0-ATP synthase 真实虚拟筛选案例的 AI 增强型候选优先级排序与多目标决策系统。系统优化已有计算候选排序，不替代 Schrödinger、MD/MMGBSA 或实验验证。

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

Phase 5 Decision Engine 不是新的监督模型，不登记为 Model v4。它读取 Model v3 和已有计算/外部先验，根据 `scoring_config.json` 的人工透明权重形成决策排序。

Phase 6A同样不是Model v4。它不训练模型，只对Phase 5既有四分量执行预设权重扰动、排名相关性、Top-k一致性和消融验证。

Phase 6B不是新模型，也不改变Decision Engine。它导入公开ATP synthase inhibitor记录，完成结构处理后，仅允许已有完整Phase 5计算证据的分子取得原始Decision Engine分数。

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

## 4. 当前代码结构

```text
ATP-Navigator/
├─ data/                 数据注册表、版本化数据、外部上传和文献记录
├─ src/                  审计、数据构建、特征、训练、评价和Decision Engine
├─ models/               历史模型与版本化配置
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
- 可与17个内部候选精确对应、且endpoint/unit/assay一致的独立外部benchmark；
- 为独立外部候选补齐按冻结协议生成的Docking、静态MM/GBSA、Model v3输入和预测ADMET等Decision Engine必需证据；
- 对公开 Dataset v1.0 逐条回源复核；
- 跨批次可校准的绝对决策分数；
- 网页端、正式服务API和软著交付包。

## 7. 当前系统边界

- Model v3 OOF Spearman 0.7696、RMSE 4.8877、NDCG@5 0.7782、Top-5 enrichment 1.36；只有17个样本，不能视为稳定泛化性能。
- Phase 5 不训练模型，也没有新性能指标。Final Score 是相对当前17候选的决策规则输出，不是活性或成功概率。
- 当前Top候选为 `ATP-SMI-C93E6EC67CDB (Hit2)`，依据是多目标计算证据；MIC、ATP enzyme和实验毒性仍为unknown。
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
