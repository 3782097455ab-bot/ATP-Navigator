# Phase 16 Molecule Expansion Engine Report

日期：2026-08-28  
状态：完成；未训练Model v5；未修改Model v0–v4-alpha、Decision Engine、历史Glide/MMGBSA、`vina_7p3w_v1`或Phase 15结果

## 1. 实现范围

本阶段打通：严格seed → 受控R-group扩展 → Generated Candidate Registry → 化学QC → novelty/diversity/tractability筛选 → 冻结Vina → generated acquisition。只验证小规模、真实、可追溯闭环，不将生成分子当作训练标签。

## 2. Generator能力

- RDKit R-group enumeration真实可用：IN-2与Hit3各生成200 raw；
- CReM：unavailable，Python module未发现，生成0；没有临时伪造fragment库；
- REINVENT4：unavailable，executable/module未发现，生成0；没有模拟输出；
- 因只有一个真实backend，不进行虚假的跨backend优劣结论。

Hit3使用项目已经保存的内部历史结构作为独立seed，`source=internal_historical_structure`、`htvs_identity=unresolved`；没有将其映射到任意HTVS-1633 ID。

## 3. Generation与QC

| seed | raw | valid | unique |
|---|---:|---:|---:|
| IN-2 | 200 | 200 | 200 |
| Hit3 | 200 | 200 | 160 |
| 合计 | 400 | 400 | 360 |

40条被明确记录为`generated_duplicate`；invalid、parent duplicate和HTVS-1633 exact duplicate均为0。所有删除均保存在`generation_qc.csv`，没有静默丢弃。

每个正式候选保存parent结构hash、generator/version/config、random seed、reaction template、building block、attachment atom、canonical SMILES、InChIKey、Murcko scaffold、timestamp和provenance hash。

## 4. 性质、警示与可合成性代理

对360个unique结构计算MW、cLogP、TPSA、HBD/HBA、rotatable bonds、formal charge、ring count、fractionCSP3、PAINS、结构警示和透明SA-like tractability proxy。经验规则只登记为descriptor/warning，不包装成活性规则。

AiZynthFinder探测结果：`unavailable / executable_and_python_module_not_found`，retrosynthesis run=0，不阻塞Phase 16。SA-like分数不是合成路线可行性证明。

## 5. Novelty、diversity与collapse检查

- validity=1.000；uniqueness=0.900；
- mean novelty vs parent=0.2411；
- mean novelty vs HTVS-1633=0.5666；
- mean pairwise similarity=0.4135；internal diversity=0.5865；
- 74个Murcko scaffolds；scaffold diversity=0.2056；
- scaffold retention=0.800；
- HTVS-1633 exact duplicate=0；
- generator collapse=false。

Novelty只表示结构距离，不表示活性、新颖专利性或合成可行性。

## 6. Cheap screening与真实Vina

360个unique候选先按validity、property tractability、novelty、diversity、scaffold retention和warnings形成cheap screening score，再以结构多样性贪心选择120个进入Vina。没有对全部raw结构直接Docking。

120个候选使用完全冻结`vina_7p3w_v1`、8并发真实执行：120 success、0 failed、120 pose QC pass。Vina affinity范围-9.438至-6.483 kcal/mol，均值-7.9363。protocol hash、receptor hash、tool hash、ligand hash、pose hash和job signature逐候选保存；generated evidence与historical1633通过`ATP-GEN-*`身份和独立目录隔离。

## 7. Generated acquisition

生成候选的acquisition score由Vina 0.25、tractability 0.20、novelty 0.20、diversity 0.15、warning-free 0.10、scaffold retention 0.10组成。Vina不是单一目标。

最终`generated_acquisition_panel_v1.csv`包含30个候选，保存generated-pool Vina rank、parent Vina对照、diversity、novelty、综合score和推荐的下一份证据。该面板是计算证据获取优先级，不是生物活性或实验命中声明。

## 8. Research Agent

Research Workspace新增只读`generation_query`，可回答IN-2已有100候选、parent、R-group、generator、parent similarity、最远离HTVS-1633候选、MM/GBSA建议和RAW淘汰原因。Agent只读取Registry和真实计算结果。

## 9. 输出

- `generated_candidate_registry.csv`
- `generation_lineage.csv`
- `generation_qc.csv`
- `generator_benchmark.csv`
- `generated_chemical_space.csv`
- `generated_screening_pool.csv`
- `generated_vina_results.csv`
- `generated_acquisition_panel_v1.csv`
- `generator_backend_status.json`
- `synthesis_feasibility_status.json`
- `figures/`

## 10. 限制

- 只有RDKit backend真实可用；没有深度生成模型比较；
- R-group枚举的chemical validity不等于真实反应可达性；
- PAINS和SA-like均为警示/代理；
- Vina不能证明ATP抑制、MIC、毒性或实验成功；
- 尚无generated candidate的MM/GBSA或湿实验结果；
- 不进行Model v5训练，不将生成分数回流为label。

## 11. 验收

- 完整历史测试与Phase 16新增测试：154/154通过；
- 24个受保护模型文件逐文件SHA-256 mismatch=0；
- Phase 15冻结结果未修改；
- 120份Vina pose已导出并逐份校验hash；
- 未进入下一阶段。
