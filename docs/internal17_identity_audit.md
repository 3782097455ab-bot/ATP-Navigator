# Internal 17 + IN-2 Identity Audit

日期：2026-08-28

## 审计结论

- 查询结构：18（Hit1–Hit17 + IN-2）；HTVS结构：1633；
- exact query：1；unresolved：17；
- related mapping只说明结构或历史关系，不升级为exact structure；未按名称、排名或相邻行猜测。

## 分层结果

| query | relation | matched HTVS | exact | confidence | notes |
|---|---|---|---|---|---|
| IN-2 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit1 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit2 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit3 | unresolved | — | false | low | aliases 466, ATP-CHAR-466, ATP-Top1-MD2 and Top-3 were searched; none map to an HTVS1633 code; no exact/related structure key or traceable historical HTVS ID found |
| Hit4 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit5 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit6 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit7 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit8 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit9 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit10 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit11 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit12 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit13 | exact_canonical | ATP-HTVS-AC71774ACC4B | true | high | historical aliases searched=91074;91074-2;rxn512b____EMOL44391395____EMOL720738____EMOL50155899; historical HTVS matches=ATP-HTVS-AC71774ACC4B; alias 91074 is directly present as an HTVS compound_code and independently supports the structural relation |
| Hit14 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit15 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit16 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |
| Hit17 | unresolved | — | false | low | no exact/related structure key or traceable historical HTVS ID found |

## 关键别名审计

- Hit3：`466`、`ATP-CHAR-466`、`ATP-Top1-MD2`、`Top-3`可在项目映射中相互关联，但没有可追溯HTVS-1633 compound code，因此仍为unresolved；
- Hit13：`91074`直接匹配HTVS compound code，且结构层同时满足exact canonical；若多个HTVS pose/variant共享相同结构，全部保留，不按rank挑成唯一身份；
- IN-2：是确认的外部/项目参考结构，但未发现其属于HTVS-1633的可追溯记录。

## 数据边界

本审计属于compound identity、target annotation和provenance QC，不产生生物活性标签，不修改历史Docking/MMGBSA或模型。
