# ATP-Navigator Phase 2 Progress Report

更新日期：2026-08-22

## 1. 本轮完成

- 保留 Dataset v0.1、Phase 1 源代码、已训练 RF/XGBoost/LightGBM、旧图和 Phase 1.5 benchmark，未删除或覆盖。
- 新增 `src/build_phase2_assets.mjs`，只读解析三个可读 HTVS Maestro 分片和 ADMET 工作簿。
- 新增 4,373 行 pose-level Docking/QuickProp 表，覆盖 1,633 个 compound code、11 个 Glide/ligand-efficiency 字段和 51 个 QuickProp 字段。
- 新增 18 行端点级 ADMET 表，保留 27 个二元预测端点和源聚合总和。
- 新增 `src/feature_pipeline_v2.py`，支持 RDKit11、Morgan1024/2048、Docking compound 聚合、QuickProp 和 ADMET 特征块；运行结果使用 v2 文件名。
- 建立 compound crosswalk，覆盖 1,633 个可读 HTVS code、17 个 VSW/MMGBSA 候选 code、Hit/Top/MD/表征历史别名，并按 confirmed / probable / unknown 分级。
- 新增 `docs/Feature_Engineering_Report.md` 和 `docs/Model_Upgrade_Plan.md`。
- 新增 `src/plot_phase2_figures.py`，从现有严格 benchmark 输出四张准备图，不训练新模型。

## 2. 身份映射进展

`运行/运行/ATP-Top1-MD2/MD.cms` 直接给出配体来源信息：VSW compound code 27063、variant 27063-1、ATP-Top1 标题和配体 SMILES。该 SMILES 对应 `ATP-SMI-874C2DE25FE4`。

RDKit 结构比较显示 `Top-3.pdb` 与上述 MD 配体具有相同的带立体化学 InChIKey，因此 `Top-3` 也映射到 `ATP-SMI-874C2DE25FE4`，置信度为 confirmed。这里暴露出来源命名不一致：同一化学结构同时出现于 ATP-Top1 和 Top-3 标签，后续报告必须以 canonical ID 为准。

项目 PPT 明确说明 Hit3 被选入 MD，且 `Hit.csv` 的 MM/GBSA 均值与 PPT 的 Hit3 MD-MM/GBSA 数值一致；结合 MD.cms 的完整结构，`HIT` / `ATP-HIT-MD-001` 映射为 confirmed。

项目 PPT 中 Hit3 的 SMILES 与 MM/GBSA `-56.37` 均和 VSW 第 3 条、Top-3 PDB 完全一致，因此 `Hit3` 为 confirmed。编号 `466` 的化学名、分子式 `C30H34N4O`、精确质量、R 构型和 LC-MS `[M+H]+` 与该中性母体一致，但没有显式样品编号交叉表，因此映射为 probable，不写 confirmed。

`VSW.maegz` 已恢复 17 个 MM/GBSA 候选的 VSW code。三个可读 HTVS 分片中仅 code 91074（Hit13）存在原始记录，对应旧键 `ATP-HTVS-AC71774ACC4B`；其 4 个可见构象得分可追溯。其余 16 个候选所在 HTVS 记录未在可读 001–003 分片中出现，004–006 又是不完整下载残片。因此目前只有 1 个 confirmed HTVS→MM/GBSA 桥，仍不足以形成公平排序 common set。

## 3. 特征层状态

| 特征层 | 已完成 | 可直接用于当前 17 个标签 | 状态 |
|---|---|---:|---|
| Morgan1024 / 2048 | 两套矩阵及碰撞诊断 | 17 / 17 | ready |
| RDKit11 | 新增芳香环数，保留兼容字段 | 17 / 17 | ready |
| ADMET 27 endpoints | 端点级表已建立 | 17 / 17 | ready_with_small_n_guardrail |
| Docking / Glide | pose-level 与 compound 聚合接口已建立 | 1 / 17 已桥接，但不足以建模 | blocked_by_identity_coverage |
| QuickProp 51 fields | pose-level 与最佳 pose 接口已建立 | 1 / 17 已桥接，但不足以建模 | blocked_by_identity_coverage |
| MD / 动态 MMGBSA | 仍为两个体系证据 | 不作为分子级训练块 | evidence_only |
| Embedding | 未启用 | 17 条不足 | planned_not_enabled |

## 4. 可视化状态

`results/figures/` 计划/生成：

- `baseline_model_comparison.png`：只画 Phase 1.5 status=ok 的 RF/XGBoost/LightGBM；Docking-only 以不可评价说明处理，不画成 0 分。
- `ai_ranking_workflow.png`：Schrödinger 输出—身份核验—特征块—模型消融—scaffold OOF—候选优先级流程。
- `top_k_enrichment_curve.png`：由 `phase15_predictions.json` 的严格 OOF 预测计算 k=1..8 曲线。
- `model_interpretability_readiness.png`：说明当前解释性证据边界及下一轮折内 permutation importance 方案，不伪造 SHAP/特征重要性。

所有图注明确：n=17、标签为计算 MM/GBSA 排序、不是实验活性。

## 5. 当前结论与下一步

Phase 2 的数据与方法准备已完成增量版，但尚未形成 Docking + 描述符 + ADMET 的同候选训练集，也未训练新模型。当前最重要的下一步不是增加模型复杂度，而是取得或恢复 17 个 VSW 候选对应的 Docking/QuickProp 结构记录或 compound code，形成可核验 common set。

在 common set 补齐前，可以安全执行的新实验只有 M1（Morgan1024）与 M2（Morgan1024 + RDKit11）在既有 scaffold-grouped OOF 协议下的复现与消融；ADMET 应作为单独子消融。M0 和 M3 继续标记不可评价，Model 4 保持未启用。
