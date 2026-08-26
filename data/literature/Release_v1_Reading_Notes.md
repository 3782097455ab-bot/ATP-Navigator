# 五篇ATP合酶研究：归档与项目使用边界

本地全文：`papers/atp_release_v1/{PMCID}.xml`与`.txt`。XML保留表格、方法、图示引用和补充材料链接；不是只有摘要。全文默认不进入Git；许可与原始内容hash见`release_v1_papers*.json`。这些资料用于理解外部证据，不代表内部Hit已完成实验。

| 文献 | 本项目应保留的信息 | 不应作出的推断 |
|---|---|---|
| [ACS Omega 2025：吡啶系列](https://pmc.ncbi.nlm.nih.gov/articles/PMC12509006/) | 鲍曼ATP synthesis、整菌MIC、ETC及不同处理条件分开；注意通透性可能限制整菌效果 | 不能把外部系列的酶学值赋给本项目候选 |
| [ChemMedChem 2025：喹啉系列](https://pmc.ncbi.nlm.nih.gov/articles/PMC12091843/) | AB与PA分别评价；同编号跨菌种不是重复标签，也不是同一assay | 不能仅因同为ATP合酶就跨菌种直接合并数值 |
| [ACS Infectious Diseases 2023：c-ring研究](https://pmc.ncbi.nlm.nih.gov/articles/PMC10714390/) | 突变与酶学实验提供作用位点相关证据，强于单一Docking示意；保留证据类型 | 不能把文献位点证据称为本项目候选位点已证实 |
| [ACS Medicinal Chemistry Letters 2024：侧链碱性](https://pmc.ncbi.nlm.nih.gov/articles/PMC10789121/) | 侧链碱性与整菌表现为区分“酶学潜力”和“整菌表现”提供线索；质子化协议重要 | 不能把可预测理化性质直接当作实测通透性或MIC |
| [ACS Omega 2022：初始SAR](https://pmc.ncbi.nlm.nih.gov/articles/PMC9386795/) | ATP synthesis dose response与ETC测量分开；保留relative IC50和残余活性的原文语境 | 酶学抑制不自动等于野生型整菌有效 |

建议增加的决策呈现能力：分别展示“靶点功能证据”“机制区分证据”“整菌效应”“分子性质”，同时显示菌株、assay、数值关系、单位和来源。该建议是基于文献的工作流推论；当前没有借此修改冻结评分或声称实验成功率。

质量提醒：发布包声称按结构图重建的身份，在本轮通过了InChIKey/分子式/MW自动核查，但没有被逐键重新绘制验证；结构公式一致只能排除部分错误。补充材料中的精确条件与原文定位应继续逐条复核，尤其mass→molar转换所用的化合物形式。
