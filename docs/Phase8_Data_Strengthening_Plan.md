# Phase 8 Data Strengthening Plan

日期：2026-08-24  
状态：数据获取规划已运行；未训练或修改任何模型

## 1. 为什么当前模型不能继续只靠算法变强

- 内部Task C只有17个静态MM/GBSA标签，任何复杂模型都会受到高维小样本限制；
- 现有外部Task B与内部17候选没有精确结构或scaffold重叠，Morgan最近邻相似度也很低；
- MIC、ATP target activity和MM/GBSA属于不同任务，不能通过混合标签制造样本量；
- 当前HTVS库有4,373个pose和1,633个compound ID，但`molecules.csv`中可直接连接的HTVS SMILES为0；
- 所以当前最高价值动作是补内部同协议标签并导出结构，而不是继续增加模型复杂度。

## 2. 本阶段建立的数据增益队列

- 可追溯且达到选择门槛的HTVS候选：1,632；
- 排除已知内部候选映射：1；
- P0首批：24个，由8个exploitation、8个descriptor diversity、8个score calibration组成；
- P1扩展批：36个，三组各12个；
- 总队列：60个，全部保留source file、title、variant、pose index和原始Docking/QuickProp证据。

三个selection arm不是三种活性标签：

1. `exploitation`：检验HTVS多评分最优分子能否在同协议MM/GBSA中保持优势；
2. `descriptor_diversity`：在缺少SMILES前，用Docking/QuickProp连续特征扩展理化覆盖；
3. `score_calibration`：主动加入中等和较弱Docking分子，避免训练集只包含Top hits。

## 3. 强制执行顺序

1. 从`source_file`按title/variant/pose导出精确SDF；
2. 生成canonical SMILES并做结构QC、重复检查和身份回写；
3. 对P0 24个分子执行与现有17候选完全一致的静态MM/GBSA协议；
4. 审计失败/缺失计算，不把失败任务写成数值；
5. P0通过后再运行P1 36个；
6. 标签达到至少41个内部样本后才进入下一轮模型实验；达到77个时再进行正式scaffold benchmark。

上述41和77分别代表当前17+P0 24、当前17+全部队列60，是数据批次里程碑，不是性能保证。

## 4. 湿实验最高价值数据

如果只能做一类实验，优先为当前17候选建立同一protocol下的鲍曼不动杆菌ATP synthase功能/酶抑制数据；其次是同菌株MIC；毒性必须保持独立端点。

实验记录必须包含strain、target construct、assay type、unit、replicate、上下限、protocol ID和QC。未完成结果保持空值或`unknown`。

## 5. 当前限制

- HTVS候选当前没有SMILES，因此本队列的多样性是descriptor-space diversity，不是Morgan/scaffold diversity；
- 队列是数据获取优先级，不是候选活性排名或新药发现结论；
- MM/GBSA是计算标签，不能替代MIC或ATP enzyme实验；
- 是否执行60个MM/GBSA取决于实际计算资源，但应保持P0/P1顺序和同协议要求。

## 6. 可执行产物

- `results/phase8_data_acquisition/mmgbsa_acquisition_queue.csv`
- `results/phase8_data_acquisition/htvs_pool_audit.csv`
- `results/phase8_data_acquisition/data_requirements_priority.csv`
- `data/templates/phase8_mmgbsa_return_template.csv`
- `data/templates/phase8_experimental_activity_template.csv`
- `src/data_acquisition_planner.py`
