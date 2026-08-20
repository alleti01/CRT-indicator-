import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const inputDir = path.join(projectRoot, "phase16/results/retest_gate_forensics");
const outputDir = path.join(projectRoot, "outputs/retest_gate_forensics");
const qaDir = "/tmp/retest_gate_forensic_workbook_qa";
const outputPath = path.join(outputDir, "RETEST_GATE_FORENSIC_TRACE.xlsx");
const previewPath = path.join(outputDir, "RETEST_GATE_FORENSIC_SUMMARY.png");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(qaDir, { recursive: true });

const workbook = Workbook.create();

async function addCsvSheet(name, fileName) {
  const csvText = await fs.readFile(path.join(inputDir, fileName), "utf8");
  const imported = await Workbook.fromCSV(csvText, { sheetName: name });
  const source = imported.worksheets.getItemAt(0);
  const values = source.getUsedRange(true).values;
  const sheet = workbook.worksheets.add(name);
  if (values.length && values[0].length) {
    const target = sheet.getRangeByIndexes(0, 0, values.length, values[0].length);
    target.values = values;
    target.format.font = { name: "Aptos", size: 9, color: "#1F2937" };
    target.format.rowHeight = 18;
    const header = sheet.getRangeByIndexes(0, 0, 1, values[0].length);
    header.format = {
      fill: "#17324D",
      font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" },
      rowHeight: 42,
      wrapText: true,
      verticalAlignment: "center",
    };
    sheet.freezePanes.freezeRows(1);
    sheet.showGridLines = false;
    target.format.autofitColumns();
    for (let column = 0; column < values[0].length; column += 1) {
      const columnRange = sheet.getRangeByIndexes(0, column, values.length, 1);
      const headerName = String(values[0][column] || "").toLowerCase();
      let width = Math.min(26, Math.max(11, headerName.length + 2));
      if (headerName.includes("timestamp")) width = 27;
      if (headerName.includes("state")) width = 22;
      if (headerName === "event") width = 26;
      if (headerName.includes("condition") || headerName.includes("reason") || headerName.includes("detail")) width = 58;
      if (headerName.includes("json")) width = 58;
      columnRange.format.columnWidth = width;
    }
  }
  return sheet;
}

await addCsvSheet("Short Candidates", "short_candidates.csv");
await addCsvSheet("Long Candidates", "long_candidates.csv");
await addCsvSheet("Event Trace", "candidate_bar_events.csv");
await addCsvSheet("Near Misses", "near_miss_shorts.csv");
await addCsvSheet("Retest Conditions", "short_retest_condition_summary.csv");
await addCsvSheet("Confirm Conditions", "short_confirmation_condition_summary.csv");

const summary = workbook.worksheets.add("Summary");
summary.showGridLines = false;
summary.getRange("A1:P2").merge();
summary.getRange("A1").values = [["Retest-Gated Entry Forensic Trace"]];
summary.getRange("A1:P2").format = {
  fill: "#102A43",
  font: { name: "Aptos Display", size: 20, bold: true, color: "#FFFFFF" },
  verticalAlignment: "center",
  horizontalAlignment: "left",
};
summary.getRange("A3:P3").merge();
summary.getRange("A3").values = [[
  "Frozen parity window: 2026-06-29 through 2026-08-18 • Diagnostic replay only • No strategy parameters changed",
]];
summary.getRange("A3:P3").format = {
  fill: "#D9EAF7",
  font: { name: "Aptos", size: 10, italic: true, color: "#334E68" },
  rowHeight: 24,
};

summary.getRange("A5:C5").values = [["Funnel stage", "Short", "Long"]];
summary.getRange("A6:A14").values = [
  ["Setup"],
  ["Variant-C qualified"],
  ["Candidate accepted"],
  ["BOS"],
  ["Retest touched"],
  ["Retest accepted"],
  ["Confirm candidate"],
  ["Confirm accepted"],
  ["Entry"],
];
const shortFormulas = [
  "=COUNTA('Short Candidates'!$A$2:$A$121)",
  "=COUNTIF('Short Candidates'!$H$2:$H$121,TRUE)",
  "=COUNTIF('Short Candidates'!$K$2:$K$121,TRUE)",
  "=COUNT('Short Candidates'!$M$2:$M$121)",
  "=COUNTIF('Short Candidates'!$V$2:$V$121,TRUE)",
  "=COUNTIF('Short Candidates'!$W$2:$W$121,TRUE)",
  "=COUNTIF('Short Candidates'!$AA$2:$AA$121,TRUE)",
  "=COUNTIF('Short Candidates'!$AB$2:$AB$121,TRUE)",
  '=COUNTIF(\'Short Candidates\'!$AO$2:$AO$121,"ENTRY")',
];
const longFormulas = [
  "=COUNTA('Long Candidates'!$A$2:$A$137)",
  "=COUNTIF('Long Candidates'!$H$2:$H$137,TRUE)",
  "=COUNTIF('Long Candidates'!$K$2:$K$137,TRUE)",
  "=COUNT('Long Candidates'!$M$2:$M$137)",
  "=COUNTIF('Long Candidates'!$V$2:$V$137,TRUE)",
  "=COUNTIF('Long Candidates'!$W$2:$W$137,TRUE)",
  "=COUNTIF('Long Candidates'!$AA$2:$AA$137,TRUE)",
  "=COUNTIF('Long Candidates'!$AB$2:$AB$137,TRUE)",
  '=COUNTIF(\'Long Candidates\'!$AO$2:$AO$137,"ENTRY")',
];
summary.getRange("B6:B14").formulas = shortFormulas.map((formula) => [formula]);
summary.getRange("C6:C14").formulas = longFormulas.map((formula) => [formula]);

summary.getRange("E5:G5").values = [["Short first-death reason", "Count", "% setups"]];
const rejectionCategories = [
  "regime restriction",
  "opposite BOS invalidation",
  "retest touched but rejected",
  "setup rejected",
  "confirmation condition rejected",
  "retest expired",
  "BOS expired",
  "session restriction",
  "no matching BOS",
  "retest never touched",
  "confirmation never occurred",
  "invalid risk",
  "other",
];
summary.getRange("E6:E18").values = rejectionCategories.map((value) => [value]);
summary.getRange("F6:F18").formulas = rejectionCategories.map(
  (_, index) => [`=COUNTIF('Short Candidates'!$AK$2:$AK$121,E${index + 6})`],
);
summary.getRange("G6:G18").formulas = rejectionCategories.map(
  (_, index) => [`=IF($B$6=0,0,F${index + 6}/$B$6)`],
);

summary.getRange("A16:C16").merge();
summary.getRange("A16").values = [["Forensic conclusion"]];
summary.getRange("A17:C21").merge();
summary.getRange("A17").values = [[
  "No state-machine defect or long/short branch asymmetry was found. After BOS, the largest short-side bottleneck is the retest stage: 13 of 40 touched retests are rejected because the touch bar closes above BOS + 0.10×ATR. A later bearish rejection is ignored after that terminal reset. Future MFE identifies 12 near misses, but does not establish that either frozen rule should be changed.",
]];
summary.getRange("A17:C21").format = {
  fill: "#FFF7D6",
  font: { name: "Aptos", size: 10, color: "#5C4813" },
  wrapText: true,
  verticalAlignment: "top",
};

for (const address of ["A5:C5", "E5:G5", "A16:C16"]) {
  summary.getRange(address).format = {
    fill: "#17324D",
    font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" },
    rowHeight: 26,
    verticalAlignment: "center",
  };
}
summary.getRange("A6:C14").format = {
  font: { name: "Aptos", size: 10, color: "#1F2937" },
  borders: { preset: "inside", style: "thin", color: "#D9E2EC" },
};
summary.getRange("E6:G18").format = {
  font: { name: "Aptos", size: 10, color: "#1F2937" },
  borders: { preset: "inside", style: "thin", color: "#D9E2EC" },
};
summary.getRange("B6:C14").format.numberFormat = "0";
summary.getRange("F6:F18").format.numberFormat = "0";
summary.getRange("G6:G18").format.numberFormat = "0.0%";
summary.getRange("G6:G18").conditionalFormats.add("dataBar", {
  color: "#E57373",
  gradient: true,
});
summary.getRange("A5:G21").format.rowHeight = 22;
summary.getRange("A1:A21").format.columnWidth = 25;
summary.getRange("B1:C21").format.columnWidth = 12;
summary.getRange("D1:D21").format.columnWidth = 3;
summary.getRange("E1:E21").format.columnWidth = 31;
summary.getRange("F1:G21").format.columnWidth = 12;
summary.getRange("H1:H21").format.columnWidth = 3;
summary.getRange("I1:P21").format.columnWidth = 12;
summary.freezePanes.freezeRows(3);

const chart = summary.charts.add("bar", summary.getRange("A5:C14"));
chart.title = "Stage survival: Short vs Long";
chart.titleTextStyle.fontSize = 12;
chart.hasLegend = true;
chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
chart.yAxis = { numberFormatCode: "0" };
chart.setPosition("I5", "P19");

const inspect = await workbook.inspect({
  kind: "workbook,sheet,formula,drawing",
  maxChars: 10000,
  tableMaxRows: 6,
  tableMaxCols: 8,
});
console.log(inspect.ndjson || inspect);

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  maxChars: 4000,
});
console.log(formulaErrors.ndjson || formulaErrors);

const preview = await workbook.render({
  sheetName: "Summary",
  autoCrop: "all",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const qaRanges = {
  "Short Candidates": "A1:P12",
  "Long Candidates": "A1:P12",
  "Event Trace": "A1:AB12",
  "Near Misses": "A1:P13",
  "Retest Conditions": "A1:C4",
  "Confirm Conditions": "A1:C6",
};
for (const [sheetName, range] of Object.entries(qaRanges)) {
  const rendered = await workbook.render({ sheetName, range, scale: 0.8, format: "png" });
  const safeName = sheetName.toLowerCase().replaceAll(" ", "_");
  await fs.writeFile(
    path.join(qaDir, `${safeName}.png`),
    new Uint8Array(await rendered.arrayBuffer()),
  );
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, previewPath }));
