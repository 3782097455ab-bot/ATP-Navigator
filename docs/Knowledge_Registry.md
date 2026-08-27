# ATP-Navigator Knowledge Registry

更新时间：2026-08-27

本登记表记录会影响计算协议、数据解释或决策边界的知识来源。它不是训练标签表；论文、历史项目文件和数据库说明中的文字不能自动转化为候选实验结果。

## 1. 项目内部方法与协议知识

| knowledge_id | 来源 | 支持内容 | 文件位置 | 当前用途 | 限制 |
|---|---|---|---|---|---|
| KNOW-ATP-HIST-001 | 原始Schrödinger VSW/受体/参考配体/SiteMap资产与项目PPT | 7P3W e/g受体、历史IN-2 pose、Fo界面位点和VSW gridbox来源 | `configs/projects/ab_atp_synthase/vina_7p3w_v1/protocol_provenance.json` | 冻结`vina_7p3w_v1`的来源审计 | Vina与历史Glide不等价；历史文件不证明候选生物活性 |
| KNOW-ATP-PROTOCOL-001 | Phase 13真实开放工具链验证 | 受体转换、ligand preparation、Vina参数、parser和pose QC合同 | `configs/projects/ab_atp_synthase/vina_7p3w_v1/` | Phase 14全库同协议Vina证据 | 只允许协议内比较；不得写入Glide字段 |
| KNOW-ATP-ENDPOINT-001 | Dataset v1/v2数据字典、Model Input Spec与QC | MIC、ATP activity、Docking、静态MM/GBSA、MD/MMGBSA和细胞毒性端点隔离规则 | `docs/ATP_Navigator_Model_Input_Spec.md`、`docs/Label_Policy.md` | 数据路由、模型和Decision Agent门禁 | 语义一致性、target annotation、endpoint segregation和provenance QC；不属于生物安全或临床叙事 |

## 2. 外部ATP合酶实验知识

以下来源已经在外部数据release及文献资产中登记。它们支持ATP synthase相关结构—实验端点知识，不能被解释为内部17候选的实验验证。

| knowledge_id | DOI/URL | 数据角色 | 本项目位置 | 主要限制 |
|---|---|---|---|---|
| KNOW-ATP-LIT-001 | `https://pmc.ncbi.nlm.nih.gov/articles/PMC12509006/` | ATP synthase inhibitor source evidence | `data/external/releases/release_v1_624c8b2309f4/` | assay、organism、unit必须保持分层 |
| KNOW-ATP-LIT-002 | `https://pmc.ncbi.nlm.nih.gov/articles/PMC12091843/` | ATP synthase inhibitor source evidence | 同上 | 不与内部MM/GBSA合并为同一label |
| KNOW-ATP-LIT-003 | `10.1021/acsinfecdis.3c00317` / `PMC10714390` | IN-2及相关ATP synthesis assay知识 | 同上 | 外部实验端点不是内部候选实验结果 |
| KNOW-ATP-LIT-004 | `10.1021/acsmedchemlett.3c00480` / `PMC10789121` | ATP synthesis inhibitor SAR知识 | 同上 | 结构与编号需服从release中的identity/QC记录 |
| KNOW-ATP-LIT-005 | `PMC9386795` | ATP synthase inhibitor source evidence | 同上 | 只使用有来源、结构和endpoint追溯的记录 |

## 3. 证据解释规则

1. 计算协议知识用于生成或解释计算证据，不产生实验标签；
2. 文献活性只属于其原assay、organism、unit和来源层；
3. target annotation错误、端点混合、身份冲突和来源缺失统一登记为数据语义/来源QC问题；
4. `unknown`不得由文献叙述、模型预测或相邻分子的结果填充；
5. 新增方法学知识必须记录正式来源、实际接入状态和未完成能力。

## 4. Phase 14登记状态

- `vina_7p3w_v1`已冻结并用于HTVS-1633真实批处理：1628 success、5个内存型failed；
- 1628个成功结果只登记为平行Vina计算证据，共4884条工具/结果/pose QC记录；
- Phase 14未训练模型、未新增实验活性、未改变Decision Engine评分逻辑；
- Glide/Vina低相关和Top-k无重叠只作为协议不确定性知识，不作为生物活性结论；
- 最终success/fail、协议分歧和scaffold统计以`results/phase14/`完成态文件为准。
