/** Create and validate Phase 3 CSV artifacts from the Python JSON payloads. */

import fsp from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const resultsDir = path.join(projectRoot, "results");
const datasetDir = path.join(projectRoot, "data", "dataset_v0.2");

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
  if (!Array.isArray(headers) || !headers.length) throw new Error(`Missing headers for ${filePath}`);
  if (!Array.isArray(rows) || !rows.length) throw new Error(`Missing rows for ${filePath}`);
  const csvText = toCsv(headers, rows);
  const workbook = await Workbook.fromCSV(csvText, { sheetName: "data" });
  const sheet = workbook.worksheets.getItemAt(0);
  const used = sheet.getUsedRange(true);
  if (!used || used.rowCount !== rows.length + 1 || used.columnCount !== headers.length) {
    throw new Error(`CSV dimension validation failed for ${filePath}`);
  }
  const inspection = await workbook.inspect({
    kind: "region",
    sheetId: sheet.name,
    range: used.address,
    maxChars: 1000,
    tableMaxRows: 4,
    tableMaxCols: Math.min(headers.length, 20),
  });
  if (!inspection) throw new Error(`CSV inspection failed for ${filePath}`);
  await fsp.writeFile(filePath, csvText, "utf8");
}

async function main() {
  await fsp.mkdir(datasetDir, { recursive: true });
  const dataset = JSON.parse(await fsp.readFile(path.join(resultsDir, "phase3_dataset_payload.json"), "utf8"));
  const results = JSON.parse(await fsp.readFile(path.join(resultsDir, "phase3_results_payload.json"), "utf8"));

  const outputs = [
    [path.join(datasetDir, "samples.csv"), dataset.samples_headers, dataset.samples_rows],
    [path.join(datasetDir, "feature_manifest.csv"), dataset.feature_manifest_headers, dataset.feature_manifest_rows],
    [path.join(resultsDir, "phase3_model_comparison.csv"), results.comparison_headers, results.comparison_rows],
    [path.join(resultsDir, "phase3_oof_predictions.csv"), results.oof_headers, results.oof_rows],
    [path.join(resultsDir, "feature_importance.csv"), results.importance_headers, results.importance_rows],
    [path.join(resultsDir, "ranking_output.csv"), results.ranking_headers, results.ranking_rows],
  ];
  for (const [filePath, headers, rows] of outputs) await writeValidatedCsv(filePath, headers, rows);
  console.log(JSON.stringify({
    outputs: outputs.map(([filePath, headers, rows]) => ({
      file: path.relative(projectRoot, filePath).replaceAll("\\", "/"),
      rows: rows.length,
      columns: headers.length,
    })),
  }, null, 2));
}

await main();
