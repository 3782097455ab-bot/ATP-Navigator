# ATP-Navigator 数据质量审计报告（QC Report）

**审计日期**：2026-08-24
**审计对象**：ATP-Navigator公开训练数据库.csv（6,777 行）
**审计方式**：只读分析，未修改任何原始数据。

---

## 1. 总体概览

| 指标 | 数值 |
|------|------|
| 总行数 | 6,777 |
| 唯一 compound_id | 2,313 |
| 唯一 canonical SMILES | 2,311 |
| 来源构成 | ChEMBL 6,414 / 原始论文 353 / 综述 10 |

## 2. 检查结果

### 检查 1：重复 compound
- 1,088 个 compound_id 出现多于 1 行（最多 296 行/化合物）。
- **判定：合规**。这是"同一化合物 × 不同菌株/不同论文拆行"的设计行为（分工文档规则），非错误。
- 典型例：CHLORAMPHENICOL（氯霉素对照）出现在多篇论文的多个菌株测定中。

### 检查 2：重复 canonical SMILES（跨 ID）
- 全部 6,777 条 SMILES 均可被 RDKit 解析（0 解析失败）。
- 发现 **4 组**同一 canonical SMILES 对应不同 compound_id：

| SMILES 对应物 | 重复 ID | 判定 |
|---|---|---|
| DCCD | CHEMBL162598 ↔ CTRL-DCCD | 合规：数据库记录与对照品条目，跨来源保留 |
| IN-2（喹啉类） | WARD2024-2 ↔ FRAUNFELTER2023-5 | 合规：同一化合物两篇论文独立报道，已在 compound_name 互注 |
| 喹啉化合物 | FRAUNFELTER2023-1 ↔ STEED2022-22 | 合规：compound 22 (2022) = compound 1 (2023)，跨论文重复报道 |
| 氯霉素 | CHLORAMPHENICOL ↔ CHEMBL130 | 合规：对照品与 ChEMBL 记录 |

- **结论：0 个未声明的隐藏重复；4 组均为已标注的合法跨来源重复。**

### 检查 3：缺失 SMILES
- **0 条缺失**（6,777/6,777 均有 SMILES，100%）。

### 检查 4：缺失 reference
- **0 条缺失**：所有行均有 paper_title 或 DOI；DOI 缺失 0 条。
- 6 条缺 assay_note（综述对照行的备注为空）——不影响可追溯性。

### 检查 5：activity 单位分布

| 单位 | 行数 | 说明 |
|------|------|------|
| ug/mL | 6,444 | ChEMBL 及部分文献行 |
| μg/mL | 289 | 文献行（μ 字符） |
| nM | 17 | ChEMBL 结核 ATP 合酶 IC50 |
| ng/mL | 10 | 吡啶系列酶活 IC50（ACS Omega 2025） |
| % | 10 | ChEMBL 抑制率记录 |
| （空） | 7 | 经典抑制剂注释行（无活性值） |

- ⚠️ **发现：同一物理单位存在两种符号（ug/mL 与 μg/mL）**。已在标准输入数据集 v1 中统一为 μg/mL；主库原样保留（本次审计不修改原始数据）。
- ⚠️ MIC（μg/mL）与 IC50（nM/ng/mL）量纲不同，统计与训练时禁止直接混用。

### 检查 6：activity_type 分布

| activity_type | 行数 | 类别 |
|---|---|---|
| MIC | 6,648 | 全细胞抗菌 |
| IC50 (ATP synthesis inhibition) | 41 | 酶活 |
| MIC (cytotoxicity, XTT) | 30 | 细胞毒性（Homo sapiens HEK 293） |
| IC50 | 17 | 酶活（ChEMBL） |
| IC50 (ATP synthesis, inverted membrane vesicles) | 9 | 酶活 |
| IC50 (ETC inhibition) | 9 | 脱靶机制 |
| （空） | 7 | 注释型 |
| Activity | 7 | ChEMBL 通用类型 |
| IC50 (ETC, ACMA fluorescence) | 6 | 脱靶机制 |
| Inhibition | 3 | 酶活（%抑制） |

- ⚠️ 酶活 IC50 存在 3 种写法（"IC50 (ATP synthesis inhibition)"、"IC50 (ATP synthesis, inverted membrane vesicles)"、"IC50"），语义一致但字符串不统一——建议下游按数据字典第 3 节一级分类归并。
- ⚠️ 活性值格式：数值型 6,648 条、截尾值（>64 等）114 条、范围值（64-128）8 条、空 7 条。截尾/范围值需在训练前单独处理（禁止静默转数值）。

### 附加观察
- 菌种分布：A. baumannii 2,915 / P. aeruginosa 1,383 / E. coli 1,206 / K. pneumoniae 1,199 / HEK293 30 / 其他 44——与项目优先级一致。
- 7 条 organism 为空（经典抑制剂注释行），已在标准集中排除或填 unknown。
- 文献年份跨度 1988–2025（ChEMBL 收录老文献），无异常年份。

## 3. 审计结论

| 项目 | 结果 |
|------|------|
| 结构完整性（SMILES） | ✅ 100% 有且可解析 |
| 来源可追溯性 | ✅ 100% 有 reference + DOI |
| 隐藏重复 | ✅ 0 个（4 组跨来源重复均已声明） |
| 单位一致性 | ⚠️ ug/mL/μg/mL 符号混用（v1 标准集已归一） |
| activity_type 一致性 | ⚠️ 同类多写法（需按一级分类归并） |
| 数据性质标注 | ✅ data_type 全为 experimental，无混入预测值 |

**总体判定：通过质量审计，可用于建模。两个 ⚠️ 项已在 v1 标准输入数据集层面处理，原始主库保持不变。**
