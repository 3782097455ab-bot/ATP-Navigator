# ATP-Navigator Target-aware Interaction Feature 设计报告

更新日期：2026-08-22  
状态：数据审计与接口设计完成；尚未接入排序模型。

## 1. 结论

当前项目具备两类可用的 target-aware 资产：

1. VSW.maegz 中 17 个候选的 Docking pose/属性记录，可作为静态 pose 交互特征的输入；
2. IN-2 与 Hit3/ATP-Top1 两个 MD 体系的逐帧蛋白–配体接触 .dat 导出，可计算占有率和 interaction fingerprint。

这批数据足以建立“交互特征抽取器”和两个体系的案例级证据对比，但不足以训练一个可泛化的 target-aware 排序模型：只有两个 MD 体系，而且原始 .xtc 均为未完成下载片段。现有接触导出可分析，却暂时不能从完整原始轨迹独立重算。

## 2. 数据审计

两个体系的接触导出均覆盖 10,000 个 frame 索引。逐帧数据包括 H-bond、hydrophobic、ionic、π-cation、water bridge；当前 Pi-Pi、halogen、metal 文件只有表头、没有事件。

| 体系 | H-bond 行 | 疏水行 | 离子行 | π-cation 行 | 水桥行 | 原始轨迹 |
|---|---:|---:|---:|---:|---:|---|
| SYS-MD-IN2-001 | 8,518 | 4,299 | 3,926 | 2,175 | 7,947 | .xtc.baiduyun.p.downloading，不完整 |
| SYS-MD-HIT-001 | 20,210 | 6,453 | 10,148 | 25 | 18,253 | .xtc.baiduyun.p.downloading，不完整 |

质量例外：IN-2 的 PL-Contacts_HBond.dat 含 229,444 个 NUL byte，严格解析得到 8,518 条事件，12 条数字开头行被拒绝，数字候选行解析率为 99.86%。该文件必须保留原件并在衍生特征中标注 source_corruption_flag=true；不能静默忽略损坏。

Hit.csv 与 IN-2.csv 各包含 1,000 条 MD 构象 MM/GBSA 记录；MMGBSA.csv 是二者的并列表。来源均为计算结果，不是活性测定。

## 3. 数据驱动的 persistent-contact 候选

下面残基是按“任一体系、任一 interaction type 占有率 ≥10%”从现有导出筛出的候选，不是预设口袋残基，也不代表已证明具有生物学功能。

| 残基 | 现有证据示例 |
|---|---|
| e:ASP81 | Hit H-bond 96.93%；IN-2 H-bond 53.61%、ionic 22.80% |
| g:GLU227 | Hit H-bond 98.56%、ionic 98.45%；IN-2 water bridge 29.42% |
| g:GLN154 | Hit water bridge 50.43%；IN-2 H-bond 11.05%、water bridge 16.98% |
| g:LEU146 | Hit hydrophobic 33.45%；IN-2 hydrophobic 31.03% |
| g:VAL223 | IN-2 hydrophobic 10.72%；Hit 8.60% |
| g:ARG224 | IN-2 π-cation 20.86% |
| e:VAL11 | Hit hydrophobic 19.71% |
| g:ASP158 | Hit water bridge 75.41% |
| g:ASP161 | Hit water bridge 28.56% |
| g:GLU147 | Hit water bridge 25.48% |

残基编号必须同时保留 chain、resname 和 residue number。禁止只用数字编号，避免不同链混淆。

## 4. 特征体系

### 4.1 Docking pose 静态特征

对每个候选的核验 pose 计算：

- pose_hbond_count、pose_hbond_donor_count、pose_hbond_acceptor_count；
- pose_hydrophobic_contact_count；
- pose_ionic_contact_count；
- pose_pi_cation_count、pose_pi_pi_count；
- pose_unique_contact_residues；
- 与数据驱动 persistent-contact 候选的二元/计数特征；
- ligand efficiency 和每重原子 contact 数。

距离和角度阈值必须记录在 protocol_id 中。若 Schrödinger 导出没有显式几何列，不能从二维示意图反推距离。

### 4.2 Interaction fingerprint

稀疏位命名规则：

IFP::<chain>:<resname><resnum>::<interaction_type>

例如 IFP::g:GLU227::HBond。首版字典只由训练折内出现的 residue/type 组合建立，held-out 数据中的新组合进入 IFP::OTHER，避免用全数据字典造成信息泄漏。

同时保留：

- 各 interaction type 总数；
- 接触残基数与 interaction-type 多样性；
- persistent-contact 位命中数；
- 与 IN-2 reference fingerprint 的 Jaccard/Tanimoto 相似度。

reference 相似度是“机制相似性证据”，不是默认越高越好；应作为单独消融，而不是硬编码加分。

### 4.3 MD 动态特征

每个 system–residue–interaction 计算：

- occupancy = occupied_frames / system_frame_count；
- event_count_per_frame；
- longest continuous run、mean run length、transition count；
- 前/中/后三段占有率和 drift；
- contact entropy；
- 关键 interaction 同时出现的 co-occupancy。

体系级聚合：

- ligand/protein RMSD 与 RMSF 摘要；
- H-bond、疏水、离子、水桥总占有率；
- MD-MM/GBSA mean、SD、median、IQR、P10/P90；
- MM/GBSA 低能构象比例和时间段漂移。

MD 帧高度自相关，置信区间应使用 block bootstrap，不能把 10,000 帧当作 10,000 个独立样本。

## 5. 与排序模型的接入边界

| 阶段 | 可接入内容 | 当前状态 |
|---|---|---|
| Pose-IFP v0.1 | 17 个核验 VSW pose 的静态 interaction features | 可开发抽取器；需验证 VSW.maegz 的蛋白坐标/pose 记录结构 |
| MD evidence v0.1 | IN-2 与 Hit3 两体系的占有率和 MM/GBSA 分布 | 可做案例级证据展示 |
| Target-aware ranker | 多候选的同协议 pose/MD 特征 | 暂不可训练；样本覆盖不足 |

推荐先把 pose-level 特征接入 17 候选消融实验；MD 特征暂时只进入候选证据卡，不进入模型训练。只有当多个候选使用相同 MD 协议并完成身份映射后，才建立 MD feature block。

## 6. 质量门槛

- 每个 contact 文件记录 hash、byte-level corruption flag、解析率和拒绝行数；
- 事件 frame 必须落在系统 frame 范围；
- chain/residue/type 字段必须完整；
- 同一 pose/system 只对应一个 canonical ligand identity；
- .png/.svg/.pdf 只用于人工核对，不作为机器学习数值来源；
- 恢复完整 XTC 后，抽样重算接触并与现有 .dat 对账；
- 在只有两个 MD 体系时，不对 target-aware 特征的泛化性能作统计性声明。
