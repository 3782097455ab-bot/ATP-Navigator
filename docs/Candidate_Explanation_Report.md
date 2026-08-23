# ATP-Navigator Candidate Explanation Report

生成范围：Decision Engine 当前 Top 5 候选。

解释只使用已有结构、Docking、静态 MM/GBSA、Model v3、外部知识 prior 和预测 ADMET。没有把未完成的 MIC、ATP enzyme 或 toxicity 实验写成结果。

## Rank 1 — ATP-SMI-C93E6EC67CDB (Hit2)

综合分数：73.91；置信度：`medium_computational_only` (60.0/100)。该置信度只表示计算证据覆盖，实验验证贡献为 0。

### 结构贡献

- MW 459.06，LogP 2.32，TPSA 62.18，HBD 4，HBA 3，Rotatable bonds 10；
- 通过 6/6 条 descriptor rules；
- 与外部直接 ATP assay 参考结构的最大 Morgan-Tanimoto 相似度为 0.174，最近参考 ID 为 `STEED2022-8`；该参考来源尚未逐条内部复核。

### 结合贡献

- Binding score：90.00；
- Model v3 计算预测：-56.388；Docking score：-8.426；静态 MM/GBSA：-56.560；三者均为计算结果；
- Model v3 与静态 MM/GBSA 相关，不能把两者当作相互独立的实验验证。

### ATP 相关证据

- ATP target score：25.16；
- PA ATP IC50 prior（log10 ug/mL）：1.155；Mtb ATP IC50 prior（log10 nM）：1.557；
- AB ATP prior 保留值 2.702，但因外部子任务不稳定，在配置中权重为 0；
- 当前候选没有已完成的 ATP 酶抑制实验，状态为 `unknown`。

### 成药性评价

- Drug-likeness score：87.04；预测 ADMET risk endpoint sum：7/27；
- Antibacterial score：93.75，来源是外部 AB whole-cell MIC 模型 prior，不是当前候选的实验 MIC。

### 当前未知风险

- MIC 实验：`unknown`；ATP enzyme 实验：`unknown`；实验毒性：`unknown`；
- 未知溶解度、稳定性、渗透/外排影响、选择性和重复实验误差不能由当前 final score 排除；
- 该推荐仅用于决定后续计算复核和实验优先级。

## Rank 2 — ATP-SMI-9DA3213A09E8 (Hit1)

综合分数：71.07；置信度：`medium_computational_only` (60.0/100)。该置信度只表示计算证据覆盖，实验验证贡献为 0。

### 结构贡献

- MW 415.54，LogP 0.98，TPSA 86.83，HBD 3，HBA 3，Rotatable bonds 9；
- 通过 6/6 条 descriptor rules；
- 与外部直接 ATP assay 参考结构的最大 Morgan-Tanimoto 相似度为 0.176，最近参考 ID 为 `STEED2022-8`；该参考来源尚未逐条内部复核。

### 结合贡献

- Binding score：82.50；
- Model v3 计算预测：-56.562；Docking score：-8.121；静态 MM/GBSA：-57.510；三者均为计算结果；
- Model v3 与静态 MM/GBSA 相关，不能把两者当作相互独立的实验验证。

### ATP 相关证据

- ATP target score：50.94；
- PA ATP IC50 prior（log10 ug/mL）：1.002；Mtb ATP IC50 prior（log10 nM）：1.527；
- AB ATP prior 保留值 2.701，但因外部子任务不稳定，在配置中权重为 0；
- 当前候选没有已完成的 ATP 酶抑制实验，状态为 `unknown`。

### 成药性评价

- Drug-likeness score：85.19；预测 ADMET risk endpoint sum：8/27；
- Antibacterial score：56.25，来源是外部 AB whole-cell MIC 模型 prior，不是当前候选的实验 MIC。

### 当前未知风险

- MIC 实验：`unknown`；ATP enzyme 实验：`unknown`；实验毒性：`unknown`；
- 未知溶解度、稳定性、渗透/外排影响、选择性和重复实验误差不能由当前 final score 排除；
- 该推荐仅用于决定后续计算复核和实验优先级。

## Rank 3 — ATP-SMI-5D3E7B6B6796 (Hit4)

综合分数：62.54；置信度：`medium_computational_only` (60.0/100)。该置信度只表示计算证据覆盖，实验验证贡献为 0。

### 结构贡献

- MW 415.47，LogP 4.30，TPSA 89.21，HBD 2，HBA 4，Rotatable bonds 8；
- 通过 6/6 条 descriptor rules；
- 与外部直接 ATP assay 参考结构的最大 Morgan-Tanimoto 相似度为 0.215，最近参考 ID 为 `CHEMBL3402629`；该参考来源尚未逐条内部复核。

### 结合贡献

- Binding score：65.00；
- Model v3 计算预测：-54.627；Docking score：-8.072；静态 MM/GBSA：-54.810；三者均为计算结果；
- Model v3 与静态 MM/GBSA 相关，不能把两者当作相互独立的实验验证。

### ATP 相关证据

- ATP target score：67.03；
- PA ATP IC50 prior（log10 ug/mL）：1.069；Mtb ATP IC50 prior（log10 nM）：1.015；
- AB ATP prior 保留值 2.709，但因外部子任务不稳定，在配置中权重为 0；
- 当前候选没有已完成的 ATP 酶抑制实验，状态为 `unknown`。

### 成药性评价

- Drug-likeness score：85.19；预测 ADMET risk endpoint sum：8/27；
- Antibacterial score：25.00，来源是外部 AB whole-cell MIC 模型 prior，不是当前候选的实验 MIC。

### 当前未知风险

- MIC 实验：`unknown`；ATP enzyme 实验：`unknown`；实验毒性：`unknown`；
- 未知溶解度、稳定性、渗透/外排影响、选择性和重复实验误差不能由当前 final score 排除；
- 该推荐仅用于决定后续计算复核和实验优先级。

## Rank 4 — ATP-SMI-96FD6257D8BA (Hit5)

综合分数：62.50；置信度：`medium_computational_only` (60.0/100)。该置信度只表示计算证据覆盖，实验验证贡献为 0。

### 结构贡献

- MW 454.62，LogP 1.58，TPSA 55.00，HBD 2，HBA 3，Rotatable bonds 8；
- 通过 6/6 条 descriptor rules；
- 与外部直接 ATP assay 参考结构的最大 Morgan-Tanimoto 相似度为 0.200，最近参考 ID 为 `CHEMBL4101131`；该参考来源尚未逐条内部复核。

### 结合贡献

- Binding score：71.25；
- Model v3 计算预测：-52.791；Docking score：-8.373；静态 MM/GBSA：-52.900；三者均为计算结果；
- Model v3 与静态 MM/GBSA 相关，不能把两者当作相互独立的实验验证。

### ATP 相关证据

- ATP target score：66.88；
- PA ATP IC50 prior（log10 ug/mL）：1.045；Mtb ATP IC50 prior（log10 nM）：1.463；
- AB ATP prior 保留值 2.702，但因外部子任务不稳定，在配置中权重为 0；
- 当前候选没有已完成的 ATP 酶抑制实验，状态为 `unknown`。

### 成药性评价

- Drug-likeness score：85.19；预测 ADMET risk endpoint sum：8/27；
- Antibacterial score：6.25，来源是外部 AB whole-cell MIC 模型 prior，不是当前候选的实验 MIC。

### 当前未知风险

- MIC 实验：`unknown`；ATP enzyme 实验：`unknown`；实验毒性：`unknown`；
- 未知溶解度、稳定性、渗透/外排影响、选择性和重复实验误差不能由当前 final score 排除；
- 该推荐仅用于决定后续计算复核和实验优先级。

## Rank 5 — ATP-SMI-E9798004BA11 (Hit6)

综合分数：59.95；置信度：`medium_computational_only` (60.0/100)。该置信度只表示计算证据覆盖，实验验证贡献为 0。

### 结构贡献

- MW 437.58，LogP 1.80，TPSA 71.77，HBD 4，HBA 4，Rotatable bonds 12；
- 通过 5/6 条 descriptor rules；
- 与外部直接 ATP assay 参考结构的最大 Morgan-Tanimoto 相似度为 0.195，最近参考 ID 为 `STEED2022-8`；该参考来源尚未逐条内部复核。

### 结合贡献

- Binding score：63.75；
- Model v3 计算预测：-51.953；Docking score：-8.235；静态 MM/GBSA：-51.990；三者均为计算结果；
- Model v3 与静态 MM/GBSA 相关，不能把两者当作相互独立的实验验证。

### ATP 相关证据

- ATP target score：65.47；
- PA ATP IC50 prior（log10 ug/mL）：1.066；Mtb ATP IC50 prior（log10 nM）：0.984；
- AB ATP prior 保留值 2.687，但因外部子任务不稳定，在配置中权重为 0；
- 当前候选没有已完成的 ATP 酶抑制实验，状态为 `unknown`。

### 成药性评价

- Drug-likeness score：80.56；预测 ADMET risk endpoint sum：6/27；
- Antibacterial score：18.75，来源是外部 AB whole-cell MIC 模型 prior，不是当前候选的实验 MIC。

### 当前未知风险

- MIC 实验：`unknown`；ATP enzyme 实验：`unknown`；实验毒性：`unknown`；
- 未知溶解度、稳定性、渗透/外排影响、选择性和重复实验误差不能由当前 final score 排除；
- 该推荐仅用于决定后续计算复核和实验优先级。
