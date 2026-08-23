/**
 * Build the additive ATP-Navigator Dataset v1.0 three-layer registry.
 *
 * The source public CSV is never modified. Exact duplicate rows and compound
 * IDs that map to multiple source-declared canonical SMILES are excluded from
 * the processed output and recorded in dataset_metadata.json.
 */

import crypto from "node:crypto";
import fsp from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const publicCsv = path.resolve(process.argv[2] || "");
if (!process.argv[2]) throw new Error("Usage: node build_dataset_v1.mjs <public-source.csv>");

const outputDir = path.join(projectRoot, "data", "dataset_v1.0");
const outputCsv = path.join(outputDir, "ATP_Navigator_Dataset_v1.csv");
const metadataPath = path.join(outputDir, "dataset_metadata.json");

const outputHeaders = [
  "compound_id",
  "canonical_smiles",
  "target",
  "protein_id",
  "organism",
  "activity_type",
  "activity_value",
  "unit",
  "dataset_layer",
  "data_source",
  "reference",
  "label_confidence",
];

const publicRequired = [
  "compound_id",
  "compound_name",
  "smiles",
  "target",
  "protein_id",
  "organism",
  "activity_type",
  "activity_value",
  "unit",
  "docking_score",
  "mmgbsa",
  "admet",
  "source_database",
  "paper_title",
  "DOI",
  "year",
  "data_type",
  "assay_note",
];

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function toCsv(headers, rows) {
  return [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))]
    .map((row) => row.map(csvCell).join(","))
    .join("\r\n") + "\r\n";
}

async function readCsv(filePath, sheetName) {
  const text = await fsp.readFile(filePath, "utf8");
  const workbook = await Workbook.fromCSV(text, { sheetName });
  const sheet = workbook.worksheets.getItemAt(0);
  const values = sheet.getUsedRange(true)?.values ?? [];
  if (!values.length) return { headers: [], rows: [] };
  const headers = values[0].map((value) => String(value ?? "").trim());
  const rows = values.slice(1).map((valuesRow) =>
    Object.fromEntries(headers.map((header, index) => [header, String(valuesRow[index] ?? "").trim()])),
  );
  return { headers, rows };
}

function sha256Text(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}

async function sha256File(filePath) {
  return sha256Text(await fsp.readFile(filePath));
}

function publicLayer(row) {
  const isChembl = row.source_database === "ChEMBL";
  const isAtpTarget = row.target.toLowerCase().includes("atp synthase");
  return isChembl && !isAtpTarget
    ? "layer_1_general_antibacterial"
    : "layer_2_atp_synthase_specific";
}

function publicConfidence(row) {
  if (!row.activity_value || !row.activity_type || !row.unit) return "low_annotation_or_incomplete";
  if (!row.source_database || !row.DOI) return "low_provenance_incomplete";
  return "medium_source_traceable_unverified";
}

function normalizedUnit(unit) {
  if (unit === "μg/mL" || unit === "µg/mL") return "ug/mL";
  return unit;
}

function publicReference(row) {
  return [
    `DOI=${row.DOI}`,
    `year=${row.year}`,
    `title=${row.paper_title}`,
    `assay_note=${row.assay_note}`,
  ].join(" | ");
}

function publicSignature(row) {
  return publicRequired.map((field) => row[field] ?? "").join("\u001f");
}

function makeInternalRow({
  compoundId,
  smiles,
  activityType,
  activityValue,
  dataSource,
  reference,
  confidence,
}) {
  return {
    compound_id: compoundId,
    canonical_smiles: smiles,
    target: "F1F0-ATP synthase (Fo a/c interface)",
    protein_id: "7P3W",
    organism: "Acinetobacter baumannii",
    activity_type: activityType,
    activity_value: activityValue,
    unit: "",
    dataset_layer: "layer_3_internal_atp_navigator",
    data_source: dataSource,
    reference,
    label_confidence: confidence,
  };
}

const publicTable = await readCsv(publicCsv, "public_source");
const missingPublicHeaders = publicRequired.filter((header) => !publicTable.headers.includes(header));
if (missingPublicHeaders.length) throw new Error(`Public CSV missing fields: ${missingPublicHeaders.join(", ")}`);

const compoundToSmiles = new Map();
for (const row of publicTable.rows) {
  if (!compoundToSmiles.has(row.compound_id)) compoundToSmiles.set(row.compound_id, new Set());
  compoundToSmiles.get(row.compound_id).add(row.smiles);
}
const conflictingIds = new Set(
  [...compoundToSmiles.entries()].filter(([, structures]) => structures.size > 1).map(([compoundId]) => compoundId),
);

const seenPublicSignatures = new Set();
const publicRows = [];
let duplicateRowsExcluded = 0;
let identityConflictRowsExcluded = 0;
for (const row of publicTable.rows) {
  const signature = publicSignature(row);
  if (seenPublicSignatures.has(signature)) {
    duplicateRowsExcluded += 1;
    continue;
  }
  seenPublicSignatures.add(signature);
  if (conflictingIds.has(row.compound_id)) {
    identityConflictRowsExcluded += 1;
    continue;
  }
  publicRows.push({
    compound_id: row.compound_id,
    canonical_smiles: row.smiles,
    target: row.target,
    protein_id: row.protein_id,
    organism: row.organism,
    activity_type: row.activity_type,
    activity_value: row.activity_value,
    unit: normalizedUnit(row.unit),
    dataset_layer: publicLayer(row),
    data_source: row.source_database,
    reference: publicReference(row),
    label_confidence: publicConfidence(row),
  });
}

const samplesTable = await readCsv(path.join(projectRoot, "data", "dataset_v0.2", "samples.csv"), "samples");
const screeningTable = await readCsv(path.join(projectRoot, "data", "screening_records.csv"), "screening");
const moleculesTable = await readCsv(path.join(projectRoot, "data", "molecules.csv"), "molecules");
const mappingTable = await readCsv(path.join(projectRoot, "data", "compound_mapping_v1.csv"), "mapping");

const sampleById = new Map(samplesTable.rows.map((row) => [row.compound_id, row]));
const moleculeById = new Map(moleculesTable.rows.map((row) => [row.canonical_id, row]));
const internalRows = [];
for (const sample of samplesTable.rows) {
  if (sample.mapping_confidence !== "confirmed" || !sample.canonical_smiles) {
    throw new Error(`Dataset v0.2 contains an unverified training identity: ${sample.compound_id}`);
  }
  internalRows.push(
    makeInternalRow({
      compoundId: sample.compound_id,
      smiles: sample.canonical_smiles,
      activityType: "MMGBSA_dG_Bind_static",
      activityValue: sample.label_score,
      dataSource: "ATP-Navigator internal VSW static MMGBSA",
      reference: sample.label_source,
      confidence: "high_internal_identity_confirmed",
    }),
  );
  internalRows.push(
    makeInternalRow({
      compoundId: sample.compound_id,
      smiles: sample.canonical_smiles,
      activityType: "Glide_docking_score",
      activityValue: sample.glide_docking_score,
      dataSource: "ATP-Navigator internal Glide docking",
      reference: sample.feature_source,
      confidence: "high_internal_identity_confirmed",
    }),
  );
}

const mdScores = screeningTable.rows.filter(
  (row) => row.stage === "MMGBSA" && ["ATP-HIT-MD-001", "ATP-REF-IN2"].includes(row.canonical_id),
);
for (const score of mdScores) {
  if (score.canonical_id === "ATP-HIT-MD-001") {
    const hitBridge = mappingTable.rows.find(
      (row) => row.original_name === "ATP-HIT-MD-001" && row.confidence === "confirmed",
    );
    if (!hitBridge || !sampleById.has(hitBridge.canonical_id)) {
      throw new Error("Confirmed ATP-HIT-MD-001 to Hit3 bridge is missing");
    }
    internalRows.push(
      makeInternalRow({
        compoundId: hitBridge.canonical_id,
        smiles: sampleById.get(hitBridge.canonical_id).canonical_smiles,
        activityType: "MMGBSA_dG_Bind_MD_mean_1000_frames",
        activityValue: score.score,
        dataSource: "ATP-Navigator internal MD/MMGBSA (Hit3)",
        reference: score.source_file,
        confidence: "high_internal_identity_confirmed",
      }),
    );
  } else {
    const referenceMolecule = moleculeById.get("ATP-REF-IN2");
    internalRows.push(
      makeInternalRow({
        compoundId: "ATP-REF-IN2",
        smiles: referenceMolecule?.smiles ?? "",
        activityType: "MMGBSA_dG_Bind_MD_mean_1000_frames",
        activityValue: score.score,
        dataSource: "ATP-Navigator internal MD/MMGBSA (IN-2)",
        reference: score.source_file,
        confidence: "medium_internal_alias_structure_unresolved",
      }),
    );
  }
}

const outputRows = [...publicRows, ...internalRows];
const csvText = toCsv(outputHeaders, outputRows);
const validationWorkbook = await Workbook.fromCSV(csvText, { sheetName: "dataset_v1" });
const validationSheet = validationWorkbook.worksheets.getItemAt(0);
const used = validationSheet.getUsedRange(true);
if (!used || used.rowCount !== outputRows.length + 1 || used.columnCount !== outputHeaders.length) {
  throw new Error("Dataset v1 CSV dimension validation failed");
}
const inspection = await validationWorkbook.inspect({
  kind: "region",
  sheetId: validationSheet.name,
  range: "A1:L8",
  maxChars: 6000,
  tableMaxRows: 8,
  tableMaxCols: 12,
});

await fsp.mkdir(outputDir, { recursive: true });
await fsp.writeFile(outputCsv, csvText, "utf8");

const layerCounts = Object.fromEntries(
  [...new Set(outputRows.map((row) => row.dataset_layer))].map((layer) => [
    layer,
    outputRows.filter((row) => row.dataset_layer === layer).length,
  ]),
);
const metadata = {
  dataset_version: "ATP-Navigator Dataset v1.0",
  purpose: "three-layer evidence registry; no cross-label training implied",
  created_at: new Date().toISOString(),
  output_file: path.relative(projectRoot, outputCsv).split(path.sep).join("/"),
  output_sha256: sha256Text(csvText),
  row_count: outputRows.length,
  column_count: outputHeaders.length,
  unique_compound_ids: new Set(outputRows.map((row) => row.compound_id).filter(Boolean)).size,
  unique_nonblank_smiles: new Set(outputRows.map((row) => row.canonical_smiles).filter(Boolean)).size,
  layer_counts: layerCounts,
  public_source: {
    file: publicCsv,
    sha256: await sha256File(publicCsv),
    raw_rows: publicTable.rows.length,
    exact_duplicate_rows_excluded: duplicateRowsExcluded,
    identity_conflict_ids_excluded: [...conflictingIds].sort(),
    identity_conflict_rows_excluded: identityConflictRowsExcluded,
    included_rows: publicRows.length,
    canonical_smiles_policy: "copied from source-declared RDKit-normalized smiles; not independently recanonicalized in this build",
  },
  internal_source: {
    static_mmgbsa_rows: samplesTable.rows.length,
    glide_docking_rows: samplesTable.rows.length,
    md_mmgbsa_mean_rows: mdScores.length,
    included_rows: internalRows.length,
    mmgbsa_unit_policy: "blank because the processed source tables do not carry an explicit unit field",
    md_trajectory_status: "source systems are marked incomplete; only existing derived 1000-frame means are registered",
  },
  rules: {
    exact_duplicates: "excluded from processed output",
    conflicting_compound_identity: "excluded; no guessed structure reassignment",
    activity_values: "preserved as source text; comparator and range values are not coerced",
    labels: "MIC, IC50, docking, static MMGBSA, and MD MMGBSA remain separate activity_type values",
    unit_normalization: "μg/mL and µg/mL normalized to ug/mL; numeric values unchanged",
  },
  validation: {
    used_range: used.address,
    preview: inspection.ndjson ?? String(inspection),
  },
};
await fsp.writeFile(metadataPath, JSON.stringify(metadata, null, 2), "utf8");
console.log(JSON.stringify(metadata, null, 2));
