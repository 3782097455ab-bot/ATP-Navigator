# ATP-Navigator Dataset Audit v1

审计对象：`ATP-Navigator公开训练数据库.csv`  
源文件 SHA-256：`8B7127C6CDDCFDEBBAAB68F1537D5CC5A7C0E4163C82269D069F4525B977D06B`  
配套说明 SHA-256：`B8ED1DBF0361CCBEB7A62DB70E66AB79AB16B2ED8D6B8039A66249D261F00905`  
审计原则：配套说明仅作为来源声明；本报告以 CSV 实际内容为准，不把说明中的质量声明视为已独立验证。

## 1. 原始数据规模

| 项目 | 实际值 |
|---|---:|
| 数据行 | 6,777 |
| 字段 | 18 |
| 唯一 `compound_id` | 2,313 |
| 唯一非空 SMILES | 2,311 |
| 唯一 target | 11 |
| 唯一 organism | 30 |
| 唯一非空 protein ID | 6 |
| 唯一 DOI | 246 |
| `data_type=experimental` | 6,777 |

“6,777 行”是 assay/evidence 记录数，不是独立化合物数，也不是可直接合并的同质标签数。

## 2. 靶点分布

| target | 行数 |
|---|---:|
| whole-cell antibacterial activity (Acinetobacter baumannii) | 2,788 |
| whole-cell antibacterial activity (Escherichia coli) | 1,200 |
| whole-cell antibacterial activity (Pseudomonas aeruginosa) | 1,200 |
| whole-cell antibacterial activity (Klebsiella pneumoniae) | 1,199 |
| whole cell | 219 |
| F1Fo-ATP synthase (Fo a/c interface) | 94 |
| whole cell (cytotoxicity) | 30 |
| F1Fo-ATP synthase (M. tuberculosis) | 27 |
| electron transport chain | 9 |
| bacterial electron transport chain (ACMA assay) | 6 |
| 30S ribosomal subunit (aminoglycoside control) | 5 |

其中 whole-cell MIC 是表型抗菌数据，不能因为化合物来自 ATP 合酶论文就自动解释为 ATP 合酶直接抑制标签。细胞毒性、ETC 和核糖体对照也必须保持独立任务语义。

## 3. Organism 分布

| organism | 行数 |
|---|---:|
| Acinetobacter baumannii | 2,788 |
| Escherichia coli | 1,203 |
| Pseudomonas aeruginosa | 1,200 |
| Klebsiella pneumoniae | 1,199 |
| Acinetobacter baumannii ATCC 17978 | 51 |
| Pseudomonas aeruginosa ATCC BAA 2108 (MDR) | 37 |
| Acinetobacter baumannii BAA 1605 (MDR) | 34 |
| Homo sapiens HEK 293 | 30 |
| Mycobacterium tuberculosis | 27 |
| Pseudomonas aeruginosa ATP synthase in E. coli DK8/pASH20 vesicles | 25 |
| Pseudomonas aeruginosa 9027 | 20 |
| Pseudomonas aeruginosa ATCC BAA 2109 (MDR) | 20 |
| Pseudomonas aeruginosa ATCC BAA 2110 (MDR) | 20 |
| Pseudomonas aeruginosa PΔ6 (efflux knockout) | 20 |
| Acinetobacter baumannii ATCC 1605 (MDR) | 17 |
| Acinetobacter baumannii ATCC 17978 (inverted membrane vesicles) | 16 |
| Pseudomonas aeruginosa PAO1 | 12 |
| Pseudomonas aeruginosa PAO1 delta6 (efflux-deficient) | 10 |
| Pseudomonas aeruginosa (inverted membrane vesicles) | 9 |
| 缺失 | 7 |
| Pseudomonas aeruginosa PAO1 (wild type) | 6 |
| Staphylococcus aureus (MSSA) | 6 |
| Pseudomonas aeruginosa PAO1 derivative 9027 | 4 |
| Acinetobacter baumannii BAA-2108 | 3 |
| Acinetobacter baumannii BAA-2109 | 3 |
| Acinetobacter baumannii BAA-2110 | 3 |
| Escherichia coli ATCC 25922 | 3 |
| broad spectrum (Gram-positive and Gram-negative) | 1 |
| Mycobacterium abscessus CIP104536T | 1 |
| Staphylococcus aureus small colony variants (SCV) | 1 |
| Streptococcus pyogenes | 1 |

物种名、菌株名、重组囊泡体系和宿主细胞目前混在同一个 `organism` 字段中。Dataset v1.0 保留原文，不自行拆分；后续应增加 organism、strain、assay system 三个独立字段。

## 4. Activity type 与单位分布

| activity_type | 行数 |
|---|---:|
| MIC | 6,648 |
| IC50 (ATP synthesis inhibition) | 41 |
| MIC (cytotoxicity, XTT) | 30 |
| IC50 | 17 |
| IC50 (ATP synthesis, inverted membrane vesicles) | 9 |
| IC50 (ETC inhibition) | 9 |
| 缺失 | 7 |
| Activity | 7 |
| IC50 (ETC, ACMA fluorescence) | 6 |
| Inhibition | 3 |

| unit | 行数 |
|---|---:|
| ug/mL | 6,444 |
| μg/mL | 289 |
| nM | 17 |
| % | 10 |
| ng/mL | 10 |
| 缺失 | 7 |

`activity_value` 的原始字符串中有 6,648 个精确数值、114 个比较符值、8 个范围值、7 个缺失值。比较符和范围均被保留，没有强制转换为伪精确数值。Dataset v1.0 仅把 `μg/mL`/`µg/mL` 统一写成 `ug/mL`，不改变数值。

## 5. 字段缺失

| 字段 | 缺失数 | 缺失率 |
|---|---:|---:|
| compound_id | 0 | 0.00% |
| compound_name | 0 | 0.00% |
| smiles | 0 | 0.00% |
| target | 0 | 0.00% |
| protein_id | 363 | 5.36% |
| organism | 7 | 0.10% |
| activity_type | 7 | 0.10% |
| activity_value | 7 | 0.10% |
| unit | 7 | 0.10% |
| docking_score | 6,777 | 100.00% |
| mmgbsa | 6,777 | 100.00% |
| admet | 6,777 | 100.00% |
| source_database | 0 | 0.00% |
| paper_title | 0 | 0.00% |
| DOI | 0 | 0.00% |
| year | 0 | 0.00% |
| data_type | 0 | 0.00% |
| assay_note | 6 | 0.09% |

公开库不能支持公开 Docking/MMGBSA/ADMET 监督训练，因为对应三列实际全部为空。这是数据现状，不通过填充值补齐。

## 6. 重复、身份与来源风险

1. 原始18字段存在35条完全重复记录，分布于26个重复组；Dataset v1.0 只保留每组第一条。
2. `WSA236` 和 `WSA238` 各对应两种不同 SMILES。无法从当前资料确定正确结构，因此去重后涉及的24条记录全部隔离，不进入统一训练表。
3. 有4组不同 compound ID 使用完全相同的 SMILES：
   - `CHLORAMPHENICOL` / `CHEMBL130`；
   - `WARD2024-2` / `FRAUNFELTER2023-5`；
   - `FRAUNFELTER2023-1` / `STEED2022-22`；
   - `CHEMBL162598` / `CTRL-DCCD`。
   这些别名记录被保留，但数据划分必须按 canonical SMILES/结构组分组，不能按 compound ID 随机拆分。
4. 配套说明称 SMILES 已由 RDKit 标准化，但本次运行环境没有重新执行 RDKit canonicalization。因此 Dataset v1.0 的 `canonical_smiles` 是“来源声明的 canonical SMILES”，不是本次独立重算结果。
5. 所有记录都有 DOI 和来源字段，但本次没有逐条回到 ChEMBL/API/论文复核。因此公开数据默认标记为 `medium_source_traceable_unverified`，不标记为最高置信度。

## 7. 三层处理结果

公开数据清洗过程：6,777 原始行 − 35 完全重复行 − 24 身份冲突行 = 6,718 条可注册公开记录。

| 数据层 | Dataset v1.0 行数 | 形成规则 |
|---|---:|---|
| Layer 1：General antibacterial | 6,355 | ChEMBL 且 target 非 ATP synthase；全部为 MIC |
| Layer 2：ATP synthase specific | 363 | ATP 合酶系列文献记录 + ChEMBL ATP synthase 记录；保留 MIC、IC50、ETC、细胞毒性和对照的不同语义 |
| Layer 3：Internal ATP-Navigator | 36 | 17 静态 MM/GBSA + 17 Glide docking + 2 个 MD/MMGBSA 1000帧均值 |
| 合计 | 6,754 | 2,329 个 compound ID；2,324 个非空 SMILES |

Layer 3 中 Hit3 已通过现有映射表与 `ATP-SMI-874C2DE25FE4`、`ATP-HIT-MD-001`、`ATP-Top1-MD2` 建立 confirmed 映射。IN-2 的 MD 系统仅有来源别名链，结构链接未达到同等置信度，因此该1条记录保留空 SMILES并标记为 `medium_internal_alias_structure_unresolved`。

内部 HTVS 有4,373个 pose/state、1,633个 canonical ID，但当前 `molecules.csv` 对这些 ID 没有 SMILES，且可读数据只覆盖部分原始分片。因此这些记录没有被强行加入 Dataset v1.0；后续完成结构恢复与 pose 聚合后再进入 Layer 3。

## 8. Dataset v1.0 完整性

最终 CSV 为12列、6,754行；没有完全重复输出行，没有同一 compound ID 对应多个非空 SMILES，也不包含被隔离的 `WSA236`/`WSA238`。其中 protein ID 缺失336行、organism/activity type/activity value各缺失4行、unit缺失40行、canonical SMILES缺失1行。缺失值均保留为空，不生成虚假标签。
