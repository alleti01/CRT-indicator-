import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

process.on("uncaughtException", (error) => {
  console.error(`WORKBOOK_ERROR: ${error?.message || error}`);
  process.exit(1);
});
process.on("unhandledRejection", (error) => {
  console.error(`WORKBOOK_ERROR: ${error?.message || error}`);
  process.exit(1);
});

const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const inputDir = path.join(projectRoot, "phase16/results/retest_reclaim_research");
const outputDir = path.join(projectRoot, "outputs/retest_reclaim_research");
const qaDir = "/private/tmp/retest_reclaim_workbook_qa";
const outputPath = path.join(outputDir, "RETEST_RECLAIM_FORENSIC_RESEARCH.xlsx");
const previewPath = path.join(outputDir, "RETEST_RECLAIM_SUMMARY.png");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(qaDir, { recursive: true });

const workbook = Workbook.create();
const datasets = new Map();

function columnLetter(index) {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function fieldIndex(values, name) {
  const index = values[0].findIndex((value) => String(value) === name);
  if (index < 0) throw new Error(`Missing field ${name}`);
  return index;
}

function sourceFormula(sheetName, values, rowIndex, field) {
  const column = columnLetter(fieldIndex(values, field));
  return `='${sheetName}'!${column}${rowIndex + 1}`;
}

async function addCsvSheet(name, fileName, options = {}) {
  const text = await fs.readFile(path.join(inputDir, fileName), "utf8");
  const imported = await Workbook.fromCSV(text, { sheetName: name });
  const source = imported.worksheets.getItemAt(0);
  const values = source.getUsedRange(true).values;
  datasets.set(name, values);
  const sheet = workbook.worksheets.add(name);
  if (!values.length || !values[0].length) return sheet;
  const range = sheet.getRangeByIndexes(0, 0, values.length, values[0].length);
  range.values = values;
  range.format.font = { name: "Aptos", size: options.fontSize || 9, color: "#1F2937" };
  range.format.rowHeight = 18;
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
  range.format.autofitColumns();
  for (let column = 0; column < values[0].length; column += 1) {
    const headerName = String(values[0][column] || "").toLowerCase();
    let width = Math.min(24, Math.max(10, headerName.length + 2));
    if (headerName.includes("timestamp")) width = 26;
    if (headerName.includes("reason") || headerName.includes("detail") || headerName.includes("classification")) width = 42;
    if (headerName.includes("state")) width = 21;
    sheet.getRangeByIndexes(0, column, values.length, 1).format.columnWidth = width;
  }
  if (options.pfField) {
    const pf = fieldIndex(values, options.pfField);
    const pfRange = sheet.getRangeByIndexes(1, pf, Math.max(1, values.length - 1), 1);
    pfRange.format.numberFormat = "0.000";
    pfRange.conditionalFormats.add("colorScale", {
      colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"],
    });
  }
  return sheet;
}

const summary = workbook.worksheets.add("Summary");
summary.showGridLines = false;

await addCsvSheet("Grid Summary", "current_vs_reclaim_grid.csv", { pfField: "net_profit_factor" });
await addCsvSheet("Recovered", "recovered_trade_summary.csv", { pfField: "recovered_profit_factor" });
await addCsvSheet("Special 12", "special_near_miss_analysis.csv");
await addCsvSheet("Forensic Audit", "diagnostic_bug_audit.csv");
await addCsvSheet("Bar Trace", "current_near_miss_bar_trace.csv");
await addCsvSheet("Breakdowns", "all_breakdowns.csv", { pfField: "profit_factor" });
await addCsvSheet("Current Trades", "current_confirm_trades.csv");
await addCsvSheet("Reclaim Trades", "reclaim_trades.csv");
await addCsvSheet("Candidate Outcomes", "reclaim_candidate_outcomes.csv");
await addCsvSheet("Transitions", "reclaim_transitions.csv", { fontSize: 8 });
await addCsvSheet("Leader Neighbors", "leader_neighbor_robustness.csv", { pfField: "net_profit_factor" });

const gridValues = datasets.get("Grid Summary");
const currentRow = gridValues.findIndex((row) => String(row[0]) === "CURRENT");
const leaderRow = gridValues.findIndex((row) => String(row[0]) === "P0.10_W3");
if (currentRow < 1 || leaderRow < 1) throw new Error("Current or leader row missing");

summary.getRange("A1:N2").merge();
summary.getRange("A1").values = [["Retest-Reclaim Forensic Research"]];
summary.getRange("A1:N2").format = {
  fill: "#102A43",
  font: { name: "Aptos Display", size: 20, bold: true, color: "#FFFFFF" },
  verticalAlignment: "center",
};
summary.getRange("A3:N3").merge();
summary.getRange("A3").values = [[
  "Development window: 2026-06-29 through 2026-08-18 · 10,164 five-minute bars · $14.50 round-turn execution cost · Frozen production logic unchanged",
]];
summary.getRange("A3:N3").format = {
  fill: "#D9EAF7",
  font: { name: "Aptos", size: 10, italic: true, color: "#334E68" },
  rowHeight: 24,
};

summary.getRange("A5:F5").values = [["Metric", "Current gross", "Current net", "P0.10/W3 gross", "P0.10/W3 net", "Net change"]];
const metricRows = [
  ["N", "gross_N", "net_N", "0"],
  ["Wins", "gross_wins", "net_wins", "0"],
  ["Losses", "gross_losses", "net_losses", "0"],
  ["Win rate", "gross_win_pct", "net_win_pct", "0.0\"%\""],
  ["Average R", "gross_avg_R", "net_avg_R", "0.000"],
  ["Total R", "gross_total_R", "net_total_R", "0.000"],
  ["Profit factor", "gross_profit_factor", "net_profit_factor", "0.000"],
  ["Max drawdown R", "gross_max_drawdown_R", "net_max_drawdown_R", "0.000"],
  ["Average MFE R", "gross_avg_MFE_R", "net_avg_MFE_R", "0.000"],
  ["Average MAE R", "gross_avg_MAE_R", "net_avg_MAE_R", "0.000"],
];
summary.getRange("A6:A15").values = metricRows.map((row) => [row[0]]);
for (let index = 0; index < metricRows.length; index += 1) {
  const sheetRow = 6 + index;
  const [, grossField, netField, format] = metricRows[index];
  summary.getRange(`B${sheetRow}`).formulas = [[sourceFormula("Grid Summary", gridValues, currentRow, grossField)]];
  summary.getRange(`C${sheetRow}`).formulas = [[sourceFormula("Grid Summary", gridValues, currentRow, netField)]];
  summary.getRange(`D${sheetRow}`).formulas = [[sourceFormula("Grid Summary", gridValues, leaderRow, grossField)]];
  summary.getRange(`E${sheetRow}`).formulas = [[sourceFormula("Grid Summary", gridValues, leaderRow, netField)]];
  summary.getRange(`F${sheetRow}`).formulas = [[`=E${sheetRow}-C${sheetRow}`]];
  summary.getRange(`B${sheetRow}:F${sheetRow}`).format.numberFormat = format;
}

summary.getRange("H5:N5").merge();
summary.getRange("H5").values = [["Forensic verdict"]];
summary.getRange("H6:I9").values = [
  ["Forensic CSV bug?", "YES"],
  ["Strategy logic bug?", "NO"],
  ["Robust neighbors?", "NO"],
  ["Freeze for new OOS?", "NO"],
];
summary.getRange("J6:N9").merge();
summary.getRange("J6").values = [[
  "The old near-miss CSV combined a diagnostic proxy bar with the rejection reason from the actual terminal state-transition bar. Candidate 86 was killed at 14:00 (close 28,910.50 > 28,905.2771), before the 14:05 bearish proxy. Candidate 221 used its 00:10 retest bar as a fallback proxy; the real invalidation occurred later at 00:20 (close 29,832.50 > 29,828.1231).",
]];
summary.getRange("J6:N9").format = { wrapText: true, verticalAlignment: "top", fill: "#FFF7D6", font: { name: "Aptos", size: 10, color: "#5C4813" } };

summary.getRange("H11:N11").merge();
summary.getRange("H11").values = [["Research conclusion"]];
summary.getRange("H12:N16").merge();
summary.getRange("H12").values = [[
  "All 20 preregistered reclaim variants were weaker than the current frozen gate after realistic costs. The quality leader P0.10/W3 still had negative expectancy (−0.0679 R), PF 0.871, and max drawdown 8.925 R. Wider penetration recovered up to nine rejected trades, but every recovered cohort had negative expectancy and PF below 1. Future MFE/MAE was used only for retrospective diagnosis.",
]];
summary.getRange("H12:N16").format = { wrapText: true, verticalAlignment: "top", fill: "#FDECEC", font: { name: "Aptos", size: 10, color: "#7F1D1D" } };

for (const address of ["A5:F5", "H5:N5", "H11:N11"]) {
  summary.getRange(address).format = {
    fill: "#17324D",
    font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" },
    rowHeight: 27,
    verticalAlignment: "center",
  };
}
summary.getRange("A6:F15").format = {
  font: { name: "Aptos", size: 10, color: "#1F2937" },
  borders: { preset: "inside", style: "thin", color: "#D9E2EC" },
  rowHeight: 22,
};
summary.getRange("H6:I9").format = {
  font: { name: "Aptos", size: 10, color: "#1F2937" },
  borders: { preset: "inside", style: "thin", color: "#D9E2EC" },
  rowHeight: 25,
};
summary.getRange("I6:I9").format = { font: { name: "Aptos", size: 10, bold: true, color: "#B42318" }, horizontalAlignment: "center" };

summary.getRange("A18:F18").merge();
summary.getRange("A18").values = [["Net profit factor sensitivity (after $14.50/trade)"]];
summary.getRange("A19:E19").values = [["Penetration ATR", "1 bar", "2 bars", "3 bars", "4 bars"]];
const penetrationValues = [0.10, 0.20, 0.30, 0.40, 0.50];
for (let pIndex = 0; pIndex < penetrationValues.length; pIndex += 1) {
  const pValue = penetrationValues[pIndex];
  const row = 20 + pIndex;
  summary.getRange(`A${row}`).values = [[pValue]];
  summary.getRange(`A${row}`).format.numberFormat = "0.00";
  for (let window = 1; window <= 4; window += 1) {
    const variant = `P${pValue.toFixed(2)}_W${window}`;
    const sourceRow = gridValues.findIndex((values) => String(values[0]) === variant);
    summary.getRangeByIndexes(row - 1, window, 1, 1).formulas = [[sourceFormula("Grid Summary", gridValues, sourceRow, "net_profit_factor")]];
    summary.getRangeByIndexes(row - 1, window, 1, 1).format.numberFormat = "0.000";
  }
}
summary.getRange("A18:E18").format = { fill: "#17324D", font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" }, rowHeight: 27 };
summary.getRange("A19:E19").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 10, bold: true, color: "#334E68" }, horizontalAlignment: "center" };
summary.getRange("A20:E24").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, horizontalAlignment: "center" };
summary.getRange("B20:E24").conditionalFormats.add("colorScale", { colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"] });

summary.getRange("H18:N18").merge();
summary.getRange("H18").values = [["Causal event order tested"]];
summary.getRange("H19:N24").merge();
summary.getRange("H19").values = [[
  "1. Accept canonical setup only while idle.  2. Matching BOS may occur on the setup bar.  3. Retest must occur on a later bar.  4. Temporary close penetration may not exceed the preregistered ATR limit.  5. Reclaim must be a later directional close back across stored BOS.  6. Existing confirmation must occur on a still later bar.  7. Entry occurs only after that completed confirmation. Opposite BOS and active-state invalidations are evaluated causally before advancement.",
]];
summary.getRange("H18:N18").format = { fill: "#17324D", font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" }, rowHeight: 27 };
summary.getRange("H19:N24").format = { fill: "#EEF5F9", wrapText: true, verticalAlignment: "top", font: { name: "Aptos", size: 10, color: "#334E68" } };

summary.getRange("A1:A24").format.columnWidth = 21;
summary.getRange("B1:F24").format.columnWidth = 14;
summary.getRange("G1:G24").format.columnWidth = 3;
summary.getRange("H1:I24").format.columnWidth = 23;
summary.getRange("J1:N24").format.columnWidth = 14;
summary.freezePanes.freezeRows(3);

const methodology = workbook.worksheets.add("Methodology");
methodology.showGridLines = false;
methodology.getRange("A1:H2").merge();
methodology.getRange("A1").values = [["Methodology and guardrails"]];
methodology.getRange("A1:H2").format = { fill: "#102A43", font: { name: "Aptos Display", size: 18, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" };
methodology.getRange("A4:B15").values = [
  ["Scope", "Development data only: 2026-06-29 through 2026-08-18 (America/Chicago). No unseen OOS data accessed."],
  ["Bars", "10,164 five-minute bars prepared with the previously parity-validated provider-roll selection, causal forward adjustment, and incomplete-resample parity setting."],
  ["Frozen inputs", "Phase 3 structure, Phase 4 liquidity, Phase 5 setup/Variant-C feed, scoring, sessions, HTF regime, cooldown, anti-chase, ATR stop, 2R target, and 60-minute hold were unchanged."],
  ["Current model", "Setup → BOS → later Retest → later Confirm; 0.10×current-bar ATR invalidation; stop-first on ambiguous exit bars."],
  ["Research variant", "Setup → BOS → later Retest touch → later bearish/bullish BOS reclaim → later existing Confirm. Long is the exact mirror of Short."],
  ["Grid", "Maximum close penetration: 0.10/0.20/0.30/0.40/0.50 ATR. Reclaim window: 1/2/3/4 loaded bars. Exactly 20 cells; no search outside the grid."],
  ["Costs", "$14.50 round turn: one NQ tick of slippage per side plus $4.50 commission, converted to R trade by trade using $20/point and frozen stop risk."],
  ["Selection", "Quality leader chosen lexicographically by net PF, then lower max drawdown, then higher net AvgR—never by frequency or TotalR alone."],
  ["Robustness", "Neighbor robustness requires at least three adjacent cells, at least 75% with positive net AvgR and PF>1, and positive medians for both."],
  ["MFE/MAE", "Retrospective diagnostics only; never used by setup qualification, entry timing, or parameter selection."],
  ["Forensic defect", "The old near-miss export mislabeled a diagnostic proxy as a would-be confirmation while attaching the actual terminal bar's rejection reason."],
  ["Production changes", "None. Pine and the frozen Python baseline were not modified."],
];
methodology.getRange("A4:A15").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 10, bold: true, color: "#334E68" }, verticalAlignment: "top" };
methodology.getRange("B4:B15").format = { font: { name: "Aptos", size: 10, color: "#1F2937" }, wrapText: true, verticalAlignment: "top" };
methodology.getRange("A4:B15").format.rowHeight = 42;
methodology.getRange("A1:A15").format.columnWidth = 22;
methodology.getRange("B1:B15").format.columnWidth = 100;
methodology.freezePanes.freezeRows(2);

const inspect = await workbook.inspect({
  kind: "workbook,sheet,formula,drawing",
  maxChars: 12000,
  tableMaxRows: 8,
  tableMaxCols: 10,
});
console.log(inspect.ndjson || inspect);
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  maxChars: 5000,
});
console.log(formulaErrors.ndjson || formulaErrors);

const preview = await workbook.render({ sheetName: "Summary", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
for (const [sheetName, range] of Object.entries({
  "Grid Summary": "A1:AU12",
  "Recovered": "A1:Q12",
  "Special 12": "A1:N18",
  "Forensic Audit": "A1:X13",
  "Bar Trace": "A1:AF18",
  "Breakdowns": "A1:Z18",
  "Current Trades": "A1:Y15",
  "Reclaim Trades": "A1:Y15",
  "Candidate Outcomes": "A1:K15",
  "Transitions": "A1:Z15",
  "Leader Neighbors": "A1:AV6",
  "Methodology": "A1:B15",
})) {
  const rendered = await workbook.render({ sheetName, range, scale: 0.8, format: "png" });
  await fs.writeFile(
    path.join(qaDir, `${sheetName.toLowerCase().replaceAll(" ", "_")}.png`),
    new Uint8Array(await rendered.arrayBuffer()),
  );
}

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(JSON.stringify({ outputPath, previewPath, qaDir }));
