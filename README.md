# ATP-Navigator

吉林大学 ATP-Navigator 项目：面向 ATP 合酶虚拟筛选后实验决策的研究者协作型 AI 候选优先级系统。

AI 用于学习和整合已有虚拟筛选证据，辅助候选排序；当前项目不将计算结果表述为真实生物活性，也不替代 Schrödinger、MD、MM/GBSA 或后续实验验证。

系统位于传统虚拟筛选之后、合成与生物实验之前。它把研究意图、Docking/MMGBSA/ADMET、外部知识、模型分歧和实验预算转化为可审计的候选优先级与下一实验建议。项目不是通用“药物发现平台”。

## 当前主入口

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
- 未完成：ATP synthase活性、MIC/MBC、实验毒性与独立前瞻验证；
- 禁止：用预测或人工填写数值代替实验结果，或把NMR/LC-MS结构确证表述为生物活性验证。
