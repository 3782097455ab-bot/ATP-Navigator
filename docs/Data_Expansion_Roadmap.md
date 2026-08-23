# ATP-Navigator Data Expansion Roadmap

目标：在不升级复杂模型的前提下，优先增加可追溯、可分任务、能支持 ATP 合酶候选排序的数据。

## 1. 当前缺口

### 1.1 公开数据库质量缺口

- 公开源有6,777条记录，但清洗后只有363条进入ATP专项层；其中直接 ATP synthesis IC50 的记录仍远少于whole-cell MIC。
- 363条原始记录缺 protein ID；organism、activity type、activity value和unit各缺7条。
- organism字段混合物种、菌株、囊泡体系和人源细胞，需要拆成标准物种、strain和assay system。
- 没有独立的 relation、assay ID、measurement ID、replicate、测试浓度、pH、培养基和时间字段。
- `WSA236`、`WSA238`存在一ID多结构冲突；另有多组同结构多别名，必须建立结构级identity table。
- 来源说明称SMILES已标准化，但仍需在固定RDKit版本下重算 canonical SMILES、InChIKey、盐型/电荷和标准化日志。

### 1.2 ATP-Navigator 内部缺口

- 只有17个静态MM/GBSA候选和2个MD/MMGBSA体系，Top-k模型无法从大量同协议后段标签中学习。
- 两个MD系统轨迹状态仍为 incomplete；当前只有派生的1000帧均值和相互作用导出。
- 1,633个可读HTVS compound ID没有可直接进入统一表的SMILES；004–006分片也不完整。
- IN-2 MD系统到具体标准化结构仍是别名链，不应在未确认前用于结构模型。
- 缺少真实ATP合酶抑制、鲍曼不动杆菌MIC、阴性候选和重复测量，无法评价AI排序是否提升真实命中恢复。

## 2. Priority 1：更多 ATP synthase inhibitor 数据

优先级最高，因为这是从“通用抗菌先验”走向“ATP靶点专项排序”的关键数据。

### 必须采集

- canonical structure、原始structure、InChIKey、盐型和立体化学状态；
- target name、ATP synthase subunit/结合位点、Protein ID、organism、strain/突变体；
- activity type、relation、value、unit、assay system、实验条件、阴/阳性对照；
- inactive/weak compounds和明确测试上限，避免只有正样本；
- DOI、数据库record ID、表格/SI位置、许可和检索日期。

### 接受门槛

- 身份和来源可核验；
- 直接ATP synthesis assay与whole-cell MIC分开；
- 同一系列的所有可用类似物和阴性结果一并提取；
- 不把综述二次汇编值和原始实验值静默合并。

### 预期用途

建立 `L2_ATP_synthesis_IC50` 与同系列MIC辅助任务，形成外部ATP prior，再由内部Layer 3完成候选排序。

## 3. Priority 2：PDBbind相关蛋白—配体数据

### 需要的数据

- PDB ID、结构分辨率、复合物链/位点、配体结构、亲和值类型与单位；
- 蛋白序列/结构与ATP synthase的关系；
- 配体共价性、金属/辅因子、结晶条件和测量来源；
- 数据版本、许可和去重规则。

### 接入规则

- PDBbind不与MIC数据合并；它应形成独立的结构—结合任务。
- 以PDB/蛋白同源组和配体scaffold共同控制泄漏。
- ATP synthase相关或膜蛋白复合物优先；远靶点数据只用于通用结合表征，不作为ATP直接证据。
- 结构质量或亲和力来源不明确的记录进入隔离层。

### 预期用途

为未来蛋白—配体interaction feature、pose质量和结合先验提供基础，而不是替代本项目Schrödinger计算。

## 4. Priority 3：BindingDB结合数据

### 需要的数据

- BindingDB ligand/target record ID、canonical structure；
- target name、UniProt/其他Protein ID、organism；
- Ki、Kd、IC50等原始关系符、数值、单位和assay描述；
- DOI、publication link、数据版本和许可；
- target sequence/variant，尤其ATP synthase亚基和耐药突变体。

### 接入规则

- Ki、Kd和IC50建立不同task view；只在任务内部做单位转换。
- 同一论文/assay重复值保留measurement ID，模型输入前按预注册规则聚合。
- 与ChEMBL重叠记录通过DOI + structure + target + activity type识别，不能简单按compound ID去重。

### 预期用途

扩充可回归的靶点结合数据，并产生结构型external prior。若ATP synthase直接数据仍少，则先用于同源靶点/膜蛋白迁移实验。

## 5. Priority 4：公开虚拟筛选 benchmark

### 需要的数据

- 明确靶点、actives/decoys定义、结构和数据许可；
- docking protocol、receptor structure、pose、score与benchmark split；
- 原始活性证据和decoy生成策略；
- scaffold、近重复和蛋白同源泄漏信息。

### 接入规则

- 不同benchmark和不同docking协议分任务保存。
- 不把人工decoy当作已实验证实inactive。
- 评估重点是NDCG@k、enrichment factor、bedroc/hit recovery等排序指标；不能只报告RMSE。
- 仅在复现实验协议后比较ATP-Navigator排序器与原始docking baseline。

### 预期用途

验证“AI可在传统docking之后改善Top-k排序”这一方法论是否可跨任务复现，而不是宣称发现新药。

## 6. 分阶段执行

| 阶段 | 工作 | 完成标准 |
|---|---|---|
| v1.1 身份与assay标准化 | 解决WSA冲突；重算结构ID；拆分organism/strain/assay；新增relation和measurement ID | 结构冲突清零；所有训练标签可追溯到measurement |
| v1.2 ATP专项扩展 | 扩展ATP synthesis direct assay与inactive compounds | ATP专项任务拥有足够独立scaffold进行group validation |
| v1.3 结合数据层 | 接入PDBbind与BindingDB的独立task views | target、structure、affinity、unit和来源通过质量门槛 |
| v1.4 VS benchmark层 | 接入公开benchmark并复现baseline | 在预注册split上得到可复核Top-k指标 |
| v2.0 迁移准备 | 生成external prior和Layer 3 OOF输入 | 不覆盖现有Model 2；只有稳定改善才升级正式模型 |

## 7. 暂不进入的工作

- 不训练GNN、Transformer或多任务深度网络；
- 不对缺失Docking/MMGBSA/ADMET生成预测填充值作为“真实标签”；
- 不把更多行数本身视为更高质量；
- 不在身份冲突、单位和assay语义未解决时直接启动外部预训练。
