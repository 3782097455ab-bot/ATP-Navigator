# Phase 14 Full-library 7P3W Vina Evidence Report

日期：2026-08-28  
状态：完成；未训练或修改任何历史模型

## 1. 冻结协议与执行边界

- protocol：`vina_7p3w_v1`，receptor=7P3W；
- box center=[198.147968, 182.436946, 155.933369] Å；box size=[25.991257, 25.991257, 25.991257] Å；
- Vina 1.2.7，exhaustiveness=16，num_modes=9，energy_range=3，seed=20260827，CPU/job=1；
- protocol文件hash：`19ff755d00741e9d2ec60c732f24dea6a28fd4f478940b28dbc11bea68c3fe36`；Evidence Registry冻结protocol hash：`5b930c3ba77cbe9b622c4e285cab89f721bedf3693e1200e98d1a4e07dc4a403`；
- 两个hash覆盖对象不同：前者为相对路径manifest，后者为Registry中解析后的冻结记录；关键科学字段已逐项一致性检查。

Vina结果只登记为独立`vina_affinity`计算证据，不写入Glide字段，不作为生物活性或实验标签。

## 2. 全库执行与QC

- total/eligible：1633/1633；processed：1633；
- Phase 14初始终态为1628 success、5 failed；Phase 14.1仅对5个technical-recoverable内存失败执行显式重试；
- Phase 14.1最终态：success=1633、failed=0；重试启动时cache hit=1628，真实新执行=5，max_workers=2；
- pose QC pass：1633；
- invalid structure：0；preparation failed：0；
- Vina failed：0；pose QC failed：0。

执行采用50–100条批次、content-addressed cache、失败结果保留和显式`retry_failed`。实测20并发触发Windows页面文件/内存错误，随后固定16并发完成主队列；Phase 14保留5条`insufficient memory`失败。Phase 14.1经人工授权后，在完全相同的冻结科学协议下以2并发只重试这5条，5/5成功。该修复只改变执行资源并发，不改变receptor、box、ligand preparation、exhaustiveness、num_modes、energy_range或seed。

### 失败审计

- Phase 14原5条内存失败审计和重试前summary保存在`results/phase14/audit/history/`；
- Phase 14.1最终失败数为0，未发生结构级、协议级或pose QC失败。

## 3. 全库结构与协议比较

- 成功候选：1633；Bemis–Murcko scaffolds：565；
- Morgan/Butina chemical-space clusters：929；
- Vina affinity分布：min=-10.553，P5=-9.1464，median=-8.029，mean=-7.899842008573179，P95=-6.056200000000004，max=-5.011 kcal/mol；
- isolated scaffolds：321；largest scaffold size：84；
- Glide/Vina matched subset：1633；Spearman=0.16871901379218926；Kendall=0.11266477813435863；
- Top5 overlap=0；Top10 overlap=0。

这些量只描述两个计算协议的排序一致性，不是实验验证，也不能据此断言候选具有生物活性。

## 4. 内部候选位置

Hit3未能通过exact canonical SMILES映射到HTVS-1633，因此全库rank、percentile和scaffold-relative rank均为unknown；未使用名称猜测补齐。

在Hit1–Hit17和IN-2共18个查询结构中，exact canonical SMILES映射数为1。Phase 14.1进一步按exact canonical、InChIKey、connectivity、neutral parent、tautomer、stereochemistry和历史ID分层审计：Hit13为exact canonical，其余17个unresolved；相关映射不会升级为exact。详见`results/phase14_1/internal17_identity_audit.csv`和`docs/internal17_identity_audit.md`。

- 已确认映射：Hit13 → `ATP-HTVS-FBBE5B904E6C`；Vina rank=1077.0，percentile=34.069，scaffold-relative rank=1.0，affinity=-7.676 kcal/mol。

## 5. 最大协议分歧

- `ATP-HTVS-CF9A421CD50D`：Vina rank=41，Glide rank=1612，rank delta=-1571，class=extreme_disagreement。
- `ATP-HTVS-898AE5CA69D9`：Vina rank=86，Glide rank=1628，rank delta=-1542，class=extreme_disagreement。
- `ATP-HTVS-450A55DE989E`：Vina rank=103，Glide rank=1630，rank delta=-1527，class=extreme_disagreement。
- `ATP-HTVS-9505CBC4E7EE`：Vina rank=27，Glide rank=1554，rank delta=-1527，class=extreme_disagreement。
- `ATP-HTVS-1449F4F4BA71`：Vina rank=1543，Glide rank=20，rank delta=1523，class=extreme_disagreement。

最大分歧用于下一步证据获取优先级设计，不表示任一协议更接近真实活性。

## 6. 主要输出

- `full_library_vina_ranking.csv`：Vina全库排序、percentile和scaffold-relative rank；
- `glide_vina_protocol_disagreement.csv`：独立协议rank delta与分歧类别；
- `vina_scaffold_analysis.csv`：scaffold coverage与scaffold内最优候选；
- `evidence_completeness_matrix.csv`：逐候选结构、准备、Vina和pose QC状态；
- `internal17_global_position.csv`：内部候选的严格结构映射；
- `failed_candidate_audit.csv/json`：逐条失败阶段、原因、日志摘要和重试建议；
- `evidence_registry_export.csv`、`evidence_registry_summary.csv`：真实工具证据导出与分组计数；
- `figures/`：全部由真实计算结果生成的统计图。

## 7. 限制

- Docking score受受体构象、质子化、搜索框和scoring function影响；
- 当前Vina与历史Glide不是等价协议，协议分歧应作为不确定性证据；
- 未新增MIC、ATP酶抑制或毒性实验结果；
- Model v0–v4-alpha共24个受保护文件hash保持不变。

## 8. 验证

- Phase 14原完整测试：120/120通过；Phase 14.1增加重试与身份审计回归测试，最终总数以Phase 14.1验收记录为准；
- 24个受保护模型文件：阶段前后SHA-256 mismatch=0；
- 最终QC、Registry、排名和图表均从保存的真实工具结果重建；只有经人工授权的Phase 14.1五条技术失败执行了`retry_failed`。
