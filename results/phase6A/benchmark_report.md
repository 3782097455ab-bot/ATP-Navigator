# ATP-Navigator Phase 6A External Benchmark Report

生成模块：`ATP-Navigator_Phase6A_Robustness_v1.0`

## 结论

当前没有可对17个内部候选实施独立外部性能评价的数据。`benchmark_results.csv`中的相关性字段保持空值，不把内部Docking、静态MM/GBSA、Model v3预测、外部prior或Phase 5 Final Score冒充外部实验真值。

## 已执行检查

| 外部知识层 | 外部记录数 | 与17候选精确canonical SMILES重叠 | 状态 |
|---|---:|---:|---|
| Layer 1 general antibacterial | 6355 | 0 | `not_evaluable` |
| Layer 2 ATP synthase specific | 363 | 0 | `not_evaluable` |

Dataset v1.0的Layer 3是本项目内部计算证据，已明确排除在external benchmark之外。Layer 1和Layer 2与内部候选均没有精确结构重叠，因此不能直接给内部候选赋MIC或IC50标签。

## 可复用验证接口

模块会检查可选文件`data/external/curated/phase6a_benchmark.csv`。最低字段为：

- `canonical_smiles`
- `endpoint`
- `activity_value`
- `unit`
- `direction`
- `evidence_type`
- `source`
- `reference`

只有`evidence_type=experimental`、与内部候选精确结构匹配、且endpoint/unit/direction构成单一可比stratum时才计算相关性；至少需要3个匹配候选。该文件永远只用于验证，不并入训练。

## 当前限制

- 无内部候选MIC、ATP enzyme inhibition或实验毒性结果；
- 无独立前瞻性候选集；
- 公开外部化合物与17候选不重叠；
- 因而当前benchmark状态是data availability audit，不是外部性能证明。
