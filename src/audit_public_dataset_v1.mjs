/** Read-only audit helper for the user-supplied public training CSV. */

import fsp from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const inputPath = process.argv[2];
const outputPath = process.argv[3];
if (!inputPath) throw new Error("Usage: node audit_public_dataset_v1.mjs <input.csv>");

const csvText = await fsp.readFile(inputPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "public_source" });
const sheet = workbook.worksheets.getItemAt(0);
const used = sheet.getUsedRange(true);
if (!used) throw new Error("CSV is empty");
const values = used.values;
const headers = values[0].map((value) => String(value ?? "").trim());
const rows = values.slice(1).map((valuesRow) =>
  Object.fromEntries(headers.map((header, index) => [header, String(valuesRow[index] ?? "").trim()])),
);

const distribution = (field) => {
  const counts = new Map();
  for (const row of rows) {
    const value = row[field] || "<missing>";
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
};

const uniqueNonBlank = (field) => new Set(rows.map((row) => row[field]).filter(Boolean)).size;
const missingByField = Object.fromEntries(
  headers.map((header) => [header, rows.reduce((count, row) => count + (row[header] ? 0 : 1), 0)]),
);

const activitySyntax = { exact_numeric: 0, comparator: 0, range: 0, other_text: 0, missing: 0 };
for (const row of rows) {
  const value = row.activity_value;
  if (!value) activitySyntax.missing += 1;
  else if (/^[<>]=?\s*-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value)) activitySyntax.comparator += 1;
  else if (/^-?\d+(?:\.\d+)?\s*[-–]\s*-?\d+(?:\.\d+)?$/.test(value)) activitySyntax.range += 1;
  else if (/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value)) activitySyntax.exact_numeric += 1;
  else activitySyntax.other_text += 1;
}

const rowSignatures = rows.map((row) => headers.map((header) => row[header]).join("\u001f"));
const signatureCounts = new Map();
for (const signature of rowSignatures) signatureCounts.set(signature, (signatureCounts.get(signature) ?? 0) + 1);
const compoundToSmiles = new Map();
const smilesToCompounds = new Map();
for (const row of rows) {
  if (row.compound_id && row.smiles) {
    if (!compoundToSmiles.has(row.compound_id)) compoundToSmiles.set(row.compound_id, new Set());
    compoundToSmiles.get(row.compound_id).add(row.smiles);
    if (!smilesToCompounds.has(row.smiles)) smilesToCompounds.set(row.smiles, new Set());
    smilesToCompounds.get(row.smiles).add(row.compound_id);
  }
}
const conflictingCompoundIds = new Set(
  [...compoundToSmiles.entries()].filter(([, smilesSet]) => smilesSet.size > 1).map(([compoundId]) => compoundId),
);
const deduplicatedRows = rows.filter(
  (row, index) => rowSignatures.indexOf(rowSignatures[index]) === index,
);
const identityCleanRows = deduplicatedRows.filter((row) => !conflictingCompoundIds.has(row.compound_id));
const sourceTargetCounts = new Map();
for (const row of rows) {
  const key = `${row.source_database || "<missing>"}\u001f${row.target || "<missing>"}`;
  sourceTargetCounts.set(key, (sourceTargetCounts.get(key) ?? 0) + 1);
}

const summary = {
  input: inputPath,
  used_range: used.address,
  row_count: rows.length,
  column_count: headers.length,
  headers,
  unique: {
    compound_id: uniqueNonBlank("compound_id"),
    smiles: uniqueNonBlank("smiles"),
    target: uniqueNonBlank("target"),
    protein_id: uniqueNonBlank("protein_id"),
    organism: uniqueNonBlank("organism"),
    reference_doi: uniqueNonBlank("DOI"),
  },
  missing_by_field: missingByField,
  activity_value_syntax: activitySyntax,
  exact_duplicate_rows: rows.length - new Set(rowSignatures).size,
  quality_details: {
    exact_duplicate_groups: [...signatureCounts.values()].filter((count) => count > 1).length,
    compound_ids_with_multiple_smiles: [...compoundToSmiles.entries()]
      .filter(([, smilesSet]) => smilesSet.size > 1)
      .map(([compound_id, smilesSet]) => ({ compound_id, smiles: [...smilesSet] })),
    smiles_with_multiple_compound_ids: [...smilesToCompounds.entries()]
      .filter(([, compoundSet]) => compoundSet.size > 1)
      .map(([smiles, compoundSet]) => ({ smiles, compound_ids: [...compoundSet] })),
    missing_activity_rows: rows
      .filter((row) => !row.activity_value)
      .map((row) => Object.fromEntries(["compound_id", "compound_name", "target", "organism", "activity_type", "unit", "source_database", "DOI"].map((field) => [field, row[field]]))),
    unique_smiles_values: [...new Set(rows.map((row) => row.smiles).filter(Boolean))],
    layer_candidate_counts: {
      layer_1_chembl_non_atp: rows.filter(
        (row) => row.source_database === "ChEMBL" && !row.target.toLowerCase().includes("atp synthase"),
      ).length,
      layer_2_literature_or_chembl_atp: rows.filter(
        (row) => row.source_database !== "ChEMBL" || row.target.toLowerCase().includes("atp synthase"),
      ).length,
      after_exact_deduplication: deduplicatedRows.length,
      identity_conflict_rows_after_deduplication: deduplicatedRows.filter((row) =>
        conflictingCompoundIds.has(row.compound_id),
      ).length,
      training_ready_public_rows: identityCleanRows.length,
      training_ready_layer_1: identityCleanRows.filter(
        (row) => row.source_database === "ChEMBL" && !row.target.toLowerCase().includes("atp synthase"),
      ).length,
      training_ready_layer_2: identityCleanRows.filter(
        (row) => row.source_database !== "ChEMBL" || row.target.toLowerCase().includes("atp synthase"),
      ).length,
    },
  },
  distributions: {
    target: distribution("target"),
    organism: distribution("organism"),
    activity_type: distribution("activity_type"),
    unit: distribution("unit"),
    source_database: distribution("source_database"),
    data_type: distribution("data_type"),
    protein_id: distribution("protein_id"),
    source_target: [...sourceTargetCounts.entries()]
      .map(([key, count]) => {
        const [source, target] = key.split("\u001f");
        return { source, target, count };
      })
      .sort((a, b) => b.count - a.count || a.source.localeCompare(b.source)),
  },
  preview: rows.slice(0, 5),
};

const inspection = await workbook.inspect({
  kind: "region",
  sheetId: sheet.name,
  range: `A1:R6`,
  maxChars: 5000,
  tableMaxRows: 6,
  tableMaxCols: 18,
});
summary.artifact_inspection = inspection.ndjson ?? String(inspection);
const output = JSON.stringify(summary, null, 2);
if (outputPath) await fsp.writeFile(outputPath, output, "utf8");
else console.log(output);
