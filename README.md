# ATP-Navigator

吉林大学 ATP-Navigator 项目：面向 ATP 合酶虚拟筛选后实验决策的研究者协作型 AI 候选优先级系统。

AI 用于学习和整合已有虚拟筛选证据，辅助候选排序；当前项目不将计算结果表述为真实生物活性，也不替代 Schrödinger、MD、MM/GBSA 或后续实验验证。

系统位于传统虚拟筛选之后、合成与生物实验之前。它把研究意图、Docking/MMGBSA/ADMET、外部知识、模型分歧和实验预算转化为可审计的候选优先级与下一实验建议。项目不是通用“药物发现平台”。

## Phase 18B 对话式研究工作区

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

访问 `http://127.0.0.1:8501`。核心首页支持“自然语言 → 结构化计划 → 人工确认 → 白名单动作 → Registry结果回到对话”，并提供候选3D pose、团队审查/投票、统一时间线、计算型DBTL和比赛演示模式。它不重训模型、不生成实验结果，也不自动运行不可用后端。详见 [Phase18B用户指南](docs/User_Guide.md) 和 [对话执行说明](docs/Conversational_Execution.md)。

## Phase 11会话工作区与实验回填

```powershell
python src/research_workspace.py --input results/demo/demo_input.csv --interactive
```

输入“状态”“按 atp_mechanism_focused 排序”“解释 Hit3”“比较模式”“查资料 ATP”。写入动作必须确认；会话和结果保存在本地`workspace_local/`。默认是有限命令模式，非自由聊天大模型；可选大模型工具路由尚未真实API联调。

真实实验回填入口是`data/experimental/incoming/`，先使用`data/templates/phase11_feedback_template.csv`。经校验、人工审查后产生独立版本，不自动重训或发布。完整指南：[Phase11 Workspace and Feedback](docs/Phase11_Workspace_and_Feedback_Guide.md)；公开数据与后续需求：[Data Priorities](docs/Phase11_Public_Knowledge_and_Data_Priorities.md)。

已保存的最终演示在`results/phase11_workspace_demo_v1_1/`，包含真实会话工具回执、17候选排序和明确为empty的湿实验反馈评价。未声称实验成功率或成本节约。

## Phase 10完整决策入口

```powershell
python examples/run_navigation_demo.py
python src/navigator_pipeline.py --input candidates.csv --profile atp_mechanism_focused
```

输入模板位于`examples/candidate_input_template.csv`，详细字段和降级规则见`docs/Phase10_Workflow_Input_Spec.md`。完整Demo会生成候选排名、逐候选解释、四模式比较、排名稳定性和10项工作流自评。

## Phase 9 Agent入口

```powershell
python run_decision_agent.py run --profile balanced --budget 6
python run_decision_agent.py explain --compound-id ATP-SMI-874C2DE25FE4
```

决策配置位于 `config/decision_agent_v1.json`。当前 P(Top-k) 仅表示候选在声明的权重分布下进入 Top-k 的频率，不是活性概率。项目战略、比赛叙事和真实实验路线见 `docs/ATP_Navigator_Project_Strategy_Master_Brief.md`。

## 仓库结构

```text
ATP-Navigator/
├─ data/                 数据资产、外部数据接入和论文来源记录
├─ src/                  数据处理、特征工程、训练和评价代码
├─ models/               已保存的小型模型文件
├─ results/              指标、排序结果和图表
├─ docs/                 数据审计、方法与阶段报告
├─ config/               透明决策权重与Agent运行配置
├─ configs/              Phase 10研究模式和工作流权重
├─ examples/             一键比赛Demo与候选输入模板
├─ tests/                可复现性和科学边界测试
├─ notebooks/            探索性分析
└─ competition/          比赛交付文件的整理入口
```

## 团队新增数据放置位置

- 新收集、尚未审计的 CSV：`data/external/incoming/`
- 已完成字段检查和来源核验的数据：`data/external/curated/`
- 论文与数据库来源记录：`data/literature/references.csv`
- 比赛最终提交材料：`competition/submission/`

上传新数据前请阅读 `data/external/incoming/README.md`，并填写同目录的 `submission_manifest.csv`。不要上传虚拟环境、缓存、未获授权的论文全文或大型 MD 轨迹。

## 数据更新流程

```text
组员上传 incoming
        ↓
来源与许可核验
        ↓
格式、SMILES、单位和重复项审计
        ↓
进入 curated / 统一 Dataset
        ↓
按任务分层训练和评估
```

MIC、IC50、Ki、Kd、Docking score 和 MM/GBSA 不会被直接混合作为同一个标签。现有 baseline 始终保留为对照。

## 当前科学边界

- 已完成：真实计算链、数据资产化、Model v0-v4-alpha对照、Decision Engine、稳健决策Agent；
- 已集成：候选输入、结构处理、冻结模型工具、四目标决策、研究模式、解释和自评审计的一次运行工作流；
- 未完成：ATP synthase活性、MIC/MBC、实验毒性与独立前瞻验证；
- 禁止：用预测或人工填写数值代替实验结果，或把NMR/LC-MS结构确证表述为生物活性验证。
