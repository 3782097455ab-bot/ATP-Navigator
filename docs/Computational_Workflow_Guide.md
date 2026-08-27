# Multi-Backend Computational Workflow：运行与验收

日期：2026-08-27。定位：实验前计算证据整合与候选优先级辅助决策。此轮没有训练模型，也没有修改冻结评分公式。

## 本机验收结论

| 项目 | 实测状态 |
|---|---|
| Schrödinger安装 | Windows安装登记定位到`D:/xuedinge the beginning`；`D:/Schrodinger`主要是安装介质 |
| Glide 10.3 | 帮助命令成功；真实计算未成功执行，产品许可签出未通过 |
| Prime/PSP 7.6 | 帮助命令成功；MM/GBSA未执行，产品许可签出未通过 |
| QikProp 8.0 | 帮助命令成功；性质预测未执行，产品许可签出未通过 |
| LigPrep（MacroModel 14.4包） | 产品可启动，许可签出未通过 |
| 标准Windows环境 | 工具子进程补齐WINDIR/SystemRoot；没有修改系统环境或许可 |
| RDKit 2026.03.5、Meeko 0.7.1 | 可执行；已真实生成结构、3D配体、PDBQT与性质 |
| AutoDock Vina 1.2.7 | 真实执行成功：官方1IEP/伊马替尼软件测试，1个化合物，affinity=-12.478 kcal/mol |
| 7P3W的3候选新计算 | 已真实做结构处理并产生阻塞记录；完整新计算链未跑通，缺许可和确认协议/grid/box |
| 17内部候选 | decision_only重放历史计算证据，输出6个候选；不是17次新对接。综合分数相对Phase12冻结结果最大差异0 |
| 1633候选 | 本轮没有重新运行高成本步骤；未声称完成1633个新MM/GBSA |
| 模型与实验 | 原24模型hash不变；旧模型、评分公式和权重无改动；反馈仍empty，前瞻指标not_available |

Vina测试完成了真实配体准备→对接→Pose QC→解析→Evidence Registry→完整性判断。受体使用官方已准备PDBQT，经过哈希检查与导入；不是本轮从7P3W原始PDB完成受体准备。官方1IEP属于非ATP的软件测试，不进入ATP训练/效能验证，也没有实验候选面板。

完整性判断正确指出缺少MM/GBSA、ADMET及冻结Glide模型的后端兼容性，final_score保持unknown。这不是商业全流程已经完成。

## 三种模式

- `commercial_full`：实际产品可用且许可签出成功、协议确认后，调度RDKit/LigPrep/Glide/Prime/QikProp。当前本机阻塞。商业adapter实现了输入准备、原生命令、输出解析接口，但未完成本机真实数值链验收。
- `open_toolchain`：RDKit/Meeko/Vina。准备工具缺失时阻塞，不跳过；可读已准备PDBQT，也可按确认的`meeko_preprotonated_pdb`协议调用Meeko准备已完成质子化处理的PDB。没有自动猜测质子化/缺残基修复。GNINA/OpenMM/gmx_MMPBSA仅保留接口，不声称可运行。
- `decision_only`：导入已有计算证据，必须提供来源工具/来源批次/协议。未识别的Docking后端不得默认为Glide。导入记录仍属于historical_result，不改写成tool_execution。

## 运行

在项目根目录使用已安装依赖的Python。Windows当前解释器为`.venv/Scripts/python.exe`。

```powershell
# 真实探测；版本化快照另存，results/system_capabilities.json为最新索引。
python src/run_computational_workflow.py inspect

# 创建计划，不运行昂贵计算。
python src/run_computational_workflow.py plan --project ab_atp_synthase --input data/external/incoming/candidates.csv --mode open_toolchain --protocol configs/projects/my_confirmed_vina_protocol.json --intent "ATP机制优先，Docking最多5个，MMGBSA最多3个，最后实验验证2个"

# 复核结构化意图、协议及预算后明确确认。
python src/run_computational_workflow.py resume <run_id> --confirm
python src/run_computational_workflow.py status <run_id>
python src/run_computational_workflow.py resume <run_id>
# failed不盲目重试；处理原因后显式允许重试。
python src/run_computational_workflow.py resume <run_id> --retry-failed
```

新协议必须使用新`protocol_id`，包含receptor路径/hash、明确box中心/尺寸、seed/exhaustiveness、配体准备/质子化策略和研究者确认。不能把新Vina盒或新Glide grid称为历史等价物。现有`configs/projects/ab_atp_synthase/`五份清单明确保留未知值，不能直接作为可执行新协议。

Vina小规模新协议的配体准备合同为`ETKDGv3_MMFF_preserve_input`；它保留输入质子化/盐型，没有执行pH枚举。原始PDBQT缺少可独立确认的化学键信息；Pose QC当前仅查坐标有限性和盒中心范围，不是结合正确性验证。

## 对话与共享状态

同一个`workspace_local/workspace.sqlite3`承载旧会话、候选、协议、计算批次/任务、证据、决策和反馈关联。

已有项目会话支持：

- `现在还缺什么证据？`、`为什么还不能排名1633个？`：查询该会话真实候选集合，不把问题中的1633当成已上传数量。
- `计划计算 ATP机制优先，MMGBSA最多40个，最后实验验证6个`：沿用会话的已选候选/受体/后端上下文，生成待确认的新运行；不会替用户猜新位点。
- `确认计算 <run_id>`：只能确认属于该会话的运行。
- `恢复计算 <run_id>`：继续已确认运行，不能绕过首次确认。

这是有限命令路由和真实工具执行，不是已实现任意自然语言理解。对话、工作区、决策没有三份平行数据。

## 任务图、预算和分数边界

持久化DAG包含导入、结构QC、受体准备、配体准备、商业LigPrep、Docking、可选XP、Pose QC、MM/GBSA、性质、完整性和决策。执行器按依赖拓扑调度，拒绝环和未知依赖。性质可走独立分支，预算和完成情况写入选择清单/执行快照。

分层预算默认62.5% exploitation、25%已观测uncertainty/disagreement、12.5%骨架多样性，配置在`configs/acquisition_policy.json`。未知uncertainty保留unknown，不能填成估计值；该层没有合格候选时，明确标注fallback。启发式选择使用当前同来源批次排序、证据完整度、观测分歧、多样性和相对成本，不是活性概率或已验证信息增益。

Glide、Glide XP、Vina和Prime各自保留证据类型/工具版本/协议/来源运行/任务/hash。直接batch-relative ranking仅在同工具、版本、协议、来源批次及证据类型的cohort内；跨cohort输出cross_protocol，不混合能量。Vina affinity不注入冻结Glide模型的docking_score字段；QikProp或RDKit性质不能冒充实验ADMET。

## 缓存、恢复与输出

- 计算任务保存输入artifact hash、协议hash、工具版本、可执行文件hash和worker hash；同一项目内已完成签名复用，不重复启动。
- 独立supervisor保存命令、stdout/stderr、PID/创建时间、结果及原生文件hash、receipt。父流程断线后可恢复已完成结果并幂等入库。
- 无receipt且进程身份不明：保留未确定状态，不冒险启动第二份；确认进程已消失时标记failed，显式重试。
- 计算执行后未完成证据事务的恢复有回归测试；普通resume及决策缓存已在真实Vina任务上核验。
- `workspace_local/`包含本地原生结果、可执行程序和会话数据库，不进入Git。各次`results/multibackend/<run_id>/`保留计划、选择原因和决策导出；旧输出不覆盖。

本轮四个验证项目共254条证据登记：49条真实工具输出（其中只有1条Vina affinity）、85条历史计算证据、120条冻结模型输出。不是254条新实验。分类详情及模型完整性在最终验收JSON中。

## 实验反馈与未来API

原FeedbackStore的上传→QC→人工审查→独立snapshot流程未重写。新增链接把calculation_run_id、decision_run_id、candidate_panel_id与已审查experiment_run_id关联；没有真实审查批次时拒绝链接，保持empty。链接本身不证明前瞻时间顺序，也不自动训练/替换模型。

`WorkflowService.request(method,path,payload)`是已测试的进程内接口，不是已经部署的HTTP服务：

| 路径 | 当前能力 |
|---|---|
| `/projects` | GET列表、POST项目ID |
| `/projects/{id}/candidates` | GET共享候选 |
| `/projects/{id}/jobs` | GET共享任务状态 |
| `/projects/{id}/evidence` | GET含backend/protocol/run/job/hash的证据 |
| `/projects/{id}/decisions` | GET冻结决策记录 |
| `/projects/{id}/experiments` | GET审查状态/链接；POST关联已审查批次 |
| `/projects/{id}/chat` | POST已关联会话消息 |
| `/projects/{id}/runs` | GET计划；POST创建/确认/恢复 |

尚未部署网页、认证HTTP服务或跨机器调度。CLI是当前实际入口。

## 验证来源和限制

首轮完整记录：`results/multibackend/validation_a4b4c0a3/`；首次90测试通过。后续增加会话/反馈/DAG测试后94项通过。最终代码验收：`results/multibackend/final_checks_0de2ce02/final_acceptance.json`，9项检查全部通过；包含辅助启动器检查。前次`final_checks_b3815219`也全部通过。保留初次`final_checks_e804db9f`汇总JSON类型导出错误对应的已完成检查产物；修复后另存新目录，没有重跑对接。

参考官方[AutoDock Vina基本对接教程](https://autodock-vina.readthedocs.io/en/latest/docking_basic.html)、[Vina v1.2.7发行](https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.7)、[Schrödinger DockingLicense接口](https://learn.schrodinger.com/public/python_api/2026-2/api/schrodinger.glide.html)。实际安装为2024-2产品包；许可特征也结合本地产品启动脚本核对。初次Glide探测使用旧IMPACT_GLIDE项，最终改为GLIDE_MAIN/SP/XP并重新签出核验，仍未通过。

Phase 13已经从历史PPT、VSW、SiteMap和IN-2 pose恢复了可追溯7P3W位点，并冻结`vina_7p3w_v1`。box中心为(198.147968, 182.436946, 155.933369) Å，三轴尺寸均为25.991257 Å，逐字取自`VSW.maegz`历史gridbox属性。它是`derived_from_historical_site`，不是Glide等价协议。

本项目已真实完成IN-2+17内部候选的Vina链；5候选门控5/5、内部候选17/17、pose QC全部通过。Agent可问“Hit3目前有哪些Docking证据？”和“Vina和Glide对哪些候选分歧最大？”，回答来自共享Registry并保留tool family/protocol。受控暂停恢复、缓存不重算和输出hash保持已实测。

当前最关键外部缺口改为：合法商业许可；开放工具链MM/GBSA/ADMET的明确协议、校准和小规模验证；以及真实ATP酶/MIC/毒性实验回流。1633候选仍未执行，仅有计划。Vina与历史Glide排序在n=17上Spearman -0.0196、Kendall 0.0000、Top-5 overlap 1/5，该结果只说明协议分歧，不能作为生物活性验证或后端准确性结论。详见`docs/Phase13_7P3W_Vina_Validation_Report.md`。
