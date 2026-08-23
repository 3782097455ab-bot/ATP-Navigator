# ATP-Navigator Phase 6B External Validation Report

生成模块：`ATP-Navigator_Phase6B_External_Benchmark_v1.0`

## 结论

External Benchmark Pipeline已经建立并成功执行数据标准化、结构去重和Morgan2048 fingerprint计算。当前ATP-Navigator可评分外部集合为**empty**，因此`benchmark_ranking.csv`只有表头，`benchmark_metrics.csv`明确记录`status=empty`，没有生成虚假相关性或实验结果。

## 输入审计

- 输入文件：`data/dataset_v1.0/ATP_Navigator_Dataset_v1.csv`
- 输入SHA-256：`88df875d4c9bd65bbb5bf16c6608d57c5947b5fbb8ec58cc053bb8c9b9724bb0`
- 原始记录：363
- RDKit可解析结构记录：363
- 缺失或无效结构记录：0
- 去重后唯一结构：109
- 合并的重复结构记录：254
- 与已知Model v2外部知识训练结构重叠：109

### Activity type分布

| activity_type | records |
|---|---:|
| MIC | 245 |
| IC50 (ATP synthesis inhibition) | 35 |
| MIC (cytotoxicity, XTT) | 30 |
| IC50 | 17 |
| IC50 (ATP synthesis, inverted membrane vesicles) | 9 |
| IC50 (ETC inhibition) | 7 |
| Activity | 7 |
| IC50 (ETC, ACMA fluorescence) | 6 |
| unknown | 4 |
| Inhibition | 3 |

MIC、IC50、细胞毒性、Activity和Inhibition保持不同端点，不作为同一个label或metric混合。

## Pipeline

1. 接收`compound_id, SMILES, target, organism, activity_type, activity_value, reference`；`unit`为推荐可选字段；
2. 使用RDKit生成isomeric canonical SMILES并记录无效结构；
3. 按canonical SMILES去重，同时保留来源compound ID、端点、organism和reference集合；
4. 计算Morgan fingerprint：radius=2、nBits=2048；
5. 调用未修改的Phase 5 Decision Engine。只有已具备完整Phase 5计算证据的结构才能取得分数；
6. 仅对成功评分的结构生成ranking；
7. metric只在外部训练结构不重叠、实验值为精确数值、且target/organism/activity type/unit/direction单一的stratum内计算。

## 当前评分与验证状态

- 可评分唯一结构：0
- ranking行数：0
- 成功评价metric strata：0
- 当前状态：`empty`

现有Layer 2结构是Model v2外部知识数据来源，不能作为完全独立验证集；同时这些外部分子没有内部Docking、静态MM/GBSA、Model v3和完整ADMET等Decision Engine必需证据。因此不修改评分逻辑、不补假特征，分数保持空值。

## 输出

- `results/phase6B/standardized_benchmark_compounds.csv`：去重结构、Morgan fingerprint、训练重叠和评分状态；
- `results/phase6B/benchmark_ranking.csv`：仅成功评分的外部候选；当前empty；
- `results/phase6B/benchmark_metrics.csv`：验证metric及不可评价原因；当前empty。

## 不变性

- `src/decision_engine.py` SHA-256：`98c638f13c111052d08dd6e144375350803a2f9a15b7c10c23e47a039c98e0d8`
- `scoring_config.json` SHA-256：`bf5a3773123025da8b1271a113342884eaa9acf1e0a49c0828bbcf14a84e3056`
- 未训练或修改Model v0-v3；
- 未改变Phase 5 Decision Engine评分公式或权重；
- 公开activity只用于未来验证分层，不进入训练或当前评分。

## 下一步满足可评价条件所需数据

对新的独立候选，必须先按冻结协议生成Decision Engine所需计算证据，再取得与训练数据隔离的同endpoint、organism、unit和assay实验结果。验证集在评分和指标方案冻结后才能打开使用。
