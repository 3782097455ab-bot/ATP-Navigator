# ATP-Navigator

吉林大学 ATP-Navigator 项目：基于鲍曼不动杆菌 F1F0-ATP 合酶真实虚拟筛选案例构建的 AI 增强型候选优先级排序系统。

AI 用于学习和整合已有虚拟筛选证据，辅助候选排序；当前项目不将计算结果表述为真实生物活性，也不替代 Schrödinger、MD、MM/GBSA 或后续实验验证。

## 仓库结构

```text
ATP-Navigator/
├─ data/                 数据资产、外部数据接入和论文来源记录
├─ src/                  数据处理、特征工程、训练和评价代码
├─ models/               已保存的小型模型文件
├─ results/              指标、排序结果和图表
├─ docs/                 数据审计、方法与阶段报告
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
