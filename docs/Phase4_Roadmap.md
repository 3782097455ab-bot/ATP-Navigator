# ATP-Navigator Phase 4 Roadmap

更新日期：2026-08-22  
目标：提高候选优先级识别能力，优先解决数据质量和排序监督不足；不开发 GNN。

## 1. 当前基线结论

Phase 4 在 Dataset v0.2 的同一 17 个候选、11 个 Bemis–Murcko scaffold group 上完成严格对照。所有学习模型使用同一 leave-one-scaffold-group-out 协议；Model 0 为无训练的 Docking 直接排序。

| 模型 | Spearman | NDCG@5 | Top-5 enrichment | Hit recovery |
|---|---:|---:|---:|---:|
| Model 0 Docking | -0.532 | 0.275 | 0.68 | 0.20 |
| Legacy P1 LightGBM | 0.598 | 0.788 | 1.36 | 0.40 |
| Model 2 LightGBM regression | **0.752** | **0.777** | **1.36** | **0.40** |
| Model 3 LightGBM LambdaRank | 0.158 | 0.536 | 0.68 | 0.20 |
| Model 4 XGBoost ranker | -0.084 | 0.585 | 0.68 | 0.20 |

结论：直接排名目标没有改善 Top-5，反而从 2/5 降到 1/5。当前不升级默认模型，Model 2 继续作为主基线。该结果不证明 ranking objective 无效，只说明在 17 个样本、单一短 query 和高维输入下没有足够的 pairwise 监督。

RMSE 不用于 Model 3/4，因为 ranker 输出是任意尺度的 ranking utility。

## 2. 开发顺序

### P4.1 数据恢复与 v0.3 物化

交付条件：

- 恢复并核验 HTVS 004–006 完整分片；
- 建立 protocol/shard hash 清单；
- compound/variant 去重；
- 输出 Dataset v0.3 pose 表、compound 表、label manifest 和 split audit；
- 17 个严格 benchmark 候选默认从弱监督预训练中屏蔽。

Go/No-Go：若完整 HTVS 仍不可用，只物化 readable_shards 版本并明确命名，不称“全库”。

### P4.2 弱监督预训练

首轮只比较：

1. Model 2 preserved regression；
2. HTVS weak pretrain → 17 候选折内 fine-tune；
3. weak pretrain + confidence weight sensitivity。

弱标签首版仅用 protocol 内 Docking 排序；QuickProp 作为输入，不并入教师标签。评价仍使用 held-out MM/GBSA 排序，主指标为 NDCG@5、Top-5 recovered count 和 enrichment。

Go/No-Go：必须在冻结 split 上至少稳定恢复 3/5，且不降低 NDCG@5，才进入下一轮。单次 17 样本结果必须同时报告 bootstrap 区间和每个候选的 OOF 排名。

### P4.3 Pose interaction features

- 建立 pose 接触抽取器与 residue/type IFP；
- 先在 17 个 VSW pose 上做可解析率和覆盖审计；
- 只做 Model 2 + Pose-IFP 单独消融；
- persistent residues 由训练折内频率定义，不使用人工挑选名单。

Go/No-Go：身份、pose 和蛋白结构必须一一对应；若 VSW.maegz 不包含可重建的复合物坐标，则先恢复/导出 pose viewer 或 receptor–ligand complex 文件。

### P4.4 MD evidence layer

- 将 IN-2/Hit3 的逐帧接触与 1,000 条 MM/GBSA 结果标准化；
- 为损坏的 IN-2 H-bond 文件增加 corruption-aware parser 和拒绝行审计；
- 恢复完整 XTC 后抽样重算；
- 当前只进入候选证据卡，不进入训练矩阵。

Go/No-Go：至少获得多个候选、同一 MD 协议、身份确认的体系后，才将 MD 作为模型特征。

## 3. 评价协议

- 主任务：计算 MM/GBSA 候选排序，不是活性预测；
- 主指标：NDCG@5、Top-5 recovered count、Top-k enrichment；
- 次指标：Spearman；回归模型另报 RMSE；
- 模型选择：使用嵌套训练折或独立 validation，禁止在最终 17 条 OOF 上反复调参；
- 拆分：pose/variant 按 compound 合并，结构可用时按 scaffold 留组；
- 对照：Model 0、Legacy P1、Model 2 始终保留；
- 负结果：完整保存，不通过重新命名或删除历史结果制造“提升”。

## 4. 比赛展示边界

可以展示：真实 ATP 合酶虚拟筛选案例、传统计算链、可追溯候选、严格 OOF 对照、SHAP、弱监督与交互特征路线。

不能展示为已完成：真实抑制活性验证、HTVS 完整全库训练、泛化的 target-aware 模型、完整原始 MD workflow、Top-k 已经提高。

Phase 4 的核心价值是把“为什么 Top-k 没提升”转化为可检验的工程路线：扩大可追溯排序样本、冻结独立评价集、增加靶点交互证据，然后再判断是否需要更复杂模型。
