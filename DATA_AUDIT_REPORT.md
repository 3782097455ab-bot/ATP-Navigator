# DATA_AUDIT_REPORT — ATP-Navigator Dataset v0.1

生成日期：2026-08-22  
扫描范围：`表征/`、`运行/`、`作图/`（只读）  
本阶段未训练模型。

## 当前数据资产

- 原始文件：159 个；总大小 2838985130 字节。
- 文件状态：complete 11，incomplete 7，corrupted 5，derived 128，unknown 8。
- 可解析 HTVS：4373 条构象/变体记录，1633 个来源 compound code；来自 001、002、003 三个可读分片。
- VSW 候选表：18 个数据行，其中 1 个空 SMILES 占位行未作为分子记录，17 个含 SMILES 和 MM/GBSA 分数的候选记录。
- MD/MMGBSA：IN-2 1000 帧，HIT 1000 帧；v0.1 仅写入各体系均值，不把帧当成独立分子样本。
- ADMET：工作表 `results_toxicity_1745582138.392`，18 条化合物行；v0.1 按源工作簿末列公式 `SUM(B:AB)` 保存 27 个二元端点的聚合值（源末列表头为空），原始端点仍保留在源工作簿中。
- 化学表征：编号 466 的 1H NMR（D2O、DMSO）和 LC-MS PDF，共 3 个文件；尚未与 HIT/Top 候选建立可审计的一一映射。
- 结构/展示资产：Top-1 至 Top-5 PDB、MD 报告、分析表、图像和视频；在 manifest 中作为 derived 管理。
- 结构化输出：molecules 1659 行；screening_records 4410 行（HTVS 4373、Docking 0、MMGBSA 19、ADMET 18）；systems 2 行。

## 当前可用于训练或建模的数据

- HTVS 的 4373 条记录可用于建立“复现/近似 Docking 分数”的 baseline，划分时必须按 compound code 分组，避免同一分子的不同质子化/构象变体跨训练集和测试集。
- HTVS 标签是计算评分，不是实验活性；它只能支持评分函数代理、排序一致性和数据流程验证，不能据此声称建立了抗菌活性预测模型。
- 17 个含 SMILES 的 VSW/MMGBSA 候选可用于小样本排序分析或外部预训练表征的初步评估，但不足以独立训练复杂模型。
- 两个 MD 体系和逐帧 MM/GBSA 可用于体系内时序/稳定性分析；仅有两个配体，不能作为分子级监督学习训练集。
- 18 条 ADMET 预测记录可作为候选描述特征或规则筛选输入，样本量不足，且预测端点不是实验真值。

## 当前不能直接使用的数据

### incomplete

- `运行/运行/ATP-Ref-MD1/MD.xtc.baiduyun.p.downloading`
- `运行/运行/ATP-Top1-MD2/MD.xtc.baiduyun.p.downloading`
- `运行/运行/ATP-VSW/ATP-VSW-DOCK_HTVS_1-004_lib.maegz.baiduyun.p.downloading`
- `运行/运行/ATP-VSW/ATP-VSW-DOCK_HTVS_1-005_lib.gz`
- `运行/运行/ATP-VSW/ATP-VSW-DOCK_HTVS_1-005_lib.maegz.baiduyun.p.downloading`
- `运行/运行/ATP-VSW/ATP-VSW-DOCK_HTVS_1-005_lib/ATP-VSW-DOCK_HTVS_1-005_lib.mae`
- `运行/运行/ATP-VSW/ATP-VSW-DOCK_HTVS_1-006_lib.maegz.baiduyun.p.downloading`

### corrupted

- `作图/作图/1-阳性化合物和蛋白的MD/图-1/images/PL-RMSD.svg`
- `作图/作图/1-阳性化合物和蛋白的MD/图-1/raw-data/L-Properties.dat`
- `作图/作图/1-阳性化合物和蛋白的MD/图-1/raw-data/PL-Contacts_HBond.dat`
- `作图/作图/3-新型苗头有化合物和蛋白复合物的MD/图-1/images/P-SSE_Timeline.svg`
- `作图/作图/3-新型苗头有化合物和蛋白复合物的MD/图-1/raw-data/PL_RMSD.dat`

- 图片、SVG、PDF 报告、视频和 CXS/AI 展示文件是衍生资产，不是独立监督标签。
- HTVS 的重复压缩/解压副本不能重复计数为新样本。
- IN-2/HIT 的 1000 帧高度相关，不能按 2000 个独立分子样本训练。
- HIT、ATP-Top1-MD2、Top-1/Top-3、466 之间缺少可核验映射，v0.1 不跨文件名强行合并。

## 下一步缺失数据

1. 从原始库到 HTVS/SP/XP/MMGBSA 的完整 compound-level workflow 表，以及每一步淘汰/保留关系。
2. 稳定的化合物主键映射：HTVS compound code、VSW SMILES、Top-1~5 PDB、HIT MD 配体、466 表征样品之间的一一对应表。
3. 可复现参数：Schrödinger 版本、网格/蛋白准备、质子化、打分、MM/GBSA 与 ADMET 运行配置。
4. 完整可读取的两套原始 MD 轨迹；当前 XTC 均为下载残片。
5. 实验活性标签（明确检测方法、浓度/单位、重复数、阳性/阴性和失败样本）。没有这些数据，不能训练或验证真实活性优先级模型。
6. 更多具备同一评价流程的负样本与中间分数，避免只保留 Top hits 造成选择偏差。

## v0.1 边界

- 本数据层建立文件级溯源、内部主键和窄表接口。
- 不修复原始文件，不补写缺失字段，不把未来计划写成已有数据。
- 不训练模型；待主键映射和实验标签补齐后再进入 baseline 阶段。
