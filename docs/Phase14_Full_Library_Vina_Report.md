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
- success：1628；failed：5；恢复启动时cache hit：1468；
- 恢复阶段真实新执行：165；最终汇总cache hit：1628；
- pose QC pass：1628；
- invalid structure：0；preparation failed：0；
- Vina failed：5；pose QC failed：0。

执行采用50–100条批次、content-addressed cache、失败结果保留和显式`retry_failed`。实测20并发触发Windows页面文件/内存错误，随后固定16并发完成剩余队列；最终仍有5条因`insufficient memory`终止。它们被保留为明确failed，未为追求100%成功率自动重试。该限制属于计算资源约束，不属于分子QC结果。

### 失败审计

- `ATP-HTVS-E82D7E524403`：vina_failed / vina_failed:return_code_1；stderr=`Error: insufficient memory!`；technical_recoverable=true；retry_performed=false。
- `ATP-HTVS-F716E067906C`：vina_failed / vina_failed:return_code_1；stderr=`Error: insufficient memory!`；technical_recoverable=true；retry_performed=false。
- `ATP-HTVS-F79E64AB5B06`：vina_failed / vina_failed:return_code_1；stderr=`Error: insufficient memory!`；technical_recoverable=true；retry_performed=false。
- `ATP-HTVS-F89CD1E9CA34`：vina_failed / vina_failed:return_code_1；stderr=`Error: insufficient memory!`；technical_recoverable=true；retry_performed=false。
- `ATP-HTVS-F8D25E752EF8`：vina_failed / vina_failed:return_code_1；stderr=`Error: insufficient memory!`；technical_recoverable=true；retry_performed=false。

## 3. 全库结构与协议比较

- 成功候选：1628；Bemis–Murcko scaffolds：564；
- Morgan/Butina chemical-space clusters：928；
- Vina affinity分布：min=-10.553，P5=-9.15165，median=-8.0335，mean=-7.902335995085996，P95=-6.113200000000002，max=-5.011 kcal/mol；
- isolated scaffolds：320；largest scaffold size：83；
- Glide/Vina matched subset：1628；Spearman=0.1644331085911322；Kendall=0.10971583402428257；
- Top5 overlap=0；Top10 overlap=0。

这些量只描述两个计算协议的排序一致性，不是实验验证，也不能据此断言候选具有生物活性。

## 4. 内部候选位置

Hit3未能通过exact canonical SMILES映射到HTVS-1633，因此全库rank、percentile和scaffold-relative rank均为unknown；未使用名称猜测补齐。

在Hit1–Hit17和IN-2共18个查询结构中，exact canonical SMILES映射数为1。其余映射状态见`results/phase14/internal17_global_position.csv`。所有无法确认的身份保持`not_present_in_htvs1633`或`unknown`。

- 已确认映射：Hit13 → `ATP-HTVS-5658ECC62B06`；Vina rank=1077.0，percentile=33.866，scaffold-relative rank=11.0，affinity=-7.672 kcal/mol。

## 5. 最大协议分歧

- `ATP-HTVS-CF9A421CD50D`：Vina rank=41，Glide rank=1608，rank delta=-1567，class=extreme_disagreement。
- `ATP-HTVS-898AE5CA69D9`：Vina rank=86，Glide rank=1623，rank delta=-1537，class=extreme_disagreement。
- `ATP-HTVS-9505CBC4E7EE`：Vina rank=27，Glide rank=1550，rank delta=-1523，class=extreme_disagreement。
- `ATP-HTVS-450A55DE989E`：Vina rank=103，Glide rank=1625，rank delta=-1522，class=extreme_disagreement。
- `ATP-HTVS-1449F4F4BA71`：Vina rank=1540，Glide rank=20，rank delta=1520，class=extreme_disagreement。

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

- 完整历史测试与Phase 14新增测试：120/120通过；
- 24个受保护模型文件：阶段前后SHA-256 mismatch=0；
- 最终QC、Registry、排名和图表均从保存的真实结果缓存重建，未在finalization阶段执行`retry_failed`。
