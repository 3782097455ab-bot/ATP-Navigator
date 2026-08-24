# ATP-Navigator 数据字典 v1.0

**版本**：v1.0
**日期**：2026-08-24
**适用范围**：ATP_Navigator_external_dataset_v1.csv（标准输入格式）、ATP-Navigator公开训练数据库.csv（主库）、Member1/2/3 数据样例

---

## 1. 标准输入数据集字段（ATP_Navigator_external_dataset_v1.csv）

| # | 字段 | 含义 | 数据类型 | 允许范围/取值 | 缺失值规则 |
|---|------|------|----------|----------------|------------|
| 1 | compound_id | 化合物唯一标识 | string | ChEMBL ID（CHEMBL\d+）/ BindingDB ID（BDBM\d+）/ 文献编号（WSA\d+、WARD2024-\d+、STEED2022-\d+、FRAUNFELTER2023-\d+、CTRL-\*） | 不允许缺失 |
| 2 | canonical_smiles | 规范 SMILES | string | RDKit 规范化输出；必须可被 RDKit 解析 | 不允许缺失（入库前必须解析通过） |
| 3 | target | 靶点描述 | string | 自由文本；酶级数据写具体蛋白（如 "F1Fo-ATP synthase (Fo a/c interface)"）；细胞级数据写 "whole-cell antibacterial activity (菌种)" | 不允许缺失 |
| 4 | organism | 测试菌种/物种 | string | 完整拉丁名 + 菌株号（如 "Acinetobacter baumannii ATCC 17978"）；禁止缩写 | 缺失填 unknown |
| 5 | activity_type | 活性类型 | string | 见第 3 节分类体系 | 缺失填 unknown |
| 6 | activity_value | 活性数值 | string（保留原始表述） | 数值 / 截尾值（">64"、"<0.1"）/ 范围值（"64-128"） | 缺失填 unknown，禁止编造 |
| 7 | unit | 活性单位 | string | μg/mL、ng/mL、nM、μM、% ；统一用 μ 字符 | 缺失填 unknown |
| 8 | reference | 来源引用 | string | 格式："论文标题 \| DOI:xxx" 或 "数据库名 \| 记录链接" | 不允许缺失（无来源不入库） |
| 9 | source_level | 来源等级 | enum | A / B / C / D（见 Source_Quality_System.md） | 不允许缺失 |
| 10 | confidence | 记录置信度 | enum | high / medium / low（见第 4 节） | 不允许缺失 |
| 11 | task_type | 任务标签 | enum | ATP_target / Antibacterial / Benchmark（每行有且仅有一个标签） | 不允许缺失 |

## 2. 主库扩展字段（ATP-Navigator公开训练数据库.csv 附加列）

| 字段 | 含义 | 说明 |
|------|------|------|
| compound_name | 化合物名称 | 无通用名时用文献编号；未知填 unknown |
| smiles | 原始 SMILES | 数据库原值或文献重建值（均经 RDKit 验证） |
| protein_id | 靶点数据库 ID | ChEMBL target ID；无则空 |
| docking_score / mmgbsa / admet | 计算/ADMET 数据 | 当前公开来源无数值，全部留空 |
| source_database | 来源库/文献标识 | 如 "ChEMBL"、"Literature (ACS Omega 2025)" |
| paper_title / DOI / year | 文献元数据 | 每行必填（综述行填综述 DOI） |
| data_type | 数据性质 | experimental / computational / predicted |
| assay_note | 实验方法备注 | 如 "broth microdilution (CLSI)"；无则空 |

## 3. activity_type 分类体系

**一级分类（按测量对象）**：

| 类别 | activity_type 实例 | 含义 | 对应 task_type |
|------|---------------------|------|----------------|
| 酶活性 | IC50 (ATP synthesis inhibition)、IC50 (ATP synthesis, inverted membrane vesicles)、Inhibition | 对分离酶/膜囊泡 ATP 合酶活性的直接抑制 | ATP_target |
| 结合亲和力 | Ki、Kd、IC50（BindingDB 结合测定）、EC50 | 小分子-蛋白结合实验 | Benchmark |
| 全细胞抗菌 | MIC、MBC | 肉汤微量稀释法等整菌抑制 | Antibacterial |
| 机制/脱靶 | IC50 (ETC inhibition)、IC50 (ETC, ACMA fluorescence) | 电子传递链抑制（脱靶机制评估） | Antibacterial |
| 细胞毒性 | MIC (cytotoxicity, XTT) | 哺乳动物细胞毒性（选择性窗口评估） | 不进入 v1 标准集（保留于主库） |
| 注释型 | （activity 为空） | 仅有靶点注释、无活性值 | 不进入 v1 标准集 |

**规则**：
- 不同一级分类**不合并统计**，activity_type 原样保留，不做统一改写。
- MIC 与 IC50 禁止互换；μg/mL 与 nM/μM 禁止直接比较（换算需分子量，作为下游清洗步骤而非入库时强制转换）。
- 截尾值（>64）与范围值（64-128）保留原始表述，禁止取中位数或极值替换。

## 4. confidence 置信度规则

| 等级 | 条件 |
|------|------|
| high | source_level ∈ {A, B} 且 activity_value、unit、reference 齐全 |
| medium | source_level = C 且有活性值；或 A/B 但个别字段缺失 |
| low | 仅注释、无活性值（此类记录不进入 v1 标准集） |

## 5. 通用缺失值规则

1. 不知道 → 填 **unknown**（主库扩展字段允许留空）。
2. 禁止编造化合物、论文、活性值、DOI。
3. 每条记录必须有 reference（无来源不入库）。
4. compound_id 在同一来源内唯一；同一化合物被不同来源收录时保留各行，由 canonical_smiles 建立跨来源关联。
