# ATP-Navigator 项目战略总纲

版本：v1.0  
日期：2026-08-26  
适用对象：团队成员、指导教师、比赛评委与后续开发人员

## 一句话结论

本项目最终选题建议确定为：

> **ATP-Navigator：面向 ATP 合酶虚拟筛选后实验决策的研究者协作型 AI 候选优先级系统**

英文副标题可使用：*An evidence-grounded, researcher-in-the-loop decision agent for post-screening candidate prioritization.*

ATP-Navigator 不是通用“药物发现平台”，也不宣称已经发现新药。它解决的是一个更具体、真实且可验证的问题：Schrödinger 虚拟筛选完成后，面对多项不完全一致的计算证据，研究人员应优先把有限的合成和实验资源投入哪些候选。

## 1. 项目从哪里开始

原始科研项目以鲍曼不动杆菌 F1F0-ATP synthase 为靶点，参考结构为 PDB 7P3W，参考配体为 IN-2。原始 39 页研究汇报记录了一条传统计算化学链：

1. 靶点与结合位点分析；
2. IN-2 体系 100 ns 分子动力学分析；
3. 以 IN-2 为基础构建约十万规模衍生物库；
4. QuickProp 预筛；
5. HTVS、SP、XP 逐级 Docking；
6. 静态 MM/GBSA 重打分并形成 17 个候选；
7. 结合结合能与预测毒性等信息，历史上选择 Hit3；
8. 对 Hit3 完成 100 ns MD、MD/MMGBSA、NMR 与 LC-MS 化学表征。

原汇报中的可确认计算结果包括：IN-2 的 MD/MMGBSA 汇总值约为 -38.42 kcal/mol，Hit3 的 MD/MMGBSA 汇总值约为 -48.69 kcal/mol；静态候选结果中 Hit1、Hit2、Hit3 的 MM/GBSA 约为 -57.51、-56.56、-56.37 kcal/mol。以上都是计算证据，不是 ATP 酶抑制、MIC、毒性或临床有效性的实验结果。

## 2. 真正的决策瓶颈

传统流程并非缺少分数，而是缺少一种能够处理“多个分数互相冲突”的规范化决策机制。例如：

- Docking 高不等于真实结合稳定；
- MM/GBSA 更优可能伴随分子过大、成药性或毒性风险；
- 与已知抑制剂结构相似并不等于具有同样活性；
- ADMET 与外部知识多为预测或跨域证据；
- 研究人员还会考虑可合成性、化学新颖性、实验预算和失败风险。

现实中，这些权衡通常存在于研究者经验中，难以追溯，也难以复现。ATP-Navigator 把这一步从隐性的“凭经验挑选”转化为显式、可审计、可解释的候选优先级决策。

## 3. AI 应插入的准确位置

```text
靶点确定与化合物库
        ↓
Schrödinger HTVS / SP / XP
        ↓
Docking、QuickProp、MM/GBSA、MD、ADMET证据
        ↓
【ATP-Navigator研究者协作型AI决策层】
        ↓
冻结候选面板与实验计划
        ↓
合成/样品QC → ATP synthase实验 → MIC/MBC → 毒性/选择性
        ↓
真实实验反馈进入下一轮模型与决策审计
```

因此，AI 与传统虚拟筛选是串联关系：AI 位于虚拟筛选之后、昂贵湿实验之前。比较验证则采用并行对照：在同一实验批次、同一预算下比较 Docking-only、历史人工选择、固定权重 Decision Engine 与 Phase 9 稳健 Agent 的候选策略。

## 4. 已经完成的三个时间层

### 过去：真实计算化学案例

- 完成 ATP synthase 靶点与 IN-2 参考体系研究；
- 完成衍生物虚拟库、分级 Docking、QuickProp、MM/GBSA；
- 形成 17 个内部候选；
- 历史上选择并合成 Hit3，完成 NMR、LC-MS 与案例级 MD 分析；
- 尚未完成 ATP enzyme、MIC、实验毒性和独立前瞻验证。

### 现在：数据、模型与决策系统

- Phase 0：159 个原始文件只读审计，形成文件、化合物、筛选记录和 MD 系统注册；
- Phase 1–2：建立 Docking-only、Random Forest、XGBoost、LightGBM baseline 与增强特征；
- Phase 3–4：建立 Dataset v1.0、外部知识分任务建模、Model v2 与 Model v3；
- Phase 5–6：建立透明多目标 Decision Engine、权重敏感性、消融和 external benchmark 空接口；
- Phase 7：Model v4-alpha 首次外部知识增强实验，结果未超过 Model v3，因此未替代正式模型；
- Phase 8：从 Maestro 源文件恢复 1,633 个 HTVS 化合物结构，建立 60 个同协议 MM/GBSA 数据获取队列；
- Phase 9：建立研究者意图驱动、稳健排序、Pareto 分析和下一实验建议的协作型 Decision Agent。

### 将来：真实验证闭环

- 冻结首轮候选面板和分析规则；
- 使用同一实验 protocol 获得 ATP synthase 功能/酶抑制剂量反应；
- 在同一鲍曼不动杆菌菌株和培养条件下获得 MIC/MBC；
- 开展细胞毒性、选择性和必要的聚集/干扰排查；
- 用新实验数据做独立评价，之后才允许迭代模型。

“将来”部分是计划，不是完成成果。

## 5. 为什么当前算法路线是先进且适配的

先进不等于在小数据上强行使用 GNN、Transformer、YOLO 或 ResNet。YOLO/ResNet主要解决图像表征问题，与本项目的结构化分子证据和候选决策目标不匹配；17 个内部候选也不足以支持复杂深度网络的可靠训练。

本项目吸收了前沿科学智能体的四个核心原则：

1. **工具增强而非语言模型直接给化学分数**：Coscientist 与 ChemCrow 的重要思想是让智能体调用检索、计算和专业工具。ATP-Navigator 中，模型、RDKit、Decision Engine 和数据注册表是可审计工具，语言层只解析研究意图和组织解释。
2. **多参数决策敏感性**：药物研发本质是多参数优化，单一权重可能让项目错失机会，因此必须报告权重变化下的排名稳定性。
3. **研究者在环**：系统允许“结合优先”“靶点机制优先”“转化平衡”等明确意图，但自由文本推断必须由研究者确认，避免 Agent 擅自改变科研目标。
4. **预算约束下主动获取信息**：MolPAL、ChemScreener 等工作说明，主动学习的关键不是把所有分子都算完，而是在 exploitation、uncertainty 与 chemical diversity 之间选择下一批最有信息价值的样本。

Phase 9 由此采用：

- 研究意图 profile；
- 20,000 次受约束 Dirichlet 权重抽样；
- rank acceptability：报告进入 Top 3/Top 5 的权重条件频率；
- Pareto front：避免把不可互相替代的目标硬压成唯一结论；
- Model v3/v4-alpha 分歧审计；
- 反事实解释；
- 基于排名区间、Top-5 边界、模型分歧、scaffold 稀有度和历史 Hit3 的实验信息价值代理；
- 完整 evidence ledger 与 agent trace。

上述 P(Top-k) 不是活性概率。系统没有独立实验数据来做概率校准或 conformal prediction，因此没有伪造置信区间。

## 6. Phase 9 当前真实结果

平衡型研究意图下，17 个候选的稳健前五为：Hit2、Hit1、Hit4、Hit5、Hit13。Hit2 的平均排名为 1.31，90% 权重条件排名区间为 1–2；Hit1 为 1.85，区间为 1–2。

历史 Hit3 的稳健顺序为第 10，平均排名约 9.78，90% 区间为 5–16。它仍具有历史人工选择、合成表征和案例级 MD 的独特价值，但并不是平衡型 Agent 的稳健首位。

不同研究意图给出不同领导者：

- balanced：Hit2；
- binding_first：Hit2；
- target_mechanism：Hit1；
- translational_balance：Hit2。

这不是系统矛盾，而是向评委展示“候选优先级取决于项目目标”，并且目标变化可以被追溯。

建议冻结的六候选验证面板为：Hit2、Hit1、Hit5、Hit13、Hit3、Hit17。它同时覆盖稳健高优先、化学空间/信息价值、历史人工选择和较低优先比较对象。Hit17 不能预先称为阴性。

## 7. Hit3 与 AI 应该一致还是不一致

最科学的答案不是追求“刚好一致又不一致”，而是先冻结规则，再接受真实结果。

- 若 AI 与 Hit3 完全一致，只能说明系统重现了部分人工判断，不能证明额外价值；
- 若 AI 排名不同，也不能说明 AI 一定正确；
- 最有信息价值的设计是把 Hit3、AI 稳健 Top、模型分歧候选和比较候选放入同一盲态/冻结实验面板；
- 实验揭盲后，再评价哪种策略在相同预算下获得更高命中率、更低失败比例和更快的首个有效候选。

因此，当前结果的价值是提出一项可被推翻的前瞻验证，而不是事后修改数据让 AI 看起来正确。

## 8. 应怎样设计湿实验闭环

### Stage 0：身份与可测性

- 样品身份、纯度与稳定性；
- 溶解度和 DMSO 工作浓度；
- 必要时排查聚集、荧光/检测干扰；
- 未通过 QC 的样品标记失败原因，不填成“无活性”。

### Stage 1：靶点层首要终点

- 同一 protocol 下 ATP synthase 功能或酶抑制剂量反应；
- IN-2 阳性对照、vehicle 阴性/背景对照；
- 预先确定重复数、浓度梯度、质控标准和主要评价量；
- 建议优先完成六候选冻结面板。

### Stage 2：抗菌效应

- 使用明确菌株、培养条件和统一标准的 MIC；
- 根据资源补充 MBC；
- ATP enzyme 与 MIC 必须分别记录，不能混成一个标签。

### Stage 3：转化风险

- 细胞毒性与选择性窗口；
- 必要的溶血、聚集和非特异干扰；
- 这些结果完成前均保持 unknown。

### 前瞻比较设计

在相同预算下预先冻结四种策略的 Top-k：

1. Model v0：Docking-only；
2. 历史人工决策：Hit3 及其当时选择规则；
3. Phase 5：固定权重 Decision Engine；
4. Phase 9：研究意图驱动的稳健 Agent。

实验完成后再计算：ATP enzyme hit rate、MIC hit rate、EF@k、NDCG@k、无效测试比例、cost-to-first-hit、每个有效候选的耗材/工时，以及不同操作者重复决策的一致性。当前这些指标均无真实数值，禁止预填。

## 9. 与比赛评分的对应

### 靶点理解

- 清楚说明 ATP synthase 的生物学意义、7P3W/IN-2 依据和结合位点；
- 区分靶点抑制、细菌生长抑制和毒性三个层次。

### 计算筛选设计

- 展示从库构建、QuickProp、HTVS/SP/XP 到 MM/GBSA/MD 的完整真实链；
- 展示 1,633 个 HTVS 结构恢复与 60 个结构感知数据获取队列；
- 保留 Docking-only 对照，而非只展示 AI。

### AI 创新

- 创新点是决策节点和研究者协作机制，而非深度模型名称；
- 展示意图条件化、权重稳健性、Pareto、模型分歧、反事实解释和主动验证；
- 明确 AI 不生成化学真值。

### 验证与可复现性

- 已有代码入口、固定随机种子、配置文件、输入输出和 agent trace；
- 真实实验结果未完成，主动说明并给出冻结验证方案；
- 外部 benchmark 不独立时保持 empty，不用训练重叠数据冒充验证。

项目更适合争取“最佳虚拟筛选”和“最佳项目展示”方向；在湿实验完成前，不应主张“最佳实验验证”。

## 10. 评委叙事主线

1. 我们不是从 AI 概念出发寻找应用，而是从一条真实 ATP synthase 虚拟筛选链发现决策瓶颈；
2. 传统计算产生了 17 个候选，但各证据尺度不同、结论不完全一致；
3. 历史人工选择 Hit3 暴露了经验型决策难以复现的问题；
4. 我们先把原始文件、身份、标签和证据资产化，再建立可复现 baseline；
5. 外部知识扩展未盲目混标签，Model v4-alpha 未超过 v3 也被如实保留；
6. 因此我们没有继续堆模型，而是建立研究者协作型 Decision Agent；
7. Agent 将研究意图、模型、计算证据、稳健性和实验预算联结成可审计行动；
8. 当前贡献是建立一项真实、可执行、可证伪的科研工作流；
9. 下一步用冻结候选面板验证其是否减少无效测试、降低成本并提高候选命中效率。

## 11. 当前最缺少的数据

按优先级排序：

1. 六候选同 protocol 的 ATP synthase 剂量反应；
2. 同菌株、同条件的 MIC/MBC；
3. 细胞毒性和选择性数据；
4. Phase 8 P0 24 个候选的同协议 MM/GBSA，用于扩大内部 Task C；
5. 与当前训练来源严格独立、同 endpoint/organism/unit 的 ATP synthase benchmark；
6. 失败样本和中等/弱活性样本，而不仅是文献正例；
7. 完整实验 protocol、重复、比较符、上下界和 QC 状态。

公开数据可以增强化学空间和先验，但不能替代本项目同靶点、同协议、同候选的实验标签。真正让系统“变强”的不是再添加一批来源不明 CSV，而是获得可追溯、可比较、包含失败样本的反馈。

## 12. 不可越过的科学边界

- 不制造 ATP 酶、MIC、毒性或命中率数据；
- 不把 Docking、MM/GBSA、MIC、IC50 合为一个监督标签；
- 不把 Model v3/v4 预测当实验真值；
- 不把 P(Top-k) 表述为活性概率；
- 不把 NMR/LC-MS 结构确证表述为生物活性验证；
- 不把计划中的闭环写成已完成；
- 不为迎合结论而在实验结果出现后改变冻结规则。

比赛强调“真问题、真数据、真验证”。项目可以在两个月内没有完成全部实验，但不能用假数据填补缺口。诚实呈现小数据限制、保留失败的 Model v4-alpha，并提出前瞻验证，反而构成项目可信度的一部分。

## 13. 主要方法依据

1. Boiko DA, MacKnight R, Kline B, et al. *Autonomous chemical research with large language models*. Nature, 2023. DOI: 10.1038/s41586-023-06792-0.
2. Bran AM, Cox S, Schilter O, et al. *Augmenting large language models with chemistry tools*. Nature Machine Intelligence, 2024. DOI: 10.1038/s42256-024-00832-8.
3. Graff DE, Shakhnovich EI, Coley CW. *Accelerating high-throughput virtual screening through molecular pool-based active learning*. Chemical Science, 2021. DOI: 10.1039/D0SC06805E.
4. Nahal Y, Menke J, Martinelli J, et al. *Human-in-the-loop active learning for goal-oriented molecule generation*. Journal of Cheminformatics, 2024. DOI: 10.1186/s13321-024-00924-y.
5. Segall MD, Yusof I, Champness EJ. *Avoiding Missed Opportunities by Analyzing the Sensitivity of Our Decisions*. Journal of Medicinal Chemistry, 2016. DOI: 10.1021/acs.jmedchem.5b01921.
6. Shen L, Fang J, Liu L, et al. *ChemScreener: an active learning enabled hit discovery workflow with WDR5 inhibitor case study*. Journal of Cheminformatics, 2026. DOI: 10.1186/s13321-026-01204-7.该工作用于架构参照，靶点不同，不是 ATP-Navigator 的独立验证证据。

## 14. 最终判断

ATP-Navigator 最值得参赛的，不是“AI 比 Docking 准了多少”这一句尚缺实验支撑的话，而是把真实虚拟筛选项目中最昂贵、最依赖经验、最难标准化的候选决策步骤，重构为一个研究者可控制、证据可追溯、结果可解释、下一步可执行的智能决策接口。

项目当前已经具备可运行的计算原型和完整叙事；下一次质的提升必须来自冻结实验面板的真实反馈。

