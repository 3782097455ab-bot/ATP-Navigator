/**
 * Build additive Phase 2 tabular assets without modifying Dataset v0.1.
 *
 * Outputs:
 *   data/docking_features_v0_2.csv
 *   data/admet_features_v0_2.csv
 *   data/compound_mapping_v1.csv
 *   results/phase2_asset_summary.json
 */

import crypto from "node:crypto";
import fsp from "node:fs/promises";
import path from "node:path";
import zlib from "node:zlib";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const workspaceRoot = path.resolve(projectRoot, "..");
const dataDir = path.join(projectRoot, "data");
const resultsDir = path.join(projectRoot, "results");

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
  if (!used || used.rowCount !== rows.length + 1 || used.columnCount !== headers.length) {
    throw new Error(`CSV validation failed: ${filePath}`);
  }
  await workbook.inspect({
    kind: "region",
    sheetId: sheet.name,
    range: used.address,
    maxChars: 1200,
    tableMaxRows: 4,
    tableMaxCols: Math.min(headers.length, 20),
  });
  await fsp.writeFile(filePath, csvText, "utf8");
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

function parseMaestroMetadata(text) {
  const rows = [];
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
    rows.push(Object.fromEntries(properties.map((property, index) => [property, values[index] ?? ""])));
  }
  return rows;
}

async function readMaestro(filePath) {
  const bytes = await fsp.readFile(filePath);
  const isGzip = bytes.length >= 2 && bytes[0] === 0x1f && bytes[1] === 0x8b;
  return (isGzip ? zlib.gunzipSync(bytes) : bytes).toString("utf8");
}

async function readCsvObjects(filePath) {
  const csvText = await fsp.readFile(filePath, "utf8");
  const workbook = await Workbook.fromCSV(csvText, { sheetName: "source" });
  const sheet = workbook.worksheets.getItemAt(0);
  const values = sheet.getUsedRange(true)?.values ?? [];
  if (!values.length) return [];
  const headers = values[0].map((value) => String(value ?? ""));
  return values.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])));
}

async function readCsvRows(filePath) {
  const csvText = await fsp.readFile(filePath, "utf8");
  const workbook = await Workbook.fromCSV(csvText, { sheetName: "source" });
  const sheet = workbook.worksheets.getItemAt(0);
  return sheet.getUsedRange(true)?.values ?? [];
}

function shortHash(namespace, value) {
  return crypto.createHash("sha256").update(`${namespace}|${value}`).digest("hex").slice(0, 12).toUpperCase();
}

function numericOrBlank(value) {
  if (value === "" || value === null || value === undefined) return "";
  const number = Number(value);
  return Number.isFinite(number) ? number : "";
}

function slug(value) {
  const output = String(value ?? "")
    .trim()
    .toLowerCase()
    .replaceAll("+", "_plus_")
    .replaceAll("-", "_minus_")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return output || "unnamed";
}

function quickPropColumn(property) {
  return `quickprop_${slug(property.replace(/^[ris]_qp_/, ""))}`;
}

function decodeMaestroBracketSmiles(value) {
  // Maestro text exports encode bracket atoms such as [NH2+] as /NH2+/.
  return String(value ?? "").replace(/\/([A-Za-z0-9@+\-]+)\//g, "[$1]");
}

async function buildDockingFeatures(moleculeRows) {
  const codeToCanonical = new Map();
  for (const row of moleculeRows) {
    if (!String(row.canonical_id).startsWith("ATP-HTVS-")) continue;
    for (const alias of String(row.historical_alias ?? "").split(";")) {
      if (alias) codeToCanonical.set(alias, row.canonical_id);
    }
  }

  const sources = [
    path.join(workspaceRoot, "运行", "运行", "ATP-VSW", "ATP-VSW-DOCK_HTVS_1-001_lib", "ATP-VSW-DOCK_HTVS_1-001_lib"),
    path.join(workspaceRoot, "运行", "运行", "ATP-VSW", "ATP-VSW-DOCK_HTVS_1-002_lib.maegz"),
    path.join(workspaceRoot, "运行", "运行", "ATP-VSW", "ATP-VSW-DOCK_HTVS_1-003_lib", "ATP-VSW-DOCK_HTVS_1-003_lib.mae"),
  ];
  const propertyMap = {
    r_i_docking_score: "glide_docking_score",
    r_i_glide_gscore: "glide_gscore",
    r_i_glide_emodel: "glide_emodel",
    r_i_glide_energy: "glide_energy",
    r_i_glide_evdw: "glide_evdw",
    r_i_glide_ecoul: "glide_ecoul",
    r_i_glide_einternal: "glide_einternal",
    r_i_glide_eff_state_penalty: "glide_eff_state_penalty",
    r_i_glide_ligand_efficiency: "glide_ligand_efficiency",
    r_i_glide_ligand_efficiency_sa: "glide_ligand_efficiency_sa",
    r_i_glide_ligand_efficiency_ln: "glide_ligand_efficiency_ln",
  };
  const records = [];
  const quickPropColumns = new Set();
  for (const source of sources) {
    const parsed = parseMaestroMetadata(await readMaestro(source));
    for (let recordIndex = 0; recordIndex < parsed.length; recordIndex += 1) {
      const row = parsed[recordIndex];
      const code = String(row.s_vsw_compound_code ?? "");
      if (!code || !Number.isFinite(Number(row.r_i_docking_score))) continue;
      const output = {
        canonical_id: codeToCanonical.get(code) ?? `ATP-HTVS-${shortHash("compound-code", code)}`,
        compound_code: code,
        title: row.s_m_title ?? "",
        variant: row.s_vsw_variant ?? "",
        pose_index: recordIndex + 1,
      };
      for (const [property, column] of Object.entries(propertyMap)) output[column] = numericOrBlank(row[property]);
      for (const [property, value] of Object.entries(row)) {
        if (!/^[ris]_qp_/.test(property)) continue;
        const column = quickPropColumn(property);
        output[column] = numericOrBlank(value);
        quickPropColumns.add(column);
      }
      output.source_file = rel(source);
      records.push(output);
    }
  }
  const fixedHeaders = [
    "canonical_id", "compound_code", "title", "variant", "pose_index",
    "glide_docking_score", "glide_gscore", "glide_emodel", "glide_energy",
    "glide_evdw", "glide_ecoul", "glide_einternal", "glide_eff_state_penalty",
    "glide_ligand_efficiency", "glide_ligand_efficiency_sa", "glide_ligand_efficiency_ln",
  ];
  const headers = [...fixedHeaders, ...[...quickPropColumns].sort(), "source_file"];
  records.sort((a, b) => String(a.canonical_id).localeCompare(String(b.canonical_id)) || Number(a.glide_docking_score) - Number(b.glide_docking_score));
  return { headers, records, quickPropColumns: [...quickPropColumns].sort() };
}

async function buildAdmetFeatures() {
  const source = path.join(workspaceRoot, "作图", "作图", "2-基于衍生数据库的虚拟筛选", "数据", "ADMET.xlsx");
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(source));
  const sheet = workbook.worksheets.getItemAt(0);
  const used = sheet.getUsedRange(true);
  const values = used?.values ?? [];
  const formulas = used?.formulas ?? [];
  if (values.length < 2) throw new Error("ADMET.xlsx has no data rows");
  const rawHeaders = values[0].map((value) => String(value ?? "").trim());
  const smilesIndex = rawHeaders.findIndex((header) => /smiles/i.test(header));
  let sumIndex = rawHeaders.findIndex((header) => /^(sum|total)$/i.test(header));
  if (sumIndex < 0) sumIndex = (formulas[1] ?? []).findIndex((formula) => /^=SUM\(/i.test(String(formula ?? "")));
  if (smilesIndex < 0 || sumIndex < 0) throw new Error("ADMET SMILES or endpoint-sum column not identified");
  const endpointIndices = [];
  for (let index = 0; index < sumIndex; index += 1) {
    if (index !== smilesIndex) endpointIndices.push(index);
  }
  const endpointColumns = endpointIndices.map((index) => `admet_${slug(rawHeaders[index])}`);
  const records = [];
  for (const row of values.slice(1)) {
    const smiles = String(row[smilesIndex] ?? "").trim();
    if (!smiles) continue;
    const output = {
      canonical_id: `ATP-SMI-${shortHash("source-smiles", smiles)}`,
      smiles,
    };
    endpointIndices.forEach((index, position) => {
      output[endpointColumns[position]] = numericOrBlank(row[index]);
    });
    const numericEndpoints = endpointIndices.map((index) => Number(row[index])).filter(Number.isFinite);
    const sourceSum = numericOrBlank(row[sumIndex]);
    output.admet_endpoint_sum = sourceSum === "" ? numericEndpoints.reduce((sum, value) => sum + value, 0) : sourceSum;
    output.source_file = rel(source);
    records.push(output);
  }
  return {
    headers: ["canonical_id", "smiles", ...endpointColumns, "admet_endpoint_sum", "source_file"],
    records,
    endpointColumns,
    rawHeaders,
    sheetName: sheet.name,
  };
}

async function buildMapping(moleculeRows, dockingRecords) {
  const mappings = [];
  const add = (canonical_id, original_name, source, confidence) => mappings.push({ canonical_id, original_name, source, confidence });

  const htvsCodes = new Map();
  for (const row of dockingRecords) {
    if (!htvsCodes.has(row.compound_code)) htvsCodes.set(row.compound_code, { canonical: row.canonical_id, source: row.source_file });
  }

  const vswSource = path.join(workspaceRoot, "作图", "作图", "2-基于衍生数据库的虚拟筛选", "数据", "VSW.csv");
  const vswRows = await readCsvRows(vswSource);
  const candidateBySmiles = new Map();
  let hitIndex = 0;
  for (const row of vswRows.slice(1)) {
    const smiles = String(row[1] ?? "").trim();
    if (!smiles) continue;
    hitIndex += 1;
    const canonical = `ATP-SMI-${shortHash("source-smiles", smiles)}`;
    candidateBySmiles.set(smiles, { canonical, hit: `Hit${hitIndex}` });
    add(canonical, smiles, rel(vswSource), "confirmed");
  }

  const vswMaegzSource = path.join(workspaceRoot, "作图", "作图", "2-基于衍生数据库的虚拟筛选", "数据", "VSW.maegz");
  const vswMetadata = parseMaestroMetadata(await readMaestro(vswMaegzSource));
  const vswCodes = new Map();
  for (const row of vswMetadata) {
    const smiles = decodeMaestroBracketSmiles(row.s_user_SMILES);
    const candidate = candidateBySmiles.get(smiles);
    const code = String(row.s_vsw_compound_code ?? "");
    if (!candidate || !code) continue;
    const evidence = rel(vswMaegzSource);
    vswCodes.set(code, { canonical: candidate.canonical, hit: candidate.hit, source: evidence });
    add(candidate.canonical, code, evidence, "confirmed");
    add(candidate.canonical, String(row.s_vsw_variant ?? ""), evidence, "confirmed");
    add(candidate.canonical, String(row.s_m_title ?? ""), evidence, "confirmed");
    add(candidate.canonical, String(row.s_lp_Variant ?? ""), evidence, "confirmed");
    add(candidate.canonical, candidate.hit, `${rel(vswSource)};${evidence}`, "confirmed");
  }

  for (const [code, item] of [...htvsCodes.entries()].sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }))) {
    const vsw = vswCodes.get(code);
    if (vsw) {
      add(vsw.canonical, code, `${item.source};${vsw.source}`, "confirmed");
      add(vsw.canonical, item.canonical, item.source, "confirmed");
    } else {
      add(item.canonical, code, item.source, "confirmed");
    }
  }

  const mdSource = path.join(workspaceRoot, "运行", "运行", "ATP-Top1-MD2", "MD.cms");
  const mdRows = parseMaestroMetadata(await readMaestro(mdSource));
  const ligandRow = mdRows.find((row) => row.s_user_SMILES && row.s_vsw_compound_code);
  if (!ligandRow) throw new Error("Could not locate ATP-Top1 ligand metadata in MD.cms");
  const decodedMdSmiles = decodeMaestroBracketSmiles(ligandRow.s_user_SMILES);
  const mdCanonical = `ATP-SMI-${shortHash("source-smiles", decodedMdSmiles)}`;
  if (!moleculeRows.some((row) => row.canonical_id === mdCanonical)) {
    throw new Error(`MD ligand SMILES is absent from molecules.csv: ${JSON.stringify({ mdCanonical, smiles: decodedMdSmiles, code: ligandRow.s_vsw_compound_code })}`);
  }
  add(mdCanonical, String(ligandRow.s_vsw_compound_code), rel(mdSource), "confirmed");
  add(mdCanonical, String(ligandRow.s_vsw_variant ?? ""), rel(mdSource), "confirmed");
  add(mdCanonical, "ATP-Top1", rel(mdSource), "confirmed");
  add(mdCanonical, "ATP-Top1-MD2", rel(mdSource), "confirmed");
  add(mdCanonical, "HIT", `ATP酶抑制剂的修饰改造.pptx;作图/作图/1-阳性化合物和蛋白的MD/图-3/Hit.csv;${rel(mdSource)}`, "confirmed");
  add(mdCanonical, "ATP-HIT-MD-001", `ATP-Navigator/data/systems.csv;作图/作图/1-阳性化合物和蛋白的MD/图-3/Hit.csv;${rel(mdSource)}`, "confirmed");

  // RDKit graph comparison performed during the Phase 2 audit: Top-3.pdb and
  // the MD.cms ligand have the same stereochemical InChIKey.
  add(mdCanonical, "Top-3", "作图/作图/2-基于衍生数据库的虚拟筛选/数据/Top-3.pdb;运行/运行/ATP-Top1-MD2/MD.cms", "confirmed");
  add(mdCanonical, "Hit3", "ATP酶抑制剂的修饰改造.pptx;作图/作图/2-基于衍生数据库的虚拟筛选/数据/VSW.csv;作图/作图/2-基于衍生数据库的虚拟筛选/数据/VSW.maegz", "confirmed");
  add(mdCanonical, "ATP-PDB-E630DDE8CA00", "ATP-Navigator/data/molecules.csv;作图/作图/2-基于衍生数据库的虚拟筛选/数据/Top-3.pdb", "confirmed");

  // Characterization strongly matches the neutral parent structure, but no
  // explicit sample-number crosswalk states that 466 equals Hit3/27063.
  const characterization = "表征/466-H1-D2O.pdf;表征/466-H1-DMSO.pdf;表征/466-LCMS.pdf";
  add(mdCanonical, "466", characterization, "probable");
  add(mdCanonical, "ATP-CHAR-466", `ATP-Navigator/data/molecules.csv;${characterization}`, "probable");

  const in2Canonical = "ATP-SMI-1EDF03AEDEF9";
  if (moleculeRows.some((row) => row.canonical_id === in2Canonical)) {
    add(in2Canonical, "IN-2", "作图/作图/2-基于衍生数据库的虚拟筛选/数据/ADMET.xlsx;运行/运行/ATP-Ref-MD1/MD.cms", "confirmed");
    add(in2Canonical, "ATP-REF-IN2", "ATP-Navigator/data/molecules.csv;ATP-Navigator/data/systems.csv;运行/运行/ATP-Ref-MD1/MD.cms", "confirmed");
  }

  const deduplicated = new Map();
  const confidenceRank = { unknown: 0, probable: 1, confirmed: 2 };
  for (const row of mappings) {
    if (!row.original_name) continue;
    const key = `${row.canonical_id}\u0000${row.original_name}`;
    const existing = deduplicated.get(key);
    if (!existing) {
      deduplicated.set(key, { ...row });
      continue;
    }
    existing.source = [...new Set(`${existing.source};${row.source}`.split(";").filter(Boolean))].join(";");
    if (confidenceRank[row.confidence] > confidenceRank[existing.confidence]) existing.confidence = row.confidence;
  }
  return [...deduplicated.values()].sort((a, b) => a.canonical_id.localeCompare(b.canonical_id) || a.original_name.localeCompare(b.original_name));
}

async function main() {
  await fsp.mkdir(dataDir, { recursive: true });
  await fsp.mkdir(resultsDir, { recursive: true });
  const molecules = await readCsvObjects(path.join(dataDir, "molecules.csv"));
  const docking = await buildDockingFeatures(molecules);
  const admet = await buildAdmetFeatures();
  const mapping = await buildMapping(molecules, docking.records);

  await writeValidatedCsv(path.join(dataDir, "docking_features_v0_2.csv"), docking.headers, docking.records);
  await writeValidatedCsv(path.join(dataDir, "admet_features_v0_2.csv"), admet.headers, admet.records);
  await writeValidatedCsv(
    path.join(dataDir, "compound_mapping_v1.csv"),
    ["canonical_id", "original_name", "source", "confidence"],
    mapping,
  );

  const summary = {
    generated_at: new Date().toISOString(),
    additive_only: true,
    docking_records: docking.records.length,
    docking_compounds: new Set(docking.records.map((row) => row.canonical_id)).size,
    docking_quickprop_fields: docking.quickPropColumns,
    admet_records: admet.records.length,
    admet_endpoint_fields: admet.endpointColumns,
    admet_source_headers: admet.rawHeaders,
    mapping_rows: mapping.length,
    mapping_confidence_counts: Object.fromEntries(["confirmed", "probable", "unknown"].map((level) => [level, mapping.filter((row) => row.confidence === level).length])),
    mapping_notes: {
      hit3: "Confirmed from the project PPT, VSW candidate score/SMILES and Top-3 structure identity.",
      characterization_466: "Formula, exact mass, stereochemistry and LC-MS support the same neutral parent, but no explicit sample crosswalk exists; kept probable.",
      top3: "Confirmed by stereochemical InChIKey equality between Top-3.pdb and the MD.cms ligand.",
      htvs_to_mmgbsa: "VSW.maegz recovers all 17 candidate codes. Only code 91074 is present in the three readable HTVS shards, yielding one confirmed HTVS-to-MMGBSA bridge.",
    },
  };
  await fsp.writeFile(path.join(resultsDir, "phase2_asset_summary.json"), JSON.stringify(summary, null, 2), "utf8");
  console.log(JSON.stringify(summary, null, 2));
}

await main();
