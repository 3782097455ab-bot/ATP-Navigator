/** Read-only audit helper for ATP-Navigator Layer 3 tabular assets. */

import fsp from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(process.argv[2] || path.resolve(import.meta.dirname, ".."));
const outputPath = process.argv[3];

async function readCsv(relativePath) {
  const filePath = path.join(projectRoot, relativePath);
  const text = await fsp.readFile(filePath, "utf8");
  const workbook = await Workbook.fromCSV(text, { sheetName: path.basename(relativePath, ".csv") });
  const sheet = workbook.worksheets.getItemAt(0);
  const values = sheet.getUsedRange(true)?.values ?? [];
  if (!values.length) return { headers: [], rows: [] };
  const headers = values[0].map((value) => String(value ?? "").trim());
  const rows = values.slice(1).map((valuesRow) =>
    Object.fromEntries(headers.map((header, index) => [header, String(valuesRow[index] ?? "").trim()])),
  );
  return { headers, rows };
}

const samples = await readCsv("data/dataset_v0.2/samples.csv");
const screening = await readCsv("data/screening_records.csv");
const systems = await readCsv("data/systems.csv");
const mapping = await readCsv("data/compound_mapping_v1.csv");
const docking = await readCsv("data/docking_features_v0_2.csv");
const molecules = await readCsv("data/molecules.csv");

const distribution = (rows, field) => {
  const counts = new Map();
  for (const row of rows) counts.set(row[field] || "<missing>", (counts.get(row[field] || "<missing>") ?? 0) + 1);
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
};

const verifiedSampleIds = new Set(samples.rows.map((row) => row.compound_id));
const candidateDocking = docking.rows.filter((row) => verifiedSampleIds.has(row.canonical_id));
const moleculeById = new Map(molecules.rows.map((row) => [row.canonical_id, row]));
const dockingIds = new Set(docking.rows.map((row) => row.canonical_id).filter(Boolean));
const dockingIdentityCoverage = [...dockingIds].map((canonicalId) => ({
  canonical_id: canonicalId,
  has_molecule_row: moleculeById.has(canonicalId),
  has_smiles: Boolean(moleculeById.get(canonicalId)?.smiles),
}));
const relevantMapping = mapping.rows.filter((row) =>
  /hit|top-3|466|in-2|md2/i.test(`${row.canonical_id} ${row.original_name}`),
);

const summary = {
  samples: {
    row_count: samples.rows.length,
    headers: samples.headers,
    identity_rows: samples.rows.map((row) => ({
      compound_id: row.compound_id,
      compound_code: row.compound_code,
      historical_alias: row.historical_alias,
      canonical_smiles: row.canonical_smiles,
      inchi_key: row.inchi_key,
      mapping_confidence: row.mapping_confidence,
      label_type: row.label_type,
      label_protocol: row.label_protocol,
      label_score: row.label_score,
      label_source: row.label_source,
      glide_docking_score: row.glide_docking_score,
      feature_source: row.feature_source,
    })),
  },
  screening: {
    row_count: screening.rows.length,
    headers: screening.headers,
    stage_distribution: distribution(screening.rows, "stage"),
    rows: screening.rows,
  },
  systems: {
    row_count: systems.rows.length,
    headers: systems.headers,
    rows: systems.rows,
  },
  mapping: {
    row_count: mapping.rows.length,
    relevant_rows: relevantMapping,
    confidence_distribution: distribution(mapping.rows, "confidence"),
  },
  molecules: {
    row_count: molecules.rows.length,
    selected_rows: molecules.rows.filter((row) =>
      ["ATP-SMI-1EDF03AEDEF9", "ATP-SMI-874C2DE25FE4", "ATP-REF-IN2", "ATP-HIT-MD-001"].includes(
        row.canonical_id,
      ),
    ),
  },
  docking: {
    row_count: docking.rows.length,
    headers: docking.headers,
    unique_ids: dockingIds.size,
    ids_with_molecule_row: dockingIdentityCoverage.filter((row) => row.has_molecule_row).length,
    ids_with_smiles: dockingIdentityCoverage.filter((row) => row.has_smiles).length,
    candidate_rows: candidateDocking.length,
    candidate_unique_ids: new Set(candidateDocking.map((row) => row.canonical_id)).size,
    candidate_pose_distribution: distribution(candidateDocking, "canonical_id"),
  },
};

const output = JSON.stringify(summary, null, 2);
if (outputPath) await fsp.writeFile(outputPath, output, "utf8");
else console.log(output);
