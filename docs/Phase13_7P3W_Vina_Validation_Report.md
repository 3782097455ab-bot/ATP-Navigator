# Phase 13：7P3W真实Vina项目工作流验证

日期：2026-08-27
范围：实验前计算证据整合与候选优先级辅助决策；本阶段未训练模型、未修改Decision Engine、未运行1633候选。

## 1. 验收结论

历史7P3W位点已从原始科研资产中恢复，`vina_7p3w_v1`已完成5候选门控和17个内部候选的真实AutoDock Vina运行。5/5门控成功，17/17内部候选对接、解析和pose QC通过。Vina作为独立开放协议证据保存，不替换历史Glide分数，也不进入Model v3的Glide特征。

这是一项真实项目计算链和方法学比较，不是生物活性验证。MIC、ATP酶抑制、细胞毒性等实验结果仍为unknown。

## 2. 历史协议恢复

可追溯来源如下：

- `ATP酶抑制剂的修饰改造.pptx`第5–7页：7P3W、Protein Preparation Wizard、Prime修复、Epik pH 7.4±0.5、OPLS_2005受限最小化、SiteMap Fo界面位点、IN-2 LigPrep和Glide XP叙述；PPT SHA-256为`b5bf3079bd25eeaeeea91da765729b204bc4e862f2190cd72046bc4a5912d286`。
- `VSW.maegz`第一结构：历史受体记录、网格名`InducedFit_1_rec-1_pv-6-out-gridgen`及精确gridbox元数据；SHA-256为`c4048042f3e35cd25c2c1b1a9a188a4000425f39d10feefea7096e98e568cdd1`。
- `ATP.pdb`：历史准备后的e/g受体；SHA-256为`b700d93fd622e74afd3b59f22e5b11f5bd4e764fcb38ad82410e0abb44db4722`。
- `ATP-Ref.pdb`：同一受体和IN-2历史pose；SHA-256为`d7ce2643ba6108e46856d22230ec18b20a17f83cef6818082d3be9b6c9df2a65`。
- `SIteMap.pdb`：117个历史位点点云；SHA-256为`3625da9d7c3680ab8b545e9c4422e3d564629e5c61d559886387b8766c2cc758`。

历史受体PDB与VSW受体按chain/residue/atom name匹配后的坐标RMSD为0.000496 Å，支持其为同一历史受体的序列化版本。

## 3. 冻结Vina协议

协议ID：`vina_7p3w_v1`。

| 参数 | 冻结值 | 来源 |
|---|---:|---|
| target | 7P3W | 历史PPT/VSW |
| box center | 198.147968, 182.436946, 155.933369 Å | `VSW.maegz` gridbox x/y/z center原属性 |
| box size | 25.991257 × 25.991257 × 25.991257 Å | `VSW.maegz` gridbox x/y/z range原属性 |
| receptor | 历史准备后的e/g受体 | `ATP.pdb`，hash固定 |
| receptor conversion | Meeko导入pre-protonated PDB | 本阶段执行选择；不是重新完成Protein Preparation Wizard |
| ligand preparation | ETKDGv3 + MMFF，保留输入质子化 | 本阶段固定合同 |
| Vina | 1.2.7 | 本机实测 |
| exhaustiveness | 16 | 本阶段设计选择 |
| num modes | 9 | 本阶段设计选择 |
| energy range | 3 kcal/mol | 本阶段设计选择 |
| random seed | 20260827 | 本阶段可复现性选择 |
| CPU | 1 | 本阶段确定性资源策略 |

`relation_to_historical_glide = derived_from_historical_site`。数值盒源自历史Glide元数据，但Vina搜索、打分和网格语义不同，因此不是Glide等价协议。

## 4. 身份与结构QC

Hit1、Hit2、Hit3、Hit5的结构与内部冻结ranking表一致。IN-2直接从历史`ATP-Ref.pdb`提取连接关系和质子化状态，使用双质子化结构`C27H31N3S+2`；新数据发布包中AI重建的IN-2别名记录未用于本轮对接，并以compound identity/provenance QC隔离，原文件未修改。

每个候选经过结构解析、配体准备、受体哈希、坐标有限性、原子数一致性、盒内质心、pose数量、分数范围、原生输出解析和输出hash检查。17个内部候选中15个输出9个Vina模式，Hit5和Hit13输出8个；均至少有一个可解析模式并通过QC。

IN-2新Vina最优pose与历史参考pose的重原子质心距离为9.6702 Å。该值只表示两套协议得到的pose位置差异，不能作为活性或结合真实性验证。

## 5. 五候选门控

| 候选 | compound ID | Vina affinity (kcal/mol) | Docking | Pose QC |
|---|---|---:|---|---|
| IN-2 | ATP-REF-IN2 | -8.212 | success | pass |
| Hit1 | ATP-SMI-9DA3213A09E8 | -8.173 | success | pass |
| Hit2 | ATP-SMI-C93E6EC67CDB | -7.887 | success | pass |
| Hit3 | ATP-SMI-874C2DE25FE4 | -8.846 | success | pass |
| Hit5 | ATP-SMI-96FD6257D8BA | -8.085 | success | pass |

门控条件全部满足：5/5成功、IN-2成功、parser成功、Evidence Registry成功、pose QC通过，因此才创建17候选批次。

## 6. 17候选Vina结果

| Vina rank | 候选 | compound ID | affinity (kcal/mol) |
|---:|---|---|---:|
| 1 | Hit4 | ATP-SMI-5D3E7B6B6796 | -9.028 |
| 2 | Hit15 | ATP-SMI-CFA68A98711F | -8.876 |
| 3 | Hit3 | ATP-SMI-874C2DE25FE4 | -8.846 |
| 4 | Hit11 | ATP-SMI-CDED936B42F4 | -8.810 |
| 5 | Hit7 | ATP-SMI-15737353FB69 | -8.557 |
| 6 | Hit17 | ATP-SMI-4417138BF81D | -8.339 |
| 7 | Hit16 | ATP-SMI-91E7552C2382 | -8.200 |
| 8 | Hit1 | ATP-SMI-9DA3213A09E8 | -8.173 |
| 9 | Hit5 | ATP-SMI-96FD6257D8BA | -8.085 |
| 10 | Hit6 | ATP-SMI-E9798004BA11 | -8.077 |
| 11 | Hit2 | ATP-SMI-C93E6EC67CDB | -7.887 |
| 12 | Hit9 | ATP-SMI-FCA9CDF3313B | -7.761 |
| 13 | Hit10 | ATP-SMI-C3308BEE03AC | -7.672 |
| 14 | Hit8 | ATP-SMI-BF69AB71C1A4 | -7.638 |
| 15 | Hit14 | ATP-SMI-775D33706F04 | -7.604 |
| 16 | Hit13 | ATP-SMI-5B36D3E11A3B | -7.449 |
| 17 | Hit12 | ATP-SMI-94F73967C042 | -7.154 |

成功17、失败0。分数只可在`vina_7p3w_v1`同批次内解释。

## 7. 描述性协议比较

样本量n=17。以下是descriptive protocol comparison only，不是biological validation，也不以MM/GBSA标签证明哪个后端更准确。

| 比较 | Spearman | Kendall tau | Top-5 overlap |
|---|---:|---:|---:|
| Vina vs historical Glide | -0.0196 | 0.0000 | 1/5（Hit15） |
| Vina vs static MM/GBSA | 0.1618 | 0.1471 | 2/5（Hit4、Hit3） |
| Vina vs Model v3 | 0.1618 | 0.1471 | 2/5（Hit4、Hit3） |

Vina与Glide分歧最大的候选：Hit4（Vina 1、Glide 17，绝对位移16）、Hit7（5 vs 16，位移11）、Hit14（15 vs 4，位移11）、Hit11（4 vs 13，位移9）和Hit12（17 vs 9，位移8）。该分歧支持后续做协议校准或有目的的正交计算，不支持直接替换旧Binding score。

## 8. Registry、Agent和恢复

Phase 13项目当前登记309条证据记录：

- 109条真实工具执行记录：18结构QC、18配体准备、18RDKit性质、1受体转换、18 Vina affinity、18 Vina通用docking包、18 pose QC；
- 68条历史冻结证据：17 Glide原始分数、17 Glide通用docking包、17静态MM/GBSA和17 Model v3 rank；
- 132条冻结Decision派生记录，来自门控批次、17候选批次以及证据语义补登记后的不可变决策快照。

这些不是309条实验数据。真正新增的Vina数值为18个：17个内部候选加IN-2参考；IN-2不属于内部17候选。

Agent已从共享Evidence Registry回答：

- “Hit3目前有哪些Docking证据？”：Historical Glide `historical_glide_vsw_v1 = -8.421964`，AutoDock Vina `vina_7p3w_v1 = -8.846`，并声明不可互换；
- “Vina和Glide对哪些候选分歧最大？”：按各自cohort rank返回真实rank shift，不合并原始分数。

17候选在3个新Vina作业后受控暂停。暂停前快照含7个完成作业（4个从五候选门控复用、3个新完成），恢复后17个完成；7个既有作业的job ID、attempt和pose hash全部不变。重复执行被阻止，输出hash保持一致。幂等重放时新增Vina作业数为0。

## 9. 工具和模型状态

- RDKit 2026.03.5、Meeko 0.7.1、AutoDock Vina 1.2.7：available并真实执行。
- Glide 10.3、Prime/PSP 7.6、QikProp 8.0、LigPrep 14.4：已安装，但许可证签出返回失败，`commercial_full = blocked`；没有批量重跑商业协议。
- 阶段前后24个受保护模型文件SHA-256完全一致；Model v0–v4-alpha、Model v3输入定义、Decision Engine和冻结6候选面板均未修改。
- 实验反馈仍为0，prospective metrics为`not_available`。
- 提交前完整回归测试105/105通过，其中Phase 13新增11项覆盖协议来源、真实pose解析、证据隔离、Agent查询、IN-2参考处理、受控恢复、重复阻止和禁止Vina冒充Glide。

## 10. 1633候选边界

没有启动1633候选对接。仅生成执行计划：1,633个作业，建议每批25个、约66批；按本轮观测的单作业中位数103.307秒，串行估计46.86小时。磁盘占用在授权前要求基于本轮原生文件实测，不编造估计。

## 11. 产物

- 冻结协议与资产：`configs/projects/ab_atp_synthase/vina_7p3w_v1/`
- 执行与审计：`results/phase13/`
- 原生pose清单：`results/phase13/pose_artifact_manifest.csv`
- Registry导出：`results/phase13/evidence_registry_export.csv`
- 描述性比较：`results/phase13/open_toolchain_shadow_analysis.csv`
- 恢复验证：`results/phase13/resume_validation.json`
- 1633计划：`results/phase13/HTVS1633_Vina_execution_plan.json`

本报告不将对接分数描述为实验成功率、真实活性或新药发现结论。
