# ATP-Navigator Model Upgrade Plan — Phase 2

更新日期：2026-08-22  
目标：在保留 Phase 1 / 1.5 baseline 的基础上，通过可解释消融评价分子表示与计算证据是否改善候选排序。标签仍是同一协议的计算 MM/GBSA，不是真实生物活性。

## 1. 对照组定义

现有 `Random Forest / XGBoost / LightGBM + Morgan1024 + RDKit10 + ADMET_SUM` 及其 LOOCV、scaffold-grouped 结果全部保留，统一称为 `Legacy_P1_*`。不改文件、不改名、不覆盖。

新的 Phase 2 消融链预注册如下：

| 模型 | 输入 | 目的 | 当前状态 |
|---|---|---|---|
| Model 0 | 同一候选集的最低 Glide docking score | 传统排序对照，无模型拟合 | 暂不可公平评价：17 个 MM/GBSA 候选中仅 1 个与可读 HTVS 分片建立 confirmed 桥接，无法形成排序集合 |
| Model 1 | LightGBM + Morgan1024 | 新的分子表示基线 | 数据允许，待严格复现实验 |
| Model 2 | Model 1 + 预注册 RDKit11 | 测试全局理化性质的边际贡献 | 数据允许，待严格复现实验 |
| Model 3 | Model 2 + Glide / ligand efficiency / compound-level Docking 统计；QuickProp、ADMET 作为预注册子消融 | 测试计算证据融合能力 | 暂缺共同候选映射；不能用缺失填补伪造信息增量 |
| Model 4 | 冻结的预训练分子 embedding + Ridge/PLS，或与相同 LightGBM 对照 | 测试外部分子表征 | 当前 17 条标签不允许启用，状态为 `planned_not_enabled_insufficient_data` |

为避免定义混乱，Model 1 不是“复现历史 LightGBM”；历史 LightGBM 已经含描述符和 ADMET 总分。新的 Model 1–3 是独立的、可辨识的特征消融链。

## 2. 评价协议

1. 评价单位固定为唯一 `canonical_id`。同一化合物的不同 pose、构象或质子化状态必须先聚合，不能跨训练/测试折。
2. 当前主标签固定为 17 个 VSW 静态 pose 的 MM/GBSA；lower-is-better。MD 帧均值、ADMET 总分和未来实验活性必须使用不同协议标识，不能混成一个标签。
3. 主榜只使用 M0–M3 全部可用且身份已核验的 common set。未形成 common set 时，状态写 `not_evaluable`，不记 0 分。
4. 沿用固定 Bemis–Murcko scaffold-grouped leave-one-group-out。缺失值处理、常量/方差筛选及任何降维仅在训练折内拟合。
5. 固定 random seed=42、fold 清单和初始 LightGBM 参数。若调参，必须使用嵌套 group CV；在当前样本量下优先保持固定参数。
6. 主指标为 Spearman、NDCG@5、Top-k enrichment、hit recovery；RMSE 作为次级误差指标。所有指标从同一份 OOF 预测计算。
7. “hit”统一定义为 MM/GBSA computational top-k，不得表述为实验活性 hit。

## 3. 特征消融顺序

### 3.1 Morgan 规格

- 主规格：1024 bit，用于与 Phase 1 比较。
- 探索规格：2048 bit，使用完全相同的样本、fold 和参数。
- 决策依据：OOF 排序指标、bootstrap 区间、排序稳定性与碰撞率，而不是一次最高值。

### 3.2 RDKit 描述符

固定 11 项白名单，不在 17 个样本上无约束扩展描述符集合。MW、LogP、TPSA、HBD、HBA、可旋转键和芳香环数用于核心解释；其余 4 项为 Phase 1 兼容字段。

### 3.3 Docking / QuickProp / ADMET

- Docking 使用最低 Glide score 对应的实际 pose 整行，以及 pose 数、中位数、标准差和 Top-2 分差。
- QuickProp 先建立精简白名单，再将 51 项全量作为次级消融；所有常量筛选在训练折内完成。
- ADMET 使用 27 端点或总和二选一，避免确定性重复。
- Model 3 只在身份桥接形成足够 common set 后启用。`VSW.maegz` 已恢复 17 个候选 code，但三个可读 HTVS 分片中只找到 code 91074（Hit13）；单个样本不能形成排序 benchmark，因此 M0/M3 仍不可评价。

## 4. Embedding 启用门槛

以下是本项目的工程门槛，不是普适统计定律：

- 至少 200 个同协议分子标签；
- 至少 50 个独立 scaffold；
- 结构—标签唯一映射 100%；
- 目标和主特征覆盖率至少 80%；
- 只使用冻结 embedding，不微调；
- 在每个训练折内用 PCA 或正则化把有效维度降到远低于训练样本数，例如不超过 `min(32, floor(n_train/5))`。

门槛未满足时 Model 4 保持计划状态，不出性能数字。

## 5. 解释性方案

现有全量拟合 joblib 模型不能代表严格 OOF 解释，因此当前不制作伪精确 SHAP 排名。下一轮 benchmark 中新增折内 permutation importance，按 `morgan / descriptors / docking / quickprop / admet` 特征组聚合，并跨 scaffold 折报告均值与区间。

Morgan bit 只显示 bit 编号；除非保存 RDKit `bitInfo` 并映射到子结构，否则不赋予化学机制含义。所有解释均为排序敏感性证据，不是因果机制。

## 6. 实施门

| Gate | 进入条件 | 通过后动作 |
|---|---|---|
| G1 身份门 | 17 个候选与 Docking/QuickProp 有可审计主键交集 | 启用 M0、M3 公平评价 |
| G2 标签门 | score type、protocol、aggregation 明确 | 固定 Phase 2 标签清单 |
| G3 划分门 | canonical/scaffold group 无跨折泄漏 | 运行 M1–M3 OOF 消融 |
| G4 稳定性门 | 指标和 bootstrap 区间可复现 | 形成比赛主图和候选证据卡 |
| G5 数据量门 | 满足 embedding 工程门槛 | 仅启用冻结 embedding 对照 |

Phase 2 当前优先通过 G1–G3，不追求大型模型或最终性能。
