/** Build and validate the header-only External Dataset Format v1 template. */

import fsp from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(import.meta.dirname, "..");
const outputPath = path.join(projectRoot, "data", "External_Dataset_Format_v1.csv");

const headers = [
  "compound_id",
  "smiles",
  "target",
  "target_name",
  "protein_id",
  "organism",
  "activity_type",
  "activity_relation",
  "activity_value",
  "activity_unit",
  "assay_type",
  "docking_score",
  "docking_protocol",
  "binding_energy",
  "binding_energy_type",
  "source",
  "source_record_id",
  "reference",
  "license",
  "retrieved_date",
];

const csvText = `${headers.join(",")}\r\n`;
const workbook = await Workbook.fromCSV(csvText, { sheetName: "external_data" });
const sheet = workbook.worksheets.getItemAt(0);
const used = sheet.getUsedRange(true);

if (!used || used.rowCount !== 1 || used.columnCount !== headers.length) {
  throw new Error("External dataset template validation failed");
}

await workbook.inspect({
  kind: "region",
  sheetId: sheet.name,
  range: used.address,
  maxChars: 2000,
  tableMaxRows: 2,
  tableMaxCols: headers.length,
});

await fsp.mkdir(path.dirname(outputPath), { recursive: true });
await fsp.writeFile(outputPath, csvText, "utf8");
console.log(JSON.stringify({ outputPath, rows: 0, columns: headers.length }, null, 2));
