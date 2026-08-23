import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const resultsDir = path.join(projectRoot, "results");
const payload = JSON.parse(
  await fs.readFile(path.join(resultsDir, "baseline_comparison_payload.json"), "utf8"),
);

function csvCell(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const csvText = [payload.comparison_headers, ...payload.comparison_rows.map((row) =>
  payload.comparison_headers.map((header) => row[header] ?? ""),
)]
  .map((row) => row.map(csvCell).join(","))
  .join("\r\n") + "\r\n";

const workbook = await Workbook.fromCSV(csvText, { sheetName: "baseline_comparison" });
const sheet = workbook.worksheets.getItemAt(0);
const used = sheet.getUsedRange(true);
if (!used || used.rowCount !== payload.comparison_rows.length + 1) {
  throw new Error("baseline_comparison.csv row validation failed");
}
const check = await workbook.inspect({
  kind: "region",
  sheetId: sheet.name,
  range: used.address,
  maxChars: 4000,
  tableMaxRows: 8,
  tableMaxCols: payload.comparison_headers.length,
});
console.log(check.ndjson);

await fs.writeFile(path.join(resultsDir, "baseline_comparison.csv"), csvText, "utf8");
