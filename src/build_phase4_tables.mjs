/** Create and validate the additive Phase 4 CSV result tables. */

import fsp from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const resultsDir = path.join(projectRoot, "results");
const payload = JSON.parse(await fsp.readFile(path.join(resultsDir, "phase4_ranker_payload.json"), "utf8"));

function csvCell(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function toCsv(headers, rows) {
  return [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))]
    .map((row) => row.map(csvCell).join(","))
    .join("\r\n") + "\r\n";
}

async function writeValidatedCsv(fileName, sheetName, headers, rows) {
  if (!Array.isArray(headers) || headers.length === 0 || !Array.isArray(rows) || rows.length === 0) {
    throw new Error(`Missing tabular payload for ${fileName}`);
  }
  const csvText = toCsv(headers, rows);
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const sheet = workbook.worksheets.getItemAt(0);
  const used = sheet.getUsedRange(true);
  if (!used || used.rowCount !== rows.length + 1 || used.columnCount !== headers.length) {
    throw new Error(`CSV dimension validation failed for ${fileName}`);
  }
  const check = await workbook.inspect({
    kind: "region",
    sheetId: sheet.name,
    range: used.address,
    maxChars: 1800,
    tableMaxRows: Math.min(rows.length + 1, 8),
    tableMaxCols: Math.min(headers.length, 24),
  });
  if (!check) throw new Error(`CSV inspection failed for ${fileName}`);
  await fsp.writeFile(path.join(resultsDir, fileName), csvText, "utf8");
  return { file: `results/${fileName}`, rows: rows.length, columns: headers.length };
}

const outputs = [];
outputs.push(await writeValidatedCsv(
  "phase4_ranking_comparison.csv",
  "phase4_comparison",
  payload.comparison_headers,
  payload.comparison_rows,
));
outputs.push(await writeValidatedCsv(
  "phase4_ranker_oof_predictions.csv",
  "phase4_oof",
  payload.prediction_headers,
  payload.prediction_rows,
));
console.log(JSON.stringify({ outputs }, null, 2));
