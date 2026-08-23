import crypto from "node:crypto";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import zlib from "node:zlib";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const workspaceRoot = path.resolve(projectRoot, "..");
const dataDir = path.join(projectRoot, "data");
const sourceModules = ["表征", "运行", "作图"];

const rel = (p) => path.relative(workspaceRoot, p).split(path.sep).join("/");

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function toCsv(headers, rows) {
  return [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))]
    .map((row) => row.map(csvCell).join(","))
    .join("\r\n") + "\r\n";
}

async function writeValidatedCsv(filePath, headers, rows) {
  const csvText = toCsv(headers, rows);
  const workbook = await Workbook.fromCSV(csvText, { sheetName: "data" });
  const sheet = workbook.worksheets.getItemAt(0);
  const used = sheet.getUsedRange(true);
  if (!used) throw new Error(`CSV validation failed: ${filePath}`);
  await workbook.inspect({
    kind: "region",
    sheetId: sheet.name,
    range: used.address,
    maxChars: 1000,
    tableMaxRows: 3,
    tableMaxCols: headers.length,
  });
  await fsp.writeFile(filePath, csvText, "utf8");
}

async function walkFiles(root) {
  const output = [];
  const entries = await fsp.readdir(root, { withFileTypes: true });
  entries.sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
  for (const entry of entries) {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) output.push(...(await walkFiles(fullPath)));
    else if (entry.isFile()) output.push(fullPath);
  }
  return output;
}

function fileType(filePath) {
  const lower = filePath.toLowerCase();
  if (lower.endsWith(".baiduyun.p.downloading")) return "download-fragment";
  const ext = path.extname(lower);
  return ext ? ext.slice(1) : "no-extension";
}

async function fingerprint(filePath) {
  const stat = await fsp.stat(filePath);
  const hash = crypto.createHash("sha256");
  let zeroBytes = 0;
  let first = Buffer.alloc(0);
  let tail = Buffer.alloc(0);
  for await (const chunk of fs.createReadStream(filePath)) {
    hash.update(chunk);
    if (first.length < 16) first = Buffer.concat([first, chunk]).subarray(0, 16);
    tail = Buffer.concat([tail, chunk]).subarray(-64);
    for (const byte of chunk) if (byte === 0) zeroBytes += 1;
  }
  return {
    size: stat.size,
    sha256: hash.digest("hex"),
    zeroBytes,
    first,
    tail,
  };
}

const textLike = new Set(["csv", "dat", "eaf", "json", "log", "mae", "md", "pdb", "py", "sh", "smi", "svg", "txt", "xml"]);

function classifyFile(moduleName, filePath, info, verifiedHtvs) {
  const relativePath = rel(filePath);
  const lower = relativePath.toLowerCase();
  const type = fileType(filePath);
  if (info.size === 0 || lower.includes(".downloading")) return "incomplete";
  if (info.zeroBytes === info.size) return "incomplete";
  if (textLike.has(type) && info.zeroBytes / info.size > 0.01) return "corrupted";
  if (moduleName === "作图") return "derived";
  if (moduleName === "表征") {
    if (type === "pdf" && info.first.toString("ascii").startsWith("%PDF-") && info.tail.toString("ascii").includes("%%EOF")) return "complete";
    return "unknown";
  }
  if (verifiedHtvs.has(relativePath)) return "complete";
  if (["csv", "eaf", "sh"].includes(type)) return "complete";
  return "unknown";
}

function stripMaestroValue(value) {
  const trimmed = value.trim();
  if (trimmed === "<>") return "";
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) return trimmed.slice(1, -1);
  return trimmed;
}

function extractFMCtBlocks(text) {
  const blocks = [];
  let cursor = 0;
  while (true) {
    const marker = text.indexOf("f_m_ct {", cursor);
    if (marker < 0) break;
    const brace = text.indexOf("{", marker);
    let depth = 0;
    let inQuote = false;
    let escaped = false;
    let end = -1;
    for (let i = brace; i < text.length; i += 1) {
      const char = text[i];
      if (inQuote) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === '"') inQuote = false;
        continue;
      }
      if (char === '"') inQuote = true;
      else if (char === "{") depth += 1;
      else if (char === "}") {
        depth -= 1;
        if (depth === 0) {
          end = i + 1;
          break;
        }
      }
    }
    if (end < 0) break;
    blocks.push(text.slice(marker, end));
    cursor = end;
  }
  return blocks;
}

function parseMaestroRecords(text, sourceFile) {
  const records = [];
  for (const block of extractFMCtBlocks(text)) {
    const atomStart = block.search(/\r?\n\s*m_atom\[/);
    const metadata = atomStart >= 0 ? block.slice(0, atomStart) : block;
    const delimiter = metadata.indexOf(":::");
    if (delimiter < 0) continue;
    const properties = metadata
      .slice(metadata.indexOf("{") + 1, delimiter)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    const values = metadata
      .slice(delimiter + 3)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map(stripMaestroValue);
    const row = Object.fromEntries(properties.map((property, index) => [property, values[index] ?? ""]));
    const score = Number(row.r_i_docking_score);
    if (!row.s_vsw_compound_code || !Number.isFinite(score)) continue;
    records.push({
      code: row.s_vsw_compound_code,
      title: row.s_m_title || "",
      score,
      sourceFile,
    });
  }
  return records;
}

async function readMaestro(filePath) {
  const bytes = await fsp.readFile(filePath);
  const isGzip = bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
  return (isGzip ? zlib.gunzipSync(bytes) : bytes).toString("utf8");
}

async function readCsvRows(filePath) {
  const csvText = await fsp.readFile(filePath, "utf8");
  const workbook = await Workbook.fromCSV(csvText, { sheetName: "source" });
  const sheet = workbook.worksheets.getItemAt(0);
  const used = sheet.getUsedRange(true);
  return used ? used.values : [];
}

async function readXlsxRows(filePath) {
  const blob = await FileBlob.load(filePath);
  const workbook = await SpreadsheetFile.importXlsx(blob);
  const sheet = workbook.worksheets.getItemAt(0);
  const used = sheet.getUsedRange(true);
  const values = used ? used.values : [];
  const formulas = used ? used.formulas : [];
  return { sheetName: sheet.name, values, formulas };
}

function shortHash(namespace, value) {
  return crypto.createHash("sha256").update(`${namespace}|${value}`).digest("hex").slice(0, 12).toUpperCase();
}

function joinUnique(a, b) {
  return [...new Set([...(a ? a.split(";") : []), ...(b ? b.split(";") : [])].filter(Boolean))].join(";");
}

function upsertMolecule(store, row) {
  const existing = store.get(row.canonical_id);
  if (!existing) {
    store.set(row.canonical_id, row);
    return;
  }
  for (const field of ["historical_alias", "structure_file", "source"]) existing[field] = joinUnique(existing[field], row[field]);
  if (!existing.smiles && row.smiles) existing.smiles = row.smiles;
  if (!existing.confidence && row.confidence) existing.confidence = row.confidence;
}

function numericMean(values) {
  const valid = values.map(Number).filter(Number.isFinite);
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null;
}

async function main() {
  await fsp.mkdir(dataDir, { recursive: true });

  const htvsSources = [
    path.join(workspaceRoot, "运行", "运行", "ATP-VSW", "ATP-VSW-DOCK_HTVS_1-001_lib", "ATP-VSW-DOCK_HTVS_1-001_lib"),
    path.join(workspaceRoot, "运行", "运行", "ATP-VSW", "ATP-VSW-DOCK_HTVS_1-002_lib.maegz"),
    path.join(workspaceRoot, "运行", "运行", "ATP-VSW", "ATP-VSW-DOCK_HTVS_1-003_lib", "ATP-VSW-DOCK_HTVS_1-003_lib.mae"),
  ];
  const verifiedHtvs = new Set();
  const htvsRecords = [];
  for (const source of htvsSources) {
    const text = await readMaestro(source);
    const parsed = parseMaestroRecords(text, rel(source));
    if (!parsed.length) throw new Error(`No readable HTVS records in ${source}`);
    verifiedHtvs.add(rel(source));
    htvsRecords.push(...parsed);
  }

  const sourceFiles = [];
  for (const moduleName of sourceModules) {
    const moduleRoot = path.join(workspaceRoot, moduleName);
    for (const filePath of await walkFiles(moduleRoot)) sourceFiles.push({ moduleName, filePath });
  }

  const fileInfo = new Map();
  for (const item of sourceFiles) fileInfo.set(rel(item.filePath), await fingerprint(item.filePath));
  const manifestRows = sourceFiles
    .map(({ moduleName, filePath }) => {
      const info = fileInfo.get(rel(filePath));
      return {
        文件名: path.basename(filePath),
        路径: rel(filePath),
        文件类型: fileType(filePath),
        大小: info.size,
        hash: info.sha256,
        所属模块: moduleName,
        状态: classifyFile(moduleName, filePath, info, verifiedHtvs),
      };
    })
    .sort((a, b) => a.路径.localeCompare(b.路径, "zh-CN"));

  const molecules = new Map();
  const screeningRecords = [];

  for (const record of htvsRecords) {
    const canonicalId = `ATP-HTVS-${shortHash("compound-code", record.code)}`;
    upsertMolecule(molecules, {
      canonical_id: canonicalId,
      historical_alias: joinUnique(record.code, record.title),
      structure_file: record.sourceFile,
      smiles: "",
      source: record.sourceFile,
      confidence: "source_structure_record",
    });
    screeningRecords.push({ canonical_id: canonicalId, stage: "HTVS", score: record.score, source_file: record.sourceFile });
  }

  upsertMolecule(molecules, {
    canonical_id: "ATP-REF-IN2",
    historical_alias: "IN-2",
    structure_file: "",
    smiles: "",
    source: "作图/作图/1-阳性化合物和蛋白的MD/图-3/IN-2.csv",
    confidence: "source_alias_only",
  });
  upsertMolecule(molecules, {
    canonical_id: "ATP-HIT-MD-001",
    historical_alias: "HIT;ATP-Top1-MD2",
    structure_file: "",
    smiles: "",
    source: "作图/作图/1-阳性化合物和蛋白的MD/图-3/Hit.csv;运行/运行/ATP-Top1-MD2/MD.cms",
    confidence: "source_alias_only",
  });

  const vswPath = path.join(workspaceRoot, "作图", "作图", "2-基于衍生数据库的虚拟筛选", "数据", "VSW.csv");
  const vswRows = await readCsvRows(vswPath);
  const vswSource = rel(vswPath);
  let vswSentinelRows = 0;
  for (const row of vswRows.slice(1)) {
    const score = Number(row[0]);
    const smiles = String(row[1] ?? "").trim();
    if (!smiles) {
      if (Number.isFinite(score)) vswSentinelRows += 1;
      continue;
    }
    const canonicalId = `ATP-SMI-${shortHash("source-smiles", smiles)}`;
    upsertMolecule(molecules, {
      canonical_id: canonicalId,
      historical_alias: "",
      structure_file: "",
      smiles,
      source: vswSource,
      confidence: "source_smiles_exact",
    });
    if (Number.isFinite(score)) screeningRecords.push({ canonical_id: canonicalId, stage: "MMGBSA", score, source_file: vswSource });
  }

  const mmgbsaPairs = [
    ["ATP-REF-IN2", path.join(workspaceRoot, "作图", "作图", "1-阳性化合物和蛋白的MD", "图-3", "IN-2.csv")],
    ["ATP-HIT-MD-001", path.join(workspaceRoot, "作图", "作图", "1-阳性化合物和蛋白的MD", "图-3", "Hit.csv")],
  ];
  const mmgbsaFrameCounts = {};
  for (const [canonicalId, source] of mmgbsaPairs) {
    const rows = await readCsvRows(source);
    const header = rows[0].map((value) => String(value ?? ""));
    const scoreIndex = header.indexOf("r_psp_MMGBSA_dG_Bind");
    const values = rows.slice(1).map((row) => row[scoreIndex]).filter((value) => Number.isFinite(Number(value)));
    mmgbsaFrameCounts[canonicalId] = values.length;
    const mean = numericMean(values);
    if (mean !== null) screeningRecords.push({ canonical_id: canonicalId, stage: "MMGBSA", score: mean, source_file: rel(source) });
  }

  const topPdbRoot = path.join(workspaceRoot, "作图", "作图", "2-基于衍生数据库的虚拟筛选", "数据");
  for (let index = 1; index <= 5; index += 1) {
    const source = path.join(topPdbRoot, `Top-${index}.pdb`);
    const sourceRel = rel(source);
    const info = fileInfo.get(sourceRel);
    if (!info) continue;
    upsertMolecule(molecules, {
      canonical_id: `ATP-PDB-${info.sha256.slice(0, 12).toUpperCase()}`,
      historical_alias: `Top-${index}`,
      structure_file: sourceRel,
      smiles: "",
      source: sourceRel,
      confidence: "structure_file_only",
    });
  }

  const characterizationSources = ["表征/466-H1-D2O.pdf", "表征/466-H1-DMSO.pdf", "表征/466-LCMS.pdf"];
  upsertMolecule(molecules, {
    canonical_id: "ATP-CHAR-466",
    historical_alias: "466",
    structure_file: "",
    smiles: "",
    source: characterizationSources.join(";"),
    confidence: "source_alias_only",
  });

  const admetPath = path.join(topPdbRoot, "ADMET.xlsx");
  const admet = await readXlsxRows(admetPath);
  const admetSource = rel(admetPath);
  const admetHeaders = (admet.values[0] ?? []).map((value) => String(value ?? "").trim());
  const findHeader = (tests) => admetHeaders.findIndex((header) => tests.some((test) => test.test(header)));
  const smilesIndex = findHeader([/^smiles$/i, /smiles/i]);
  const aliasIndex = findHeader([/^name$/i, /^compound/i, /^drug/i, /^title$/i, /^molecule/i]);
  let sumIndex = findHeader([/^sum$/i, /total/i]);
  if (sumIndex < 0 && admet.formulas.length > 1) {
    sumIndex = (admet.formulas[1] ?? []).findIndex((formula) => /^=SUM\(/i.test(String(formula ?? "")));
  }
  let admetRecordCount = 0;
  for (const row of admet.values.slice(1)) {
    if (!row.some((value) => value !== null && value !== undefined && String(value).trim() !== "")) continue;
    const smiles = smilesIndex >= 0 ? String(row[smilesIndex] ?? "").trim() : "";
    const alias = aliasIndex >= 0 ? String(row[aliasIndex] ?? "").trim() : "";
    let canonicalId = "";
    if (alias.toUpperCase() === "IN-2") canonicalId = "ATP-REF-IN2";
    else if (smiles) canonicalId = `ATP-SMI-${shortHash("source-smiles", smiles)}`;
    if (canonicalId) {
      upsertMolecule(molecules, {
        canonical_id: canonicalId,
        historical_alias: alias,
        structure_file: "",
        smiles,
        source: admetSource,
        confidence: smiles ? "source_smiles_exact" : "source_alias_only",
      });
    }
    let score = sumIndex >= 0 && Number.isFinite(Number(row[sumIndex])) ? Number(row[sumIndex]) : "";
    if (score === "" && sumIndex > 1) {
      const endpointValues = row.slice(1, sumIndex).map(Number).filter(Number.isFinite);
      if (endpointValues.length === sumIndex - 1) score = endpointValues.reduce((sum, value) => sum + value, 0);
    }
    screeningRecords.push({ canonical_id: canonicalId, stage: "ADMET", score, source_file: admetSource });
    admetRecordCount += 1;
  }

  const systemsRows = [
    {
      system_id: "SYS-MD-IN2-001",
      ligand_id: "ATP-REF-IN2",
      protein: "7P3W",
      trajectory_status: "incomplete",
      source: "运行/运行/ATP-Ref-MD1/MD.xtc.baiduyun.p.downloading;运行/运行/ATP-Ref-MD1/MD.cms;作图/作图/1-阳性化合物和蛋白的MD/图-1/ATP-Ref-MD1.pdf",
    },
    {
      system_id: "SYS-MD-HIT-001",
      ligand_id: "ATP-HIT-MD-001",
      protein: "7P3W",
      trajectory_status: "incomplete",
      source: "运行/运行/ATP-Top1-MD2/MD.xtc.baiduyun.p.downloading;运行/运行/ATP-Top1-MD2/MD.cms;作图/作图/3-新型苗头有化合物和蛋白复合物的MD/图-1/ATP-Top1-MD2.pdf",
    },
  ];

  const moleculeRows = [...molecules.values()].sort((a, b) => a.canonical_id.localeCompare(b.canonical_id));
  screeningRecords.sort((a, b) => a.stage.localeCompare(b.stage) || a.canonical_id.localeCompare(b.canonical_id) || a.score - b.score);

  const allowedStatuses = new Set(["complete", "incomplete", "corrupted", "derived", "unknown"]);
  const allowedStages = new Set(["HTVS", "Docking", "MMGBSA", "ADMET"]);
  if (new Set(manifestRows.map((row) => row.路径)).size !== manifestRows.length) throw new Error("Duplicate path in raw_manifest.csv");
  if (manifestRows.some((row) => !allowedStatuses.has(row.状态) || !/^[0-9a-f]{64}$/.test(row.hash))) throw new Error("Invalid manifest status or SHA-256");
  if (new Set(moleculeRows.map((row) => row.canonical_id)).size !== moleculeRows.length) throw new Error("Duplicate canonical_id in molecules.csv");
  const moleculeIds = new Set(moleculeRows.map((row) => row.canonical_id));
  if (screeningRecords.some((row) => !allowedStages.has(row.stage) || (row.canonical_id && !moleculeIds.has(row.canonical_id)))) throw new Error("Invalid screening stage or molecule foreign key");
  if (systemsRows.some((row) => row.ligand_id && !moleculeIds.has(row.ligand_id))) throw new Error("Invalid systems ligand foreign key");

  await writeValidatedCsv(path.join(dataDir, "raw_manifest.csv"), ["文件名", "路径", "文件类型", "大小", "hash", "所属模块", "状态"], manifestRows);
  await writeValidatedCsv(path.join(dataDir, "molecules.csv"), ["canonical_id", "historical_alias", "structure_file", "smiles", "source", "confidence"], moleculeRows);
  await writeValidatedCsv(path.join(dataDir, "screening_records.csv"), ["canonical_id", "stage", "score", "source_file"], screeningRecords);
  await writeValidatedCsv(path.join(dataDir, "systems.csv"), ["system_id", "ligand_id", "protein", "trajectory_status", "source"], systemsRows);

  const statusCounts = Object.fromEntries(["complete", "incomplete", "corrupted", "derived", "unknown"].map((status) => [status, manifestRows.filter((row) => row.状态 === status).length]));
  const stageCounts = Object.fromEntries(["HTVS", "Docking", "MMGBSA", "ADMET"].map((stage) => [stage, screeningRecords.filter((row) => row.stage === stage).length]));
  const uniqueHtvs = new Set(htvsRecords.map((row) => row.code)).size;

  const dictionary = `# ATP-Navigator Dataset v0.1 数据字典

## 通用规则

- 原始输入仅来自工作区的 \`表征/\`、\`运行/\`、\`作图/\`，构建过程不写入这些目录。
- 路径均为相对工作区根目录的 POSIX 风格路径，便于迁移。
- 空字符串表示当前来源无法确认；不得据文件名或展示顺序推断。
- \`canonical_id\` 是 v0.1 内部稳定记录键，不等同于 InChIKey，也不声明 SMILES 已进行化学规范化。
- 多个来源或历史别名使用英文分号 \`;\` 分隔。

## data/raw_manifest.csv

| 字段 | 含义 |
|---|---|
| 文件名 | 原始文件的基本文件名。 |
| 路径 | 相对工作区根目录的原始文件路径。 |
| 文件类型 | 扩展名（不含点）；百度云下载残片记为 \`download-fragment\`，无扩展名记为 \`no-extension\`。 |
| 大小 | 文件字节数，整数。 |
| hash | 原始文件内容的 SHA-256 十六进制摘要。 |
| 所属模块 | \`表征\`、\`运行\` 或 \`作图\`。 |
| 状态 | \`complete\`：完成了当前文件级读取/格式验证；\`incomplete\`：下载残片、空文件或全零占位；\`corrupted\`：预期文本型文件存在显著异常空字节；\`derived\`：分析、绘图或展示产物；\`unknown\`：仅凭当前扫描无法确认语义完整性。状态不代表整个科研 workflow 是否完整。 |

## data/molecules.csv

| 字段 | 含义 |
|---|---|
| canonical_id | v0.1 项目内部记录键。\`ATP-HTVS-*\` 由来源 compound code 生成；\`ATP-SMI-*\` 由来源 SMILES 原文生成；其他为明确来源实体键。 |
| historical_alias | 来源中直接出现的历史名称或编号；未确认留空。 |
| structure_file | 含该条目结构记录的来源文件；不能确认结构对应关系时留空。 |
| smiles | 来源直接提供的 SMILES；未做结构推断或规范化，缺失留空。 |
| source | 支持该记录的来源文件。 |
| confidence | v0.1 证据类型：\`source_structure_record\`、\`source_smiles_exact\`、\`structure_file_only\` 或 \`source_alias_only\`。它描述来源确定性，不代表生物活性可信度。 |

## data/screening_records.csv

| 字段 | 含义 |
|---|---|
| canonical_id | 对应 \`molecules.csv\` 的记录键；ADMET 来源无法映射时留空。 |
| stage | \`HTVS\`、\`Docking\`、\`MMGBSA\` 或 \`ADMET\`。v0.1 没有可独立确认的结构化 Docking（非 HTVS）记录，因此该阶段当前为 0 行。 |
| score | 来源数值。HTVS 为 \`r_i_docking_score\`；VSW 为来源列 \`MMGBSA dG Bind\`；两套 MD 为 1000 帧 \`r_psp_MMGBSA_dG_Bind\` 的算术均值；ADMET 为源工作簿末列 \`SUM(B:AB)\` 公式所定义的 27 个二元端点之和（该末列表头在源文件中为空）。空值表示来源行没有可放入本窄表的单一聚合分数。 |
| source_file | 产生该记录的直接来源文件。 |

## data/systems.csv

| 字段 | 含义 |
|---|---|
| system_id | v0.1 MD 体系键。 |
| ligand_id | 对应 \`molecules.csv\` 的配体记录键；不据推断把 HIT 映射到 Top-1/Top-3/466。 |
| protein | 当前来源中明确的蛋白结构标识，本批数据为 \`7P3W\`。 |
| trajectory_status | 原始轨迹状态；当前两套 XTC 均为 \`incomplete\` 下载残片。 |
| source | 体系的原始/衍生来源路径。 |
`;

  const corruptedRows = manifestRows.filter((row) => row.状态 === "corrupted").map((row) => `- \`${row.路径}\``).join("\n") || "- 无";
  const incompleteRows = manifestRows.filter((row) => row.状态 === "incomplete").map((row) => `- \`${row.路径}\``).join("\n") || "- 无";
  const audit = `# DATA_AUDIT_REPORT — ATP-Navigator Dataset v0.1

生成日期：2026-08-22  
扫描范围：\`表征/\`、\`运行/\`、\`作图/\`（只读）  
本阶段未训练模型。

## 当前数据资产

- 原始文件：${manifestRows.length} 个；总大小 ${manifestRows.reduce((sum, row) => sum + Number(row.大小), 0)} 字节。
- 文件状态：complete ${statusCounts.complete}，incomplete ${statusCounts.incomplete}，corrupted ${statusCounts.corrupted}，derived ${statusCounts.derived}，unknown ${statusCounts.unknown}。
- 可解析 HTVS：${htvsRecords.length} 条构象/变体记录，${uniqueHtvs} 个来源 compound code；来自 001、002、003 三个可读分片。
- VSW 候选表：${vswRows.length - 1} 个数据行，其中 ${vswSentinelRows} 个空 SMILES 占位行未作为分子记录，${vswRows.length - 1 - vswSentinelRows} 个含 SMILES 和 MM/GBSA 分数的候选记录。
- MD/MMGBSA：IN-2 ${mmgbsaFrameCounts["ATP-REF-IN2"] ?? 0} 帧，HIT ${mmgbsaFrameCounts["ATP-HIT-MD-001"] ?? 0} 帧；v0.1 仅写入各体系均值，不把帧当成独立分子样本。
- ADMET：工作表 \`${admet.sheetName}\`，${admetRecordCount} 条化合物行；v0.1 按源工作簿末列公式 \`SUM(B:AB)\` 保存 27 个二元端点的聚合值（源末列表头为空），原始端点仍保留在源工作簿中。
- 化学表征：编号 466 的 1H NMR（D2O、DMSO）和 LC-MS PDF，共 3 个文件；尚未与 HIT/Top 候选建立可审计的一一映射。
- 结构/展示资产：Top-1 至 Top-5 PDB、MD 报告、分析表、图像和视频；在 manifest 中作为 derived 管理。
- 结构化输出：molecules ${moleculeRows.length} 行；screening_records ${screeningRecords.length} 行（HTVS ${stageCounts.HTVS}、Docking ${stageCounts.Docking}、MMGBSA ${stageCounts.MMGBSA}、ADMET ${stageCounts.ADMET}）；systems ${systemsRows.length} 行。

## 当前可用于训练或建模的数据

- HTVS 的 ${htvsRecords.length} 条记录可用于建立“复现/近似 Docking 分数”的 baseline，划分时必须按 compound code 分组，避免同一分子的不同质子化/构象变体跨训练集和测试集。
- HTVS 标签是计算评分，不是实验活性；它只能支持评分函数代理、排序一致性和数据流程验证，不能据此声称建立了抗菌活性预测模型。
- ${vswRows.length - 1 - vswSentinelRows} 个含 SMILES 的 VSW/MMGBSA 候选可用于小样本排序分析或外部预训练表征的初步评估，但不足以独立训练复杂模型。
- 两个 MD 体系和逐帧 MM/GBSA 可用于体系内时序/稳定性分析；仅有两个配体，不能作为分子级监督学习训练集。
- ${admetRecordCount} 条 ADMET 预测记录可作为候选描述特征或规则筛选输入，样本量不足，且预测端点不是实验真值。

## 当前不能直接使用的数据

### incomplete

${incompleteRows}

### corrupted

${corruptedRows}

- 图片、SVG、PDF 报告、视频和 CXS/AI 展示文件是衍生资产，不是独立监督标签。
- HTVS 的重复压缩/解压副本不能重复计数为新样本。
- IN-2/HIT 的 1000 帧高度相关，不能按 2000 个独立分子样本训练。
- HIT、ATP-Top1-MD2、Top-1/Top-3、466 之间缺少可核验映射，v0.1 不跨文件名强行合并。

## 下一步缺失数据

1. 从原始库到 HTVS/SP/XP/MMGBSA 的完整 compound-level workflow 表，以及每一步淘汰/保留关系。
2. 稳定的化合物主键映射：HTVS compound code、VSW SMILES、Top-1~5 PDB、HIT MD 配体、466 表征样品之间的一一对应表。
3. 可复现参数：Schrödinger 版本、网格/蛋白准备、质子化、打分、MM/GBSA 与 ADMET 运行配置。
4. 完整可读取的两套原始 MD 轨迹；当前 XTC 均为下载残片。
5. 实验活性标签（明确检测方法、浓度/单位、重复数、阳性/阴性和失败样本）。没有这些数据，不能训练或验证真实活性优先级模型。
6. 更多具备同一评价流程的负样本与中间分数，避免只保留 Top hits 造成选择偏差。

## v0.1 边界

- 本数据层建立文件级溯源、内部主键和窄表接口。
- 不修复原始文件，不补写缺失字段，不把未来计划写成已有数据。
- 不训练模型；待主键映射和实验标签补齐后再进入 baseline 阶段。
`;

  await fsp.writeFile(path.join(projectRoot, "docs", "data_dictionary.md"), dictionary, "utf8");
  await fsp.writeFile(path.join(projectRoot, "DATA_AUDIT_REPORT.md"), audit, "utf8");

  console.log(JSON.stringify({
    manifest: manifestRows.length,
    statusCounts,
    molecules: moleculeRows.length,
    screeningRecords: screeningRecords.length,
    stageCounts,
    systems: systemsRows.length,
    htvsRecords: htvsRecords.length,
    uniqueHtvs,
    admetHeaders,
    admetRecordCount,
  }, null, 2));
}

await main();
