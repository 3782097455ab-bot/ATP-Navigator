# ATP-Navigator Generator Registry

更新时间：2026-08-28

| generator | version | status | Phase 16实际产出 | 边界 |
|---|---|---|---:|---|
| RDKit R-group enumeration | RDKit 2026.03.5 | available | 400 raw；400 valid；360 unique | 解释性芳香C–H位点R-group替换；保存模板、building block和attachment atom |
| CReM | unknown | unavailable | 0 | Python module未发现；未创建伪fragment database |
| REINVENT4 shadow | unknown | unavailable | 0 | executable与module未发现；未模拟生成结果 |

## 统一接口

`src/generation/backends.py`定义`generate()`、`validate()`、`canonicalize()`、`deduplicate()`、`get_provenance()`和`get_parent_mapping()`。`GeneratorRegistry`登记真实能力；`GeneratedCandidateRegistry`只接收具有完整parent、operation、structure和provenance hash的结构。

## RDKit冻结配置

- 配置：`configs/generation_phase16.json`；
- seed：IN-2和Hit3内部历史结构；Hit3的HTVS-1633 identity保持`unresolved`；
- generation method：`scaffold_preserving_R_group_enumeration`；
- reaction template：`aromatic_CH_Rgroup_substitution_v1`；
- 20个显式building blocks；每个产物保存attachment atom index；
- random seed：20260828；每seed raw target=200；
- 正式Registry：`results/phase16/generated_candidate_registry.csv`。

本登记表描述生成软件和可追溯性，不评价生物活性。
