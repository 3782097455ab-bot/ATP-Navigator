# Phase 17 High-Cost Evidence Acquisition Report

更新时间：2026-08-28

## 1. 结论

Phase 17 已按门控规则在资格验证前停止。项目隔离环境中真实安装并通过导入测试的是 OpenMM 8.6.0（Reference、CPU、OpenCL 平台）和 openmmforcefields 0.15.1；但是本机没有形成可审计的端到端 open-MM/GBSA 路线。缺失项包括可用的 OpenFF Toolkit 或 AmberTools 小分子参数化链，以及 ParmEd/gmx_MMPBSA 等经过验证的分析链。Prime MM/GBSA 沿用既有许可审计结论 `license_unavailable`，本阶段没有重复签出。

因此：8个资格候选全部记为 `blocked`，不是 `failed`，也没有生成任何 `open_mmgbsa_deltaG` 数值；30候选和最多60候选两级批处理均未启动。该结果是科学能力门控的真实负结果，不是高成本证据验证通过。

## 2. 后端审计

| 后端/依赖 | 真实状态 | 结论 |
|---|---|---|
| RDKit | available | 可做结构处理，不等同MM/GBSA后端 |
| OpenMM 8.6.0 | 项目隔离安装，导入及平台探测通过 | 单独可用，但不是完整MM/GBSA路线 |
| openmmforcefields 0.15.1 | 项目隔离安装，导入通过 | 缺少OpenFF Toolkit或AmberTools，不能给候选配体建立经验证参数 |
| OpenFF Toolkit | 无兼容包索引发行 | blocked |
| ParmEd | 构建需要当前本机缺失的Microsoft C++ 14+ | blocked |
| GROMACS | executable not found | blocked |
| gmx_MMPBSA | executable not found | blocked |
| AmberTools（antechamber/tleap/sqm） | executable not found | blocked |
| ACPYPE | executable not found | blocked |
| Prime MM/GBSA | 已安装；既有真实license checkout失败 | `license_unavailable`，本阶段未重试 |

完整机器可读审计见 `results/phase17/high_cost_backend_status.json`。所有新增依赖仅写入 `workspace_local/phase17/deps`，没有修改系统级环境、Schrödinger安装或历史模型环境。

## 3. 候选池与资格集合

统一候选池保留来源隔离，共90个唯一ID：Phase 15历史HTVS候选60个，Phase 16生成候选30个。生成候选没有改写为历史HTVS身份。

资格集合固定为8个：IN-2参照1个、multi-protocol strong 2个、extreme disagreement 2个、medium control 1个、generated high-ranking 1个、generated diverse/novel 1个。IN-2没有被其他候选替代。

## 4. 协议状态

`open_mmgbsa_7p3w_v1`只建立了阻断状态清单，没有建立可运行的冻结科学协议。受体来源和上游`vina_7p3w_v1`来源hash已记录；但配体电荷、力场、水模型、离子处理、最小化、采样、帧提取和GB/PB模型均保持 `unresolved`。这些项目不能在没有真实工具链资格验证时靠默认值补齐。

输出字段预留为 `open_mmgbsa_deltaG`，没有使用或覆盖历史 `prime_mmgbsa` 字段。

## 5. 门控结果

- qualification requested：8；
- success：0；
- failed：0；
- blocked：8；
- 数值结果：0；
- 资格阈值：至少7/8成功；
- qualification：未执行，能力门控阻断；
- 30-candidate pilot：未启动；
- 自动扩展至60：未启动；
- Evidence Registry新增高成本物理证据：0。

`open_mmgbsa_results.csv`逐候选保存阻断阶段、原因、输入hash、attempt=0和终态。没有模拟轨迹、能量、帧数或DeltaG。

## 6. 下游分析状态

由于高成本数值证据为0，以下分析均明确为 `not_available`：Glide/Vina/open-MMGBSA三协议相关性、最大三协议分歧、parent-child open-MMGBSA差值、Phase 17 shadow ranking、基于新高成本证据的next20 acquisition。对应CSV保留稳定schema和原因，而不是填入假数值。

Phase 14–16结果、`vina_7p3w_v1`、Decision Engine和Model v0–v4-alpha均未修改。24个受保护模型文件阶段前后SHA-256完全一致；没有训练Model v5。

## 7. 继续条件

Phase 17后续计算只有在以下任一路线完成独立资格审查后才能恢复：

1. 安装并验证GROMACS + gmx_MMPBSA + AmberTools/ACPYPE；或
2. 为OpenMM补齐兼容的OpenFF/GAFF小分子参数化和经验证的MM/GBSA分析实现；或
3. 获得可用Prime MM/GBSA许可并按独立协议运行。

恢复时必须从现有8候选资格门控开始，先达到至少7/8且通过轨迹、解析和有限值QC，不能直接跳到30/60候选，也不能把不同后端结果混成同一标签。

## 8. 语义边界

本阶段属于计算后端能力、数据语义一致性和provenance QC，不是生物安全、临床前或临床研究。没有实验活性标签，没有证明候选有效，也没有将协议一致性解释为生物学真值。
