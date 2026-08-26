# Phase 12 — Computational Execution Workspace

日期：2026-08-26。定位：实验前计算证据整合与候选优先级辅助决策系统。

## 已实际运行的范围

- RDKit 2026.03.5可用，无商业许可证签出要求。17个内部候选和1,633个HTVS候选均运行了真实RDKit子进程，计算canonical SMILES、Morgan1024、scaffold及描述符。
- 当前受检环境没有设置SCHRODINGER，PATH和常见安装目录没有发现glide、prime_mmgbsa、qikprop、ligprep、structconvert、jobcontrol。状态为`not_found`，不能声称已安装但无许可证；商业许可证状态为未检测到。
- 找到历史`7P3W-A.pdb`并保存SHA256；没有找到可确认的Glide grid或完整输入协议。不能将这份PDB自动等同于历史prepared receptor。
- 内部17候选：真实结构计算 → 共享Evidence Registry → 保留模型 → 原四分量决策/稳健排序 → 6个计算优先候选。历史结合/ADMET数值明确标记historical_result；并非本轮重新计算或实验验证。
- HTVS 1,633候选：结构计算及冻结模型调用完成；由于缺少MM/GBSA、完整ADMET证据，完整决策数为0、实验候选面板为空。系统没有为了达到6个预算而补分或改变缺失权重规则。
- 商业计算成功数为0。内部演示36个blocked job；HTVS演示402个blocked job（包括未满足前级证据的门控占位job，不代表402次工具调用）。

最终演示：`results/phase12/internal_17_run2/`、`results/phase12/htvs_1633_run2/`。第一轮结果保留；HTVS首轮已完成计算和评分，但空值摘要序列化失败，修复后第二轮复用计算并完成记录。

## 运行入口

在项目目录、使用原有Python环境：

```powershell
.venv\Scripts\python.exe src\run_research_workspace.py --project atp_synthase --library internal --intent "ATP机制优先，MMGBSA最多40个，最终实验预算6个"
.venv\Scripts\python.exe src\run_research_workspace.py --project atp_synthase --library htvs --intent "ATP机制优先，候选1633个，MMGBSA最多40个，最终实验预算6个"
```

先显示结构化意图，再确认。`--yes`仅确认本次计划，不会把unknown协议或许可证变成可用。默认库是17个内部候选，不是1633个；候选数量与声明不符时拒绝继续。输入语言当前是有限规则解析，不是通用LLM理解。

`--session SESSION_ID`沿用Phase11会话的冻结候选快照；新运行生成的新session也能由原`research_workspace.py --session ... --message "状态"`或“解释 Hit5”读取。会话与执行均使用`workspace_local/workspace.sqlite3`。

```powershell
.venv\Scripts\python.exe src\run_research_workspace.py --resume-batch BATCH_ID
```

恢复入口读取独立supervisor保存的receipt并幂等登记证据。没有receipt的running job不会盲目重复提交；需检查进程/工具作业状态。失败任务须显式retry；重提相同意图时，相同输入内容/候选/工具/协议/命令签名复用成功计算。取消状态和非法状态转换也受约束。

## 共享状态与来源

新增表：execution_project、candidate、protocol、calculation_batch、calculation_job、calculation_artifact、evidence、decision_run、feedback_link、knowledge_record；保留原sessions/events/proposals。

每条证据包含compound_id、类型、原始值、normalized_value、单位、protocol_id、tool_version、source_job_id、artifact_hash、timestamp和来源。无法定义的标准化值为null，未知单位为unknown，不擅自换算。数值来源仅限真实工具、可追溯历史结果或冻结模型；文献测量不直接变成内部候选的实验结果。

CSV是SQLite的可追溯导出视图，不是第三套独立数据源。结合证据按所选protocol读取；不能悄悄混用不同协议的Docking和MM/GBSA。化学性质保留各自来源。冻结模型继续执行原完整性门控，必要分量缺失则final_score unknown。

原FeedbackStore不重写、不自动训练。已有审查快照通过candidate_id/project_id/assay protocol/decision_run_id/model_version建立索引；链接本身不能证明前瞻性时间关系。当前真实反馈0，status=empty，prospective_metrics=not_available。

## 预算与stage gate

Structure QC → HTVS → SP → XP → MMGBSA → 可选MD；QikProp从Structure QC分支。默认SP预算200、XP100、MMGBSA40、实验6、MD0。QikProp第一版预算沿用SP预算，并在计划中显式显示。

`gate()`支持top-k、percentile、scaffold多样性、观察到的不确定性阈值和相对成本上限。前级未完成时，后级预算保留为deferred slots，不能当作已选中或已执行的候选。历史协议与新协议的继承须在冻结配置中列出`approved_predecessor_protocol_ids`。

acquisition是可解释启发式：

`(.40×rank utility + .20×missing evidence + .15×observed uncertainty + .15×model disagreement + .10×new scaffold) / relative cost`

unknown不确定性仍显示unknown；其启发式项不计入，不称为测得“零不确定性”。可用时读取冻结稳健排名区间和已有v3/v4-alpha OOF排名差异。relative cost是规划单位，不是实测人民币或运行秒数。该分数不是生物活性概率，也不是经验证的期望信息增益。

## 商业工具接入条件与限制

商业adapter代码会调用真实命令，不生成模拟值；但本机没有环境，因此只能完成解析器/命令状态机单元测试，不能宣称已完成Glide/Prime/QikProp端到端认证。

接入须提供：可执行环境、实际许可证、已确认且hash-pinned的receptor/grid、force field/protonation/ligand preparation、允许的docking mode、MMGBSA配置，以及逐候选prepared input/poseviewer。使用`--protocol`显式提交新ID的协议。unknown保持阻塞；不会自动建grid或用RDKit的2D结构冒充LigPrep产物。Desmond仅注册预留，未实现MD运行adapter。

许可探测首先使用官方只读`run lictool status`。服务器状态不能证明具体工具可签出；管理员可提供`configs/workspace_license_features.json`（工具名到真实feature名称列表），程序通过实际`lictest`检验，不接受“licensed=true”作为证据。许可证feature映射仍须与实际安装版本核对。

官方接口依据：[许可证检查](https://learn.schrodinger.com/public/getting-started/2025-3/system_requirements/Content/licensing/licmgr-server_identify_install.htm)、[QikProp原生任务](https://learn.schrodinger.com/public/python_api/2022-3/_modules/schrodinger/application/livedesign/tasks.html)、[Prime流程](https://learn.schrodinger.com/public/python_api/2022-2/_modules/schrodinger/pipeline/stages/prime.html)。

## 新增四表的独立QC

587条记录登记到knowledge_record：ATP87（7条target annotation冲突隔离，80待来源核查）；SAR352按target/organism/strain/endpoint/unit/assay隔离，保留不等号；结构28进入结构参考层；bridge120只允许未核实检索，不训练。

PapD相关原文确为菌毛形成/伴侣蛋白研究，不能据此构造ATP合酶标签：[原始论文](https://pmc.ncbi.nlm.nih.gov/articles/PMC3665338/)。数据问题统一表述为数据语义一致性、target annotation、endpoint segregation和provenance QC。

## 验收与复现

`examples/verify_phase12.py`运行全量旧/新测试，核对演示数量、unknown、blocked产物、24个模型SHA256、冻结代码/配置以及内部排名与Phase10一致性。机器可读结果和完整日志位于`results/phase12/verification/`。

Phase11已先独立提交并推送：`481faed9ebec6df09143fe34a98b181426ac800d`。Phase12是独立后续提交；未训练任何新监督模型，未改Model v0-v4-alpha及原Decision Engine逻辑。
