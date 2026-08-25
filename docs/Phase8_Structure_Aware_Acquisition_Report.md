# Phase 8 Structure-aware Acquisition Report

日期：2026-08-25  
状态：v2数据获取队列已建立；未训练或修改模型

## 为什么重做队列

v1建立时HTVS结构尚未提取，只能用Docking/QuickProp连续特征近似多样性。现在1,633个compound均已有RDKit canonical SMILES、Morgan fingerprint和scaffold，因此保留v1作审计对照，新增v2作为当前推荐队列。

## v2三臂设计

1. `exploitation` 20个：保持多评分最优候选；
2. `local_structure_bridge` 20个：选择与内部17候选最接近、同时尽量不同scaffold的结构，修复v4-alpha的化学空间断层；
3. `scaffold_score_exploration` 20个：在10个Docking分位层各取2个结构远离已选集合的scaffold，提供中弱分数和结构负对照。

P0仍为24个，每臂8个；P1为36个，每臂12个。

## 实际结果

- v2候选：60；unique scaffolds：57；P0 scaffolds：24；
- v1/v2重叠：24；v2新增候选：36；
- v2到内部17候选最大Morgan相似度中位数：0.285；
- bridge臂相似度中位数：0.570；
- exploration臂相似度中位数：0.194。

## 当前推荐执行

使用`mmgbsa_acquisition_queue_v2.csv`和`p0_structures_v0_2.sdf`运行首批24个同协议MM/GBSA。v1文件不删除、不覆盖，但不再作为首选执行队列。

## 边界

- Morgan/scaffold只用于数据获取设计，不是活性标签；
- SDF来自原始Docking pose，不代表已完成新的MM/GBSA；
- 所有返回模板中的MM/GBSA值仍为空；
- 下一轮模型训练必须等待P0真实计算结果和protocol QC。
