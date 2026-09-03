# 从 IN-2 出发的端到端可复现虚拟筛选入口

## 文档目的

本工作流补齐了项目中“从已确认母体结构出发，形成可重复生成、可质控、可进入真实计算工具和证据登记层的候选库入口”。它不是对 2024 年历史十万分子库的复刻，也不改变任何历史模型或历史计算结果。

工作流的科学位置为：

```text
靶点与 IN-2
  → 衍生库生成
  → 结构准备与过滤
  → 开放工具 Docking
  → 分层精筛
  → 高成本 MM/GBSA 门控
  → Evidence Registry
  → AI 辅助决策
  → 研究者候选面板
```

## 一、历史 Schrödinger 工作流

项目原始研究以鲍曼不动杆菌 F1F0-ATP 合酶为靶点，使用 Schrödinger 工作流开展化合物枚举、虚拟筛选、候选精筛及部分 MM/GBSA、ADMET 和 MD 分析。现有仓库保存的是从原始科研文件中恢复、整理或导出的证据，而不是一套可重新执行的完整 Schrödinger 工程。

当前本机能够检测到 LigPrep、Glide、QikProp 和 Prime MM/GBSA 可执行文件，但真实 license checkout 未通过。因此本轮没有运行 Auto_Enum、LigPrep、Glide HTVS/SP/XP、QikProp 或 Prime MM/GBSA，也没有用其他软件生成数值后冒用这些名称。

在获得原始 Auto_Enum 配置、原始 building-block 库、原始 attachment 定义、原始枚举输出和可用商业许可证之前，不声称能够逐字节复现历史商业工作流。

## 二、恢复的历史证据

仓库中已恢复或登记的历史证据继续只读保留，包括：

- HTVS 1633 化合物的结构与历史 Glide 相关字段；
- 内部 Hit1–Hit17、IN-2 及其分层身份审计；
- 历史静态 MM/GBSA、ADMET、MD 分析和化学表征记录；
- 1633 个候选在冻结 `vina_7p3w_v1` 下的开放协议证据；
- 30 个候选在冻结 `open_mmgbsa_7p3w_v2` 下的真实开放 MM/GBSA 结果；
- Model v0–v4-alpha、Model v3 Decision Engine 与既有三协议分析。

这些证据不会因为新库生成而被重新命名、覆盖、重训或重新解释。尤其是 Vina 不等于 Glide，开放 MM/GBSA 不等于 Prime MM/GBSA，协议一致性也不等于生物活性。

## 三、重建的开放可复现工作流

### 3.1 输入与冻结配置

母体使用身份清单中已确认的 `ATP-REF-IN2`。规范结构为：

```text
C[NH+](C)Cc1ccc(C[NH2+]Cc2cc3ccccc3nc2SCc2ccccc2)cc1
```

母体结构 SHA-256：

```text
ccd401f1ea07dc14c58a5929c18ed4fc70241dd381d7d16b9e89c0c47542dc72
```

正式配置为 `configs/library_generation/in2_reconstructed_v1.json`。它冻结：

- generator version：`1.0.0`；
- building-block library version：`in2_building_blocks_v1`，50 个计算枚举片段；
- reaction template：`aromatic_CH_Rgroup_substitution_v1`；
- attachment rule：带氢芳香碳；IN-2 当前识别出 14 个原子位点；
- substitution depth：单点与双点取代；
- random seed：`20260903`；
- RDKit sanitization、FragmentParent、canonical isomeric SMILES 和去重规则；
- 硬过滤阈值及 Lipinski、Veber、PAINS、reactive warning 的处理方式。

配置与其依赖资产的组合哈希为：

```text
0edaacdb8a4b66f6f28108efa09d111887870a2ef58b4953eddeaca48e82dd6b
```

单点和双点组合形成 228,200 个确定性设计位置。seed 用于构造可复现的全排列访问顺序，不依赖 Python 的随机散列顺序。

### 3.2 逐分子记录与 provenance

每个被接受结构记录：母体 ID、canonical SMILES、InChIKey、生成方法、attachment site、reaction SMARTS、building-block ID/SMILES、generator config hash、seed、timestamp 和 provenance hash。稳定 library hash 不包含运行时间戳，因此相同化学输入与冻结配置可跨运行比较。

所有原始设计都进入分块 checkpoint。结构生成、sanitize、去盐/FragmentParent、价态、去重或硬阈值失败的记录不会静默消失，而是写入 `rejections.csv` 并保留明确 `rejection_reason`。

Lipinski、Veber、PAINS 和 reactive warning 在当前 v1 配置中属于警示或规则字段，不作为默认硬删除条件。这一点避免把药物化学启发式误当成真实活性或合成可行性结论。

### 3.3 实测生成结果

| 验证 | 原始处理数 | 唯一接受数 | 拒绝数 | 实测耗时 | library hash |
|---|---:|---:|---:|---:|---|
| N=100 工作流 smoke | 100 | 100 | 0 | 生成约 1.9 s | `2b7fc63e4253ee5d40f551f75cce97d7aa96b10fc1adc32412f382c8b71d10bf` |
| N=1,000 generation | 1,004 | 1,000 | 4 | 7.20 s | `8f5f10e74f226db5d79e35ba92bcaefc15c5e897b2b2fc8dfbe5ff1d83cef232` |
| N=100,000 checkpoint/resume | 146,283 | 100,000 | 46,283 | 826.52 s 活跃运行 | `2af8186dde533bf14bef2c38cd929f2c0bd7756dc20db0bd4f67936a499458ba` |
| N=100,000 独立重复生成 | 146,283 | 100,000 | 46,283 | 812.71 s | `2af8186dde533bf14bef2c38cd929f2c0bd7756dc20db0bd4f67936a499458ba` |

两次 100,000 结构运行的 library hash 完全一致。第一轮在 raw=20,000 时保存 checkpoint（已接受 19,293，拒绝 707），随后从该位置恢复；恢复结果与独立重复生成相同。最终 100,000 条 canonical SMILES 与 InChIKey 均唯一，逐分子 provenance 字段完整。

46,283 条拒绝记录均为 `generated_duplicate`。这不是静默损失，而是分子对称性、位点/片段组合在规范化后得到同一连接结构的可审计结果。当前没有结构生成、sanitize、价态或硬阈值失败。

峰值 Python 追踪内存为 16.43 MiB；这是 `tracemalloc` 记录的 Python 分配峰值，不等价于操作系统进程总 RSS。第一轮最终库约 50.28 MB，拒绝表约 17.28 MB，均保存在 `workspace_local`，避免把大规模派生文件直接提交到 Git。

### 3.4 N=100 真实开放工具 smoke

N=100 库使用冻结 `vina_7p3w_v1` 执行真实 AutoDock Vina 1.2.7：

- success：100；
- failed：0；
- affinity 范围：-9.244 至 -6.520 kcal/mol；
- mean：-8.02583 kcal/mol；
- 100 个任务首个启动至最后完成：约 5,837.42 s；
- 写入共享 Evidence Registry：200 条真实记录（100 条 Vina affinity + 100 条 pose QC）；
- 再次运行全部命中缓存，未重复 docking。

Vina 数值只解释为 `vina_7p3w_v1` 下的计算 docking evidence，不命名为 Glide SP/XP，也不作为活性、命中率或实验成功概率。

### 3.5 正式统一控制器

统一科研入口为：

```powershell
.\.venv\Scripts\python.exe run_pipeline.py --config configs/in2_7p3w_reference.yaml --mode development
```

`smoke`、`development`、`full` 三种规模由同一个 `ReferencePipeline` 控制。每次运行写入 `runs/<run_id>/`，其中按 `config/manifests/library/filtering/docking/refinement/mmgbsa/evidence/decision/reports/logs` 组织。阶段状态写入 `manifests/stage_state.json`；库生成按 chunk 恢复，Vina 和 Open MM/GBSA 按候选与协议哈希缓存，失败不会在未明确允许时自动重试。

统一配置同时冻结项目 UUID、7P3W/IN-2 哈希、生成协议、开放过滤协议、`vina_7p3w_v1`、`open_mmgbsa_7p3w_v2`、证据门控和透明决策权重。

### 3.6 冻结的开放过滤协议

对 PPT 的 39 张源幻灯片逐页审计后，能够确认历史文字流程是：QuickProp 仅保留符合 Lipinski 且不含反应性片段的结构，再执行 Glide HTVS 前 10% → SP 前 10% → XP → Prime MM/GBSA → Deep-PK。当前开放工作流没有把该描述伪装成已恢复的机器可执行 QuickProp/Glide 配置。

`open_physchem_structural_filter_v1` 在查看漏斗结果前冻结：MW 250–500、cLogP -1–5、TPSA ≤140、HBD ≤5、HBA ≤10、可旋转键 ≤10、绝对形式电荷 ≤2 作为 hard filter；RDKit sanitize、价态与 reactive SMARTS 也作为 hard filter；环数、fraction Csp3 与 PAINS 仅作 warning。每个失败规则均保留 field、threshold、raw value、rationale、kind 和协议哈希。它明确不是 QuickProp。

实测 full 库：100,000 个唯一结构经该冻结规则后保留 7,265 个，92,735 个至少触发一条 hard filter。逐规则记录允许同一结构存在多个失败原因，因此规则计数之和不等于被剔除结构数。

### 3.7 100K Vina 资源门控

根据真实 N=100 `vina_7p3w_v1` 运行的 5,837.42 s wall time、约 23,084 s 候选累计时间、磁盘与失败率线性估算，7,265 个过滤后结构在 4 workers 下约需 424,088 s（117.8 h）wall time。该值超过统一配置的 24 h 自动门限，因此 full 模式在 Vina 前真实停止为 `blocked_by_resource_gate`，没有启动 7,265 个或 100,000 个 docking，也没有生成模拟结果。

### 3.8 高成本证据与两级决策

开放精筛不制造第二套 Vina 来冒充 SP/XP。Level A 用真实 Vina、结构多样性、边界位置、IN-2 相似性和证据缺口选择下一份高成本证据，输出被明确标记为 `NOT biological hit ranking`。Level B 只接受同时具备 `vina_7p3w_v1` 与 `open_mmgbsa_7p3w_v2` 的结构；缺失 ADMET、ATP 抑制、MIC 或细胞毒性时继续标记 unknown，并提出独立实验验证顺序。

## 四、AI / 决策扩展

统一控制器不强迫完整 Model v3 对缺少历史 Glide、QuickProp、ADMET 或实验结果的新结构给出伪确定结论，也没有训练新模型。

Level A 是证据获取决策：利用 Vina 批内相对位置、IN-2 结构相似性、scaffold 多样性、边界位置和证据缺口，决定有限 Open MM/GBSA 预算先给谁。该输出始终标记为“下一份高成本证据优先级”，不是生物活性排序。

Level B 是实验前计算候选决策：只有 Vina pose QC 通过且获得真实 `open_mmgbsa_7p3w_v2` 的结构才能进入。它调用冻结的 structure-only / ATP / antibacterial 先验输出，并以统一配置中公开的权重融合 Vina、Open MM/GBSA、结构先验和规则型 drug-likeness。ADMET、ATP 抑制、MIC 和细胞毒性若无真实记录，保持 `unknown`，不会填 0、插值或借用其他 endpoint。

Level B 的名称固定为 **computational pre-experimental prioritization**。它不是 active compound、validated inhibitor 或 drug candidate 清单。

## 五、执行方式

仅生成或恢复衍生库：

```powershell
.\.venv\Scripts\python.exe src\generate_reconstructed_library.py `
  --target 100000 `
  --run-id in2_reconstructed_100k_v1 `
  --verify
```

执行统一 N=100 smoke：

```powershell
.\.venv\Scripts\python.exe run_pipeline.py `
  --config configs\in2_7p3w_reference.yaml `
  --mode smoke
```

将 `--mode` 替换为 `development` 或 `full` 即可使用完全相同的控制器。`--stop-after docking` 等参数可在阶段边界安全停止；之后用相同 run ID 重启，会验证 checkpoint、library/config/protocol/artifact hash，并跳过已经完成的候选。失败任务不会在未明确允许时自动重试。

## 六、仍缺失的历史信息

以下项目仍为 `unknown` 或未获得，不能从当前资产反推：

1. 2024 历史 Auto_Enum 的原始配置、完整 building-block 库与版本；
2. 历史十万结构库的原始逐分子文件及其 library hash；
3. 历史 attachment site、reaction template、枚举顺序、seed、去重和失败保留规则；
4. 能够证明历史 LigPrep/Glide/QikProp/Prime 全链参数的完整机器可读 protocol manifest；
5. 新重建衍生结构的实验 ATP 抑制、MIC、毒性和合成结果；
6. 新重建衍生库中除已通过高成本采集门控的小规模候选外，其余结构的 Open MM/GBSA 证据；
7. 新库与原历史十万库逐结构一致性的任何证据。

因此正式名称始终为 **reconstructed reproducible derivative library（重建的可复现衍生库）**，不得改称 historical 100k library。
