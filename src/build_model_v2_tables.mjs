/** Create and validate Model v2 CSV result artifacts from the immutable JSON payload. */

import fsp from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const resultsDir = path.join(projectRoot, "results", "model_v2");
const payloadPath = path.join(resultsDir, "model_v2_payload.json");

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
  if (!Array.isArray(headers) || headers.length === 0) throw new Error(`Missing headers: ${filePath}`);
  if (!Array.isArray(rows) || rows.length === 0) throw new Error(`Missing rows: ${filePath}`);
  const csvText = toCsv(headers, rows);
  const workbook = await Workbook.fromCSV(csvText, { sheetName: "data" });
  const sheet = workbook.worksheets.getItemAt(0);
  const used = sheet.getUsedRange(true);
  if (!used || used.rowCount !== rows.length + 1 || used.columnCount !== headers.length) {
    throw new Error(`CSV dimension validation failed: ${filePath}`);
  }
  const inspection = await workbook.inspect({
    kind: "region",
    sheetId: sheet.name,
    range: used.address,
    maxChars: 1200,
    tableMaxRows: 5,
    tableMaxCols: Math.min(headers.length, 20),
  });
  if (!inspection) throw new Error(`CSV inspection failed: ${filePath}`);
  await fsp.writeFile(filePath, csvText, "utf8");
}

async function main() {
  const payload = JSON.parse(await fsp.readFile(payloadPath, "utf8"));
  const outputs = [
    ["external_task_metrics.csv", "external_metrics"],
    ["internal_model_comparison.csv", "internal_comparison"],
    ["internal_oof_predictions.csv", "internal_oof"],
    ["external_priors_internal.csv", "internal_priors"],
  ];
  for (const [fileName, tableName] of outputs) {
    await writeValidatedCsv(
      path.join(resultsDir, fileName),
      payload.table_headers[tableName],
      payload.tables[tableName],
    );
  }
  console.log(JSON.stringify({
    outputs: outputs.map(([fileName, tableName]) => ({
      file: path.posix.join("results", "model_v2", fileName),
      rows: payload.tables[tableName].length,
      columns: payload.table_headers[tableName].length,
    })),
  }, null, 2));
}

await main();
