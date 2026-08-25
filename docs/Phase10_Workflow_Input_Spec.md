# ATP-Navigator Phase 10 Workflow Input Specification

版本：`ATP-Navigator_Phase10_Input_v1.0`

## 1. 最小字段

| 字段 | 必需 | 说明 |
|---|---|---|
| `compound_id` | 是 | 候选唯一ID；空值时系统根据canonical SMILES生成请求ID |
| `historical_alias` | 否 | Hit1、Hit3等历史别名 |
| `SMILES` | 是 | RDKit可解析结构；系统生成canonical isomeric SMILES与Murcko scaffold |
| `docking_score` | 是 | 同一批次、同一协议的Docking分数，lower-is-better |
| `mmgbsa_score` | 是 | 同一协议静态MM/GBSA，lower-is-better；不是实验活性 |
| `quickprop_features` | 是 | JSON对象；键使用冻结Model v3字段名，如`quickprop_qplogs` |
| `admet_features` | 是 | JSON对象；包含各预测端点及`admet_endpoint_sum` |
| `literature_features` | 否 | JSON对象；仅接收结构化可追溯特征，不接收自由文本作为数值标签 |
| `docking_features` | 否 | JSON对象；用于Model v3的E-model、energy、ligand efficiency等完整Docking字段 |
| `source` | 建议 | 候选表和计算协议来源 |

模板：`examples/candidate_input_template.csv`。

## 2. 自动计算

- canonical isomeric SMILES；
- Murcko scaffold；
- Morgan fingerprint，radius=2、1024 bit、chirality开启；
- RDKit 16项结构描述符；
- 与Dataset v1.0中55个去重直接ATP assay参考结构的最大Tanimoto相似度；
- 保留的Model v2外部抗菌/ATP子模型prior；
- Frozen Model v3输入完整性检查。

## 3. 模型门控

- 1128个冻结特征全部存在：调用`Model_v3_full_frozen`；
- 特征不完整但SMILES有效：仅调用`Model_v2-A_structure_only_fallback`；
- SMILES无效：不运行模型；
- Decision Engine任一必需计算分量缺失：`final_score=unknown`，不对剩余权重重新归一化。

这种降级是显式的。系统不会用0、平均值或模型预测填充缺失的Docking、MM/GBSA、ADMET或实验结果。

## 4. 实验字段

如果输入未提供可追溯实验结果，以下字段固定为：

```text
experimental_ATP_inhibition = unknown
experimental_MIC = unknown
experimental_toxicity = unknown
```

Phase 10不会把结构模型、外部prior、Docking或MM/GBSA改写为实验值。

## 5. 分数语义

- `model_score`：对静态MM/GBSA计算排序任务的模型输出，lower-is-better；
- `binding_score`、`ATP_score`、`antibacterial_score`、`drug_score`：当前输入批次内0–100相对分量；
- `final_score`：研究profile条件下的批次相对决策分数；
- `P(Top-k)`：权重分布条件下进入Top-k的频率；
- 以上均不是活性概率或实验成功率。

