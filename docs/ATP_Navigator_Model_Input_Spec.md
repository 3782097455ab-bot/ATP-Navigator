# ATP-Navigator 模型输入规范 v1.0

**日期**：2026-08-24
**适用数据**：ATP_Navigator_external_dataset_v1.csv（8,820 行，字段与取值见 ATP_Navigator_Data_Dictionary_v1.md）
**读者**：模型开发人员

---

## 1. 三个任务定义

### Task A：Antibacterial activity modeling（抗菌活性建模）
- **目标**：给定分子结构，预测对革兰阴性菌的全细胞抗菌活性。
- **数据子集**：`task_type = Antibacterial`（6,663 行，MIC，μg/mL）。
- **输入字段**：`canonical_smiles`（分子表征唯一入口）、`organism`（菌种，作为条件特征或分物种建模）。
- **输出字段**：`activity_value` + `unit`（回归：MIC 数值；或按阈值二分类 active/inactive）。
- **允许的数据类型**：experimental（source_level A/B/C）。
- **禁止混合**：
  - 不得混入 `ATP_target`（酶活）或 `Benchmark`（结合亲和力）行作为标签；
  - 不得将截尾值（">64"）静默转为数值参与回归——须删去或按删失数据处理；
  - MIC（μg/mL）不得与其他量纲直接拼接训练。

### Task B：ATP synthase target modeling（ATP 合酶靶点建模）
- **目标**：给定分子结构，预测对细菌 F1Fo-ATP 合酶的酶级抑制活性。
- **数据子集**：`task_type = ATP_target`（77 行，IC50/Inhibition）。
- **输入字段**：`canonical_smiles`、`target`（区分 Fo a/c 界面 vs 结核分枝杆菌 ATP 合酶等亚型）。
- **输出字段**：`activity_value` + `unit`（IC50，注意 μg/mL、ng/mL、nM 三种单位并存，须先按分子量换算或分单位建模）。
- **允许的数据类型**：experimental（source_level A/B）。
- **禁止混合**：
  - 不得混入 MIC（全细胞）数据冒充酶活标签；
  - 不得混入 % Inhibition 与 IC50 于同一回归目标（量纲不同）；
  - 不得使用 D 级预测数据作标签（当前库中无，属预防性规则）。

### Task C：Candidate ranking decision engine（候选排序决策引擎）
- **目标**：融合 Task A/B 输出与外部 benchmark 表现，对候选分子排序。
- **数据子集**：Task A/B 模型输出 + `task_type = Benchmark`（2,080 行，BindingDB，IC50/Ki/EC50/Kd，nM）用于泛化能力校准。
- **输入字段**：上游模型预测值、`confidence`、`source_level`、（可选）Benchmark 子集的结构-亲和力对。
- **输出字段**：排序分数 / 优先级列表（本数据集不提供该标签，由引擎生成）。
- **允许的数据类型**：实验数据 + 模型预测（预测值只允许出现在引擎内部，不回写数据资产）。
- **禁止混合**：Benchmark 数据只用于校准与评估，**不得**并入 Task A/B 的训练标签。

## 2. 字段用途划分

| 字段 | training | validation | benchmark/报告 |
|------|:---:|:---:|:---:|
| canonical_smiles | ✅ 输入 | ✅ 输入 | ✅ 输入 |
| organism / target | ✅ 条件特征 | ✅ | ✅ 分层报告 |
| activity_value + unit | ✅ 标签 | ✅ 评估真值 | ✅ 评估真值 |
| task_type | ✅ 数据路由 | ✅ | ✅ |
| source_level | ⚠️ 采样权重 | ✅ 评估切片 | ✅ 只报告 A/B 级指标 |
| confidence | ⚠️ 样本权重 | ✅ 评估切片 | ✅ |
| compound_id | ❌ 不作特征 | ❌ | ✅ 追溯 |
| reference | ❌ 不作特征 | ❌ | ✅ 追溯 |

- **训练/验证划分必须按 canonical_smiles 去重分组**（scaffold split 推荐），防止同一分子泄漏到两侧。
- 跨来源重复（同一 SMILES 不同 compound_id，如 IN-2）在划分时视为同一样本。

## 3. source_level 与 confidence 在模型评价中的使用

1. **训练权重**：按 Source_Quality_System.md 第 3 节——A=1.0，B=0.8（微调）/1.0（预训练），C=0.5；预训练与微调权重方案不同，须在训练配置中显式声明。
2. **评价切片**：验证集指标必须按 source_level 分层报告（A 级单独出指标）；不得只报混合指标。
3. **confidence 门槛**：正式性能报告仅统计 `confidence = high` 的留出样本；medium 样本可用于训练，其评估结果单独标注。
4. **Benchmark 任务（Task C 校准）**：只使用 `task_type = Benchmark` 行；这些行禁止出现在 Task A/B 训练集，避免泛化能力高估。
5. **D 级数据**（当前无）：未来若引入，只能作为预训练弱标签或引擎内部特征，权重 ≤0.3，且永不出现在评估集。

## 4. 红线

- 不修改已有 CSV；如需清洗（单位换算、截尾值处理）在训练流水线内完成并留配置记录。
- 不向任何文件回写预测值充当标签。
- 无来源（reference）的记录不得进入任何任务。
