# ATP-Navigator Label Policy

版本：Dataset v1.0  
核心原则：Dataset v1.0 是分层证据注册表，不是单一标签训练表。任何训练任务必须先按数据层、标签语义、靶点、物种、单位和实验/计算协议生成独立 task view。

## 1. 标签来源边界

| 数据层 | 标签性质 | 可以表达的结论 | 不能表达的结论 |
|---|---|---|---|
| Layer 1 | whole-cell antibacterial MIC | 化合物在特定菌种/菌株与 assay 下的表型抗菌活性 | ATP 合酶直接抑制、结合亲和力或作用机制 |
| Layer 2 | ATP synthesis IC50、ATP系列化合物MIC、ETC、Inhibition、细胞毒性 | ATP相关实验知识、同系列SAR和辅助表型/安全证据 | 所有记录都直接作用于 ATP 合酶；MIC 等价于 IC50 |
| Layer 3 | Glide、静态MM/GBSA、MD/MMGBSA | 当前项目计算流程下的候选排序证据 | 真实生物活性、临床有效性或实验命中 |

## 2. Classification 使用规则

允许的 classification 必须由一个预注册任务单独生成；Dataset v1.0 当前不直接提供二元标签。

- Layer 1 MIC：只有在 organism/strain、assay、单位和阈值明确后，才能生成 active/inactive。阈值必须来自任务定义或公认标准，不能从本数据分位数临时挑选。
- Layer 2 ATP synthesis：可在同一 assay、同一单位下按预注册阈值分类；不能把 ETC IC50、whole-cell MIC 和 ATP synthesis IC50 共同二值化。
- Inhibition 百分比：只有同时知道测试浓度、时间和阳性/阴性定义时才能分类；当前只有百分比而条件不完整的记录不用于监督分类。
- 细胞毒性：只能作为安全性/选择性任务，不作为抗菌活性正标签。
- 无活性值的4条 Dataset v1.0 记录是 target annotation，只可用于知识图谱/结构空间描述。

## 3. Ranking 使用规则

- Layer 3 静态 MM/GBSA 是当前候选排序主标签，lower-is-better；只和相同 `MMGBSA_dG_Bind_static` 协议的记录比较。
- Glide docking score 是独立 ranking baseline，lower-is-better；不能与 MM/GBSA 数值拼接后共同排序。
- MD/MMGBSA 1000帧均值是后段证据，只覆盖IN-2与Hit3；在更多体系与完整协议可用前不作为通用训练标签。
- Layer 1/2 可在同一 assay/source、organism/strain、activity type和单位内形成 pairwise ranking；比较符/范围可转为顺序约束，但不能伪装为精确回归值。
- 多个 pose/state 必须先在 compound level 按预注册规则聚合，不能把同一化合物构象当作独立样本进入不同数据折。

## 4. Regression 使用规则

回归仅使用满足以下全部条件的记录：

1. `activity_value` 是精确有限数值，不含 `<`、`>`、范围或其他截尾表达；
2. activity type、target、organism/strain 和 assay 兼容；
3. unit 明确且可以在不引入假设的情况下统一；
4. 同一结构的重复/别名记录不会跨训练测试；
5. 标签方向和转换写入任务 metadata。

MIC 的 `ug/mL` 可以在同一表型任务中做 `log10(MIC)`，但不等于摩尔浓度。IC50/Ki/Kd 只有在单位可转换为 mol/L 时才能生成 pActivity。缺少可靠分子量、盐型或单位时禁止质量浓度到摩尔浓度转换。

## 5. 明确禁止的标签混合

- MIC、IC50、Ki、Kd、Inhibition%、Glide score、静态MM/GBSA和MD/MMGBSA不得作为同一个回归列。
- 不同 organism/strain 的 MIC 不默认同质。
- whole-cell MIC 不默认等于 ATP synthase inhibition。
- ATP synthesis IC50、ETC IC50和细胞毒性IC50不得合并。
- 不同 docking/MMGBSA 软件、受体构象或协议的绝对分数不得直接合并。
- 比较符、范围值和缺失值不得用边界值、区间中点或零进行静默填补。
- 公开实验标签不得描述为ATP-Navigator团队完成的实验验证。

## 6. `label_confidence` 定义

| 值 | 含义 | 训练资格 |
|---|---|---|
| `high_internal_identity_confirmed` | 内部来源文件、结构身份和映射已在现有资产中确认 | 可进入对应计算任务，但仍不是实验活性 |
| `medium_source_traceable_unverified` | 有来源与文献信息；尚未逐条回源复核 | 通过任务清洗与抽样复核后可用 |
| `medium_internal_alias_structure_unresolved` | 内部数值来源明确，但结构链接仅为别名链 | 可作证据展示；结构模型训练前必须解决身份 |
| `low_annotation_or_incomplete` | 无可监督活性值或关键 assay 字段缺失 | 不进入监督训练 |
| `low_provenance_incomplete` | 缺少来源或 reference | 隔离，补齐前不训练 |

置信度评价的是记录溯源、身份和标签完整性，不评价化合物是否“更有效”。

## 7. 数据划分与泄漏控制

- 首先按 canonical SMILES/InChIKey 做身份组；同结构不同 compound ID 必须在同一数据折。
- 再按 Bemis–Murcko scaffold 做 group split；比赛主结果继续使用 scaffold-aware 评估。
- 同一化合物的不同 assay、菌株、构象、pose和重复测量不得跨训练/测试。
- ATP系列论文的结构类似物应在 source/scaffold 维度做压力测试，避免随机切分夸大泛化。
- 外部预训练模型产生的 prior 必须用独立或OOF方式生成，不能使用当前测试折标签。

## 8. 推荐 task views

1. `L1_MIC_gram_negative_v1`：按 organism/strain 分任务的 whole-cell MIC；用途是抗菌化学空间和表型先验。
2. `L2_ATP_synthesis_IC50_v1`：仅 ATP synthesis direct assay；用途是靶点专项结构—活性先验。
3. `L2_ATP_series_MIC_v1`：ATP抑制剂系列的whole-cell MIC；用途是渗透/外排/表型辅助任务。
4. `L3_Glide_ranking_v1`：内部 docking baseline。
5. `L3_static_MMGBSA_ranking_v1`：17候选主排序标签。
6. `L3_MD_evidence_v1`：IN-2/Hit3后段证据；当前仅展示，不训练通用模型。

这些 task views 应从 Dataset v1.0 派生并独立版本化，不能覆盖统一注册表或已有 baseline。
