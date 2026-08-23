/** Verify the generated Dataset v1.0 CSV with artifact-tool. */

import fsp from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const inputPath = path.join(projectRoot, "data", "dataset_v1.0", "ATP_Navigator_Dataset_v1.csv");
const outputPath = path.join(projectRoot, "results", "dataset_v1_validation.json");
const text = await fsp.readFile(inputPath, "utf8");
const workbook = await Workbook.fromCSV(text, { sheetName: "dataset_v1" });
const sheet = workbook.worksheets.getItemAt(0);
const used = sheet.getUsedRange(true);
if (!used) throw new Error("Generated CSV is empty");
const values = used.values;
const headers = values[0].map((value) => String(value ?? "").trim());
const rows = values.slice(1).map((valuesRow) =>
  Object.fromEntries(headers.map((header, index) => [header, String(valuesRow[index] ?? "").trim()])),
);

const distribution = (field, subset = rows) => {
  const counts = new Map();
  for (const row of subset) counts.set(row[field] || "<missing>", (counts.get(row[field] || "<missing>") ?? 0) + 1);
  return Object.fromEntries([...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])));
};
const signatures = rows.map((row) => headers.map((header) => row[header]).join("\u001f"));
const identity = new Map();
for (const row of rows) {
  if (!identity.has(row.compound_id)) identity.set(row.compound_id, new Set());
  if (row.canonical_smiles) identity.get(row.compound_id).add(row.canonical_smiles);
}

const missingByField = Object.fromEntries(
  headers.map((header) => [header, rows.filter((row) => !row[header]).length]),
);
const layerActivity = {};
for (const layer of new Set(rows.map((row) => row.dataset_layer))) {
  layerActivity[layer] = distribution("activity_type", rows.filter((row) => row.dataset_layer === layer));
}

const validation = {
  status: "valid",
  used_range: used.address,
  rows: rows.length,
  columns: headers.length,
  headers,
  unique_compound_ids: new Set(rows.map((row) => row.compound_id)).size,
  unique_nonblank_smiles: new Set(rows.map((row) => row.canonical_smiles).filter(Boolean)).size,
  exact_duplicate_rows: rows.length - new Set(signatures).size,
  compound_ids_with_multiple_nonblank_smiles: [...identity.entries()]
    .filter(([, structures]) => structures.size > 1)
    .map(([compoundId, structures]) => ({ compound_id: compoundId, structures: [...structures] })),
  quarantined_ids_present: rows.filter((row) => ["WSA236", "WSA238"].includes(row.compound_id)).length,
  layer_counts: distribution("dataset_layer"),
  activity_type_by_layer: layerActivity,
  label_confidence_counts: distribution("label_confidence"),
  missing_by_field: missingByField,
};

if (validation.rows !== 6754 || validation.columns !== 12) validation.status = "invalid_dimensions";
if (validation.exact_duplicate_rows !== 0) validation.status = "invalid_duplicates";
if (validation.compound_ids_with_multiple_nonblank_smiles.length) validation.status = "invalid_identity_conflict";
if (validation.quarantined_ids_present) validation.status = "invalid_quarantine_leak";

await fsp.writeFile(outputPath, JSON.stringify(validation, null, 2), "utf8");
console.log(JSON.stringify(validation, null, 2));
