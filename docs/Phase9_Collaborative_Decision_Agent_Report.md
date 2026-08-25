# Phase 9 Collaborative Decision Agent Report

日期：2026-08-26  
版本：`ATP-Navigator_Phase9_Collaborative_Decision_Agent_v1.0`  
模型变化：无；Model v0-v4-alpha与Phase 5 Decision Engine均保留

## 1. 系统定位

Phase 9把既有模型、决策分量、稳健性分析和实验规划组织为一个受控的研究者协作Agent。Agent的任务不是替研究者宣称活性，而是将研究意图翻译为可审计的偏好分布，调用现有专业工具，暴露排序不稳定性，比较人工历史选择，并建议在有限预算下最有信息价值的下一批验证。

选择的研究意图配置：`balanced`。来源：`explicit_profile`。是否需要人工确认：`false`。

## 2. 前沿方法的项目化实现

- 工具编排：读取冻结的Phase 5分量、Model v3/v4-alpha OOF和证据注册，而不是让语言模型生成化学分数；
- 偏好条件化：四个决策目标不固定为唯一权重，按研究任务选择profile；
- 稳健多目标排序：使用SMAA-inspired受限Dirichlet Monte Carlo，报告rank acceptability；
- Pareto分析：识别不存在单一目标全面更差的候选；当前Pareto第一层有12个候选；
- 反事实解释：回答单个候选主要被哪个分量拉开，以及需要多大归一化分量变化才可能改变顺序；
- 主动验证：用排名区间、Top-5边界不确定性、Model v3/v4分歧、scaffold稀有度和Hit3历史证据建立透明的信息价值代理。

## 3. 当前profile稳健Top 5

| Robust order | Alias | Compound ID | Mean rank | 90% rank interval | P(Top3) | P(Top5) |
|---:|---|---|---:|---:|---:|---:|
| 1 | Hit2 | ATP-SMI-C93E6EC67CDB | 1.31 | 1–2 | 0.971 | 0.990 |
| 2 | Hit1 | ATP-SMI-9DA3213A09E8 | 1.85 | 1–2 | 0.997 | 1.000 |
| 3 | Hit4 | ATP-SMI-5D3E7B6B6796 | 4.04 | 3–6 | 0.275 | 0.897 |
| 4 | Hit5 | ATP-SMI-96FD6257D8BA | 4.49 | 3–8 | 0.404 | 0.780 |
| 5 | Hit13 | ATP-SMI-5B36D3E11A3B | 5.61 | 3–9 | 0.219 | 0.453 |

这里的P(Top-k)只表示在已声明权重分布下进入Top-k的频率，不是活性概率、成功概率或置信度校准结果。

## 4. Hit3与Agent结果的正确关系

- Agent稳健首位：Hit2（ATP-SMI-C93E6EC67CDB），mean rank=1.31；
- 历史Hit3：ATP-SMI-874C2DE25FE4，Phase 5 rank=8，robust order=10，90% rank interval=5–16；
- Hit3仍保留原始人工选择、100 ns MD/MMGBSA及NMR/LC-MS化学表征优势，但ATP enzyme、MIC和实验毒性仍为unknown；
- 最有价值的验证不是让AI强行“同意”或“否定”Hit3，而是把Hit3与Agent稳健Top、模型分歧候选和低优先比较候选放进同一冻结实验面板。

## 5. 建议冻结的首轮实验面板

| Order | Candidate | Role | Mean rank | Information-value proxy | Result |
|---:|---|---|---:|---:|---|
| 1 | Hit2 | robust_profile_leader | 1.31 | 0.066 | unknown |
| 2 | Hit1 | weight_robust_high_priority | 1.85 | 0.181 | unknown |
| 3 | Hit5 | information_value_and_scaffold_diversity | 4.49 | 0.441 | unknown |
| 4 | Hit13 | information_value_fill | 5.61 | 0.410 | unknown |
| 5 | Hit3 | legacy_Hit3_MD_and_chemical_characterization_bridge;model_version_disagreement_probe | 9.78 | 0.489 | unknown |
| 6 | Hit17 | lower_priority_comparator_not_assumed_inactive | 13.49 | 0.262 | unknown |

首要终点应为同一protocol下ATP synthase功能/酶抑制剂量反应；随后再做同菌株MIC。必须包含IN-2阳性、vehicle、适当比较候选及技术/生物重复。面板中较低优先候选只是比较对象，不能预先称为阴性。

## 6. 可信度边界

- 现有17候选的监督标签是静态MM/GBSA，不是真实活性；
- Binding内部存在相关证据重复，Agent单独保留相关性警告；
- ATP和抗菌先验来自外部跨域模型，不能当作内部测量；
- 20,000次权重抽样量化的是决策偏好不确定性，不是模型预测误差的正式概率校准；
- 当前不具备用于可靠conformal calibration的独立实验标签，因此未伪造预测区间；
- 实验结果回填前，Agent只能证明候选决策过程更透明、可追踪和可执行，不能证明命中率已经提高。

## 7. 比赛主张

ATP-Navigator的核心创新应表述为：在传统Schrödinger虚拟筛选之后、合成与生物验证之前，建立研究者意图驱动的证据决策层，把依赖经验的候选取舍转化为可审计的多目标排序、稳健性分析和主动验证计划。项目当前最强证据是完整真实计算链、可运行代码、模型历史对照、结构恢复、决策敏感性与真实的验证接口，而不是未完成的实验命中率。
