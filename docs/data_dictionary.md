# ATP-Navigator Dataset v0.1 数据字典

## 通用规则

- 原始输入仅来自工作区的 `表征/`、`运行/`、`作图/`，构建过程不写入这些目录。
- 路径均为相对工作区根目录的 POSIX 风格路径，便于迁移。
- 空字符串表示当前来源无法确认；不得据文件名或展示顺序推断。
- `canonical_id` 是 v0.1 内部稳定记录键，不等同于 InChIKey，也不声明 SMILES 已进行化学规范化。
- 多个来源或历史别名使用英文分号 `;` 分隔。

## data/raw_manifest.csv

| 字段 | 含义 |
|---|---|
| 文件名 | 原始文件的基本文件名。 |
| 路径 | 相对工作区根目录的原始文件路径。 |
| 文件类型 | 扩展名（不含点）；百度云下载残片记为 `download-fragment`，无扩展名记为 `no-extension`。 |
| 大小 | 文件字节数，整数。 |
| hash | 原始文件内容的 SHA-256 十六进制摘要。 |
| 所属模块 | `表征`、`运行` 或 `作图`。 |
| 状态 | `complete`：完成了当前文件级读取/格式验证；`incomplete`：下载残片、空文件或全零占位；`corrupted`：预期文本型文件存在显著异常空字节；`derived`：分析、绘图或展示产物；`unknown`：仅凭当前扫描无法确认语义完整性。状态不代表整个科研 workflow 是否完整。 |

## data/molecules.csv

| 字段 | 含义 |
|---|---|
| canonical_id | v0.1 项目内部记录键。`ATP-HTVS-*` 由来源 compound code 生成；`ATP-SMI-*` 由来源 SMILES 原文生成；其他为明确来源实体键。 |
| historical_alias | 来源中直接出现的历史名称或编号；未确认留空。 |
| structure_file | 含该条目结构记录的来源文件；不能确认结构对应关系时留空。 |
| smiles | 来源直接提供的 SMILES；未做结构推断或规范化，缺失留空。 |
| source | 支持该记录的来源文件。 |
| confidence | v0.1 证据类型：`source_structure_record`、`source_smiles_exact`、`structure_file_only` 或 `source_alias_only`。它描述来源确定性，不代表生物活性可信度。 |

## data/screening_records.csv

| 字段 | 含义 |
|---|---|
| canonical_id | 对应 `molecules.csv` 的记录键；ADMET 来源无法映射时留空。 |
| stage | `HTVS`、`Docking`、`MMGBSA` 或 `ADMET`。v0.1 没有可独立确认的结构化 Docking（非 HTVS）记录，因此该阶段当前为 0 行。 |
| score | 来源数值。HTVS 为 `r_i_docking_score`；VSW 为来源列 `MMGBSA dG Bind`；两套 MD 为 1000 帧 `r_psp_MMGBSA_dG_Bind` 的算术均值；ADMET 为源工作簿末列 `SUM(B:AB)` 公式所定义的 27 个二元端点之和（该末列表头在源文件中为空）。空值表示来源行没有可放入本窄表的单一聚合分数。 |
| source_file | 产生该记录的直接来源文件。 |

## data/systems.csv

| 字段 | 含义 |
|---|---|
| system_id | v0.1 MD 体系键。 |
| ligand_id | 对应 `molecules.csv` 的配体记录键；不据推断把 HIT 映射到 Top-1/Top-3/466。 |
| protein | 当前来源中明确的蛋白结构标识，本批数据为 `7P3W`。 |
| trajectory_status | 原始轨迹状态；当前两套 XTC 均为 `incomplete` 下载残片。 |
| source | 体系的原始/衍生来源路径。 |
