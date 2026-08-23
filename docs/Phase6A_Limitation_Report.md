# ATP-Navigator Phase 6A Limitation Report

## 已确认限制

1. 样本只有17个，且来自经过筛选的候选集合，不代表完整化学空间。
2. 权重敏感性只能说明规则在指定A-D场景内的排名稳定程度，不能证明真实活性预测有效。
3. 四个决策分量并非相互独立：Binding含Model v3、Docking和静态MM/GBSA；Model v3本身以静态MM/GBSA为计算标签。
4. ATP target和antibacterial分量含外部模型prior，存在organism、assay和chemical-domain shift。
5. Drug-likeness包含启发式描述符阈值和预测ADMET，不是实验安全性。
6. Final Score采用批内rank percentile，候选集合变化时分数和排名可能改变，不能直接跨批次比较。
7. 当前没有MIC、ATP enzyme inhibition、实验毒性或独立前瞻性结果；所有这些实验状态仍是`unknown`。
8. Dataset v1.0外部Layer 1/2与17个内部候选精确结构重叠为0；当前external benchmark可评价条目为0。
9. 消融或权重场景的Top候选变化只能解释决策规则依赖性，不能选择“实验上最佳”的公式。
10. Phase 6A没有形成Model v4，也没有产生新的监督性能指标。

## 禁止性解释

- 不得把场景稳定性写成实验验证；
- 不得把外部prior写成内部候选MIC/IC50；
- 不得把Phase 5/6A分数回流成监督标签；
- 不得用当前17候选内的高相关性声称跨项目泛化；
- 不得将`not_evaluable` benchmark描述为通过验证。

## 解除限制所需数据

- 对预先冻结候选和评价方案取得同协议MIC及ATP enzyme inhibition实验；
- 记录毒性、选择性、溶解度和稳定性实验；
- 建立独立、未参与权重选择的前瞻性候选集；
- 在单一endpoint、organism/strain、unit和assay条件下积累至少可计算相关性的候选级外部/实验匹配数据。
