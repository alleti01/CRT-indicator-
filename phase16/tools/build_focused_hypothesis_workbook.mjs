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
const inputDir = path.join(projectRoot, "phase16/results/focused_hypothesis_testing");
const outputPath = path.join(inputDir, "FOCUSED_HYPOTHESIS_TESTING.xlsx");
const previewPath = path.join(inputDir, "FOCUSED_HYPOTHESIS_TESTING_SUMMARY.png");
const inspectPath = path.join(inputDir, "FOCUSED_HYPOTHESIS_TESTING.inspect.ndjson");
const qaDir = "/private/tmp/focused_hypothesis_testing_qa";
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

function fieldIndex(values, field) {
  const index = values[0].findIndex((value) => String(value) === field);
  if (index < 0) throw new Error(`Missing field ${field}`);
  return index;
}

function sourceFormula(sheetName, values, rowIndex, field) {
  return `='${sheetName}'!${columnLetter(fieldIndex(values, field))}${rowIndex + 1}`;
}

function formatFor(header) {
  const name = header.toLowerCase();
  if (name === "n" || name.endsWith("_n") || name.includes("wins") || name.includes("losses") || name.includes("flats") || name.includes("count") || name === "removed_n") return "0";
  if (name.includes("pct") || name.includes("rate")) return '0.00"%"';
  if (name.includes("timestamp")) return "yyyy-mm-dd hh:mm";
  if (name.includes("p_one") || name.includes("fdr_q")) return "0.0000";
  if (name.includes("pf")) return "0.0000";
  if (name.includes("avgr") || name.includes("totalr") || name.includes("drawdown") || name.includes("largest") || name.includes("improvement") || name.includes("median") || name.includes("atr") || name.includes("bars")) return "0.0000";
  return "General";
}

async function addCsvSheet(sheetName, fileName, options = {}) {
  const csvText = await fs.readFile(path.join(inputDir, fileName), "utf8");
  const imported = await Workbook.fromCSV(csvText, { sheetName });
  const source = imported.worksheets.getItemAt(0);
  const values = source.getUsedRange(true).values;
  datasets.set(sheetName, values);
  const sheet = workbook.worksheets.add(sheetName);
  sheet.showGridLines = false;
  if (!values.length || !values[0].length) return sheet;
  const used = sheet.getRangeByIndexes(0, 0, values.length, values[0].length);
  used.values = values;
  used.format.font = { name: "Aptos", size: options.fontSize || 8, color: "#1F2937" };
  used.format.rowHeight = 18;
  const header = sheet.getRangeByIndexes(0, 0, 1, values[0].length);
  header.format = {
    fill: "#17324D",
    font: { name: "Aptos Display", size: 9, bold: true, color: "#FFFFFF" },
    rowHeight: 48,
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.freezePanes.freezeRows(1);
  for (let column = 0; column < values[0].length; column += 1) {
    const field = String(values[0][column] || "");
    const lower = field.toLowerCase();
    let width = Math.min(24, Math.max(10, field.length + 2));
    if (lower.includes("timestamp")) width = 23;
    if (lower.includes("json")) width = 30;
    if (lower.includes("summary_role") || lower.includes("classification") || lower.includes("test_definition")) width = 34;
    sheet.getRangeByIndexes(0, column, values.length, 1).format.columnWidth = width;
    if (values.length > 1) sheet.getRangeByIndexes(1, column, values.length - 1, 1).format.numberFormat = formatFor(field);
  }
  const headers = values[0].map(String);
  for (const field of ["net_AvgR", "net_TotalR", "net_PF", "net_AvgR_improvement_vs_baseline", "difference_selected_minus_excluded"]) {
    if (headers.includes(field) && values.length > 1) {
      const column = fieldIndex(values, field);
      sheet.getRangeByIndexes(1, column, values.length - 1, 1).conditionalFormats.add("colorScale", {
        colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"],
      });
    }
  }
  for (const field of ["promising", "FDR_significant_0_05", "survives_time_stability", "survives_outlier_removal", "broad_plateau"]) {
    if (headers.includes(field) && values.length > 1) {
      const column = fieldIndex(values, field);
      sheet.getRangeByIndexes(1, column, values.length - 1, 1).conditionalFormats.add("containsText", {
        text: "TRUE",
        format: { fill: "#D4EDDA", font: { color: "#176B3A", bold: true } },
      });
    }
  }
  return sheet;
}

const summary = workbook.worksheets.add("Summary");
summary.showGridLines = false;
await addCsvSheet("Baseline", "baseline_reproduction.csv");
await addCsvSheet("Candidates", "candidate_summary.csv");
await addCsvSheet("H1 Grid", "h1_grid.csv", { fontSize: 7 });
await addCsvSheet("H2 Grid", "h2_grid.csv", { fontSize: 7 });
await addCsvSheet("H3 Matrix", "h3_volatility_session.csv", { fontSize: 7 });
await addCsvSheet("Stability", "stability_results.csv", { fontSize: 7 });
await addCsvSheet("Outliers", "outlier_results.csv", { fontSize: 7 });
await addCsvSheet("FDR", "fdr_results.csv", { fontSize: 7 });

const baseline = datasets.get("Baseline");
const candidates = datasets.get("Candidates");

summary.getRange("A1:N2").merge();
summary.getRange("A1").values = [["Focused Hypothesis Testing — Retest-Gated Entry Quality"]];
summary.getRange("A1:N2").format = {
  fill: "#102A43",
  font: { name: "Aptos Display", size: 19, bold: true, color: "#FFFFFF" },
  verticalAlignment: "center",
};
summary.getRange("A3:N3").merge();
summary.getRange("A3").values = [["Development data only · 2024-01-01 through 2026-06-26 CT · 93 preregistered cells · $14.50/trade · No new downloads · No Pine changes"]];
summary.getRange("A3:N3").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 10, italic: true, color: "#334E68" }, rowHeight: 25 };

summary.getRange("A5:C5").values = [["Baseline metric", "42-trade reference", "Larger development"]];
const baselineRows = [
  ["N", "N", "0"],
  ["Wins", "net_wins", "0"],
  ["Losses", "net_losses", "0"],
  ["Win rate", "net_WR_pct", '0.00"%"'],
  ["Net AvgR", "net_AvgR", "0.00000"],
  ["Net TotalR", "net_TotalR", "0.00000"],
  ["Net PF", "net_PF", "0.00000"],
  ["Net Max DD (R)", "net_MaxDD_R", "0.00000"],
];
summary.getRange("A6:A13").values = baselineRows.map((row) => [row[0]]);
for (let index = 0; index < baselineRows.length; index += 1) {
  const row = 6 + index;
  const [, field, numberFormat] = baselineRows[index];
  summary.getRange(`B${row}`).formulas = [[sourceFormula("Baseline", baseline, 1, field)]];
  summary.getRange(`C${row}`).formulas = [[sourceFormula("Baseline", baseline, 2, field)]];
  summary.getRange(`B${row}:C${row}`).format.numberFormat = numberFormat;
  summary.getRange(`B${row}:C${row}`).format.font = { name: "Aptos", size: 10, color: "#008000" };
}

summary.getRange("E5:N5").merge();
summary.getRange("E5").values = [["Decision"]];
summary.getRange("E6:F12").values = [
  ["Baseline reproduction", "PASS"],
  ["Best individual hypothesis", "NONE"],
  ["Robust plateau", "NO"],
  ["FDR survivors", 0],
  ["Combined rule tested", "NO"],
  ["Evidence", "WEAK"],
  ["Action", "NO QUALITY FILTER SHOULD BE ADDED YET"],
];
summary.getRange("G6:N12").merge();
summary.getRange("G6").values = [["H2 showed the strongest isolated observation at retest range ≥1.00 ATR and reclaim ≥0.30 ATR, but it failed neighboring-cell, time-stability, outlier-removal, and FDR requirements. H1 remained negative after costs. H3 High × Premarket was positive but retained only 19.7%, depended on one year, and failed outlier/FDR checks."]];
summary.getRange("G6:N12").format = { fill: "#FFF7D6", wrapText: true, verticalAlignment: "top", font: { name: "Aptos", size: 10, color: "#5C4813" } };

summary.getRange("A16:N16").merge();
summary.getRange("A16").values = [["Strongest adequately supported observations — descriptive only, not selected rules"]];
summary.getRange("A17:N17").values = [["Hypothesis", "Cell", "N", "Retention %", "Gross AvgR", "Net AvgR", "Gross TotalR", "Net TotalR", "Gross PF", "Net PF", "Net MaxDD", "Plateau", "Time stable", "FDR q"]];
for (let index = 0; index < 3; index += 1) {
  const row = 18 + index;
  const sourceRow = index + 1;
  const mappings = [
    ["A", "hypothesis"], ["B", "cell_id"], ["C", "N"], ["D", "trade_retention_pct"],
    ["E", "gross_AvgR"], ["F", "net_AvgR"], ["G", "gross_TotalR"], ["H", "net_TotalR"],
    ["I", "gross_PF"], ["J", "net_PF"], ["K", "net_MaxDD_R"], ["L", "broad_plateau"],
    ["M", "survives_time_stability"], ["N", "BH_FDR_q"],
  ];
  for (const [column, field] of mappings) summary.getRange(`${column}${row}`).formulas = [[sourceFormula("Candidates", candidates, sourceRow, field)]];
}
summary.getRange("C18:C20").format.numberFormat = "0";
summary.getRange("D18:D20").format.numberFormat = '0.0"%"';
summary.getRange("E18:K20").format.numberFormat = "0.0000";
summary.getRange("N18:N20").format.numberFormat = "0.0000";
summary.getRange("F18:F20").conditionalFormats.add("colorScale", { colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"] });
summary.getRange("J18:J20").conditionalFormats.add("colorScale", { colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"] });

for (const address of ["A5:C5", "E5:N5", "A16:N16"]) {
  summary.getRange(address).format = { fill: "#17324D", font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" }, rowHeight: 28, verticalAlignment: "center" };
}
summary.getRange("A17:N17").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 9, bold: true, color: "#334E68" }, rowHeight: 36, wrapText: true, verticalAlignment: "center" };
summary.getRange("A6:C13").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 22, font: { name: "Aptos", size: 10, color: "#1F2937" } };
summary.getRange("E6:F12").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 31, wrapText: true, verticalAlignment: "center", font: { name: "Aptos", size: 10, color: "#1F2937" } };
summary.getRange("F6:F12").format.font = { name: "Aptos", size: 10, bold: true, color: "#B42318" };
summary.getRange("A18:N20").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 25, font: { name: "Aptos", size: 9, color: "#1F2937" } };
summary.getRange("A1:A22").format.columnWidth = 22;
summary.getRange("B1:B22").format.columnWidth = 28;
summary.getRange("C1:C22").format.columnWidth = 18;
summary.getRange("D1:D22").format.columnWidth = 14;
summary.getRange("E1:N22").format.columnWidth = 15;
summary.getRange("G1:G22").format.columnWidth = 18;
summary.freezePanes.freezeRows(3);

const methodology = workbook.worksheets.add("Methodology");
methodology.showGridLines = false;
methodology.getRange("A1:H2").merge();
methodology.getRange("A1").values = [["Preregistered design, feature timing, and decision gates"]];
methodology.getRange("A1:H2").format = { fill: "#102A43", font: { name: "Aptos Display", size: 18, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" };
methodology.getRange("A4:B18").values = [
  ["Data rule", "Only already-used Databento history. 2024-01-01 through 2026-06-26 is classified as development data. No new download or unseen/OOS access."],
  ["Reference guard", "The exact 42-trade baseline had to reproduce before any grid ran: N 42, W 17, L 25, net AvgR -0.00845527, TotalR -0.35512146, PF 0.98369324, MaxDD 8.37128129R."],
  ["Frozen model", "The existing Confirm/retest-gated sequence, entries, exits, stops, targets, score, HTF rules, sessions, cooldown, anti-chase, and costs were unchanged."],
  ["H1", "36 cells: BOS close distance beyond stored broken structure / BOS ATR at thresholds 0.00–0.50, crossed with BOS volume / mean prior 20 completed bars at 0.75–2.00."],
  ["H2", "36 cells: accepted retest range / retest ATR at 0.25–1.50, crossed with direction-signed confirmation close beyond stored BOS / confirmation ATR at 0.00–0.30."],
  ["H3", "21 cells: confirmation ATR percentile versus the prior 100 completed bars; LOW ≤0.33, MID >0.33 and <0.67, HIGH ≥0.67, crossed with the seven frozen sessions."],
  ["Causality", "BOS features are known at BOS close. Retest range is known at accepted retest close. Reclaim and ATR-state features are known at confirmation/entry close. Current bars are excluded from trailing reference means."],
  ["Costs", "$14.50 round turn converted to R using each trade's frozen risk distance and $20 per NQ point."],
  ["Sample classes", "N<30 insufficient; 30–49 very weak; 50–99 exploratory; N≥100 better supported."],
  ["Stability", "Requires at least two years, ≥2/3 positive years, both chronological halves positive, and at least half of represented quarters positive; H1/H2 also require a broad orthogonal-neighbor plateau."],
  ["Outliers", "Every cost-positive cell with N≥30 was recomputed after removing the best trade, top three winners, and top 1% winners."],
  ["FDR", "One-sided Welch tests compare selected versus excluded net-R distributions. Benjamini-Hochberg correction is applied jointly across all 76 testable cells out of 93 predefined cells."],
  ["Promotion gate", "Positive net AvgR, net PF>1, ≥0.05R AvgR improvement, ≥20% retention, N≥100, time stability, outlier survival, FDR q<0.05, and a broad H1/H2 plateau where applicable."],
  ["Combination rule", "No individual hypothesis passed every gate, so no two-hypothesis combination was tested."],
  ["Conclusion", "NO QUALITY FILTER SHOULD BE ADDED YET."],
];
methodology.getRange("A4:A18").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 10, bold: true, color: "#334E68" }, verticalAlignment: "top" };
methodology.getRange("B4:B18").format = { font: { name: "Aptos", size: 10, color: "#1F2937" }, wrapText: true, verticalAlignment: "top" };
methodology.getRange("A4:B18").format.rowHeight = 48;
methodology.getRange("A1:A18").format.columnWidth = 24;
methodology.getRange("B1:B18").format.columnWidth = 110;
methodology.freezePanes.freezeRows(2);

const checks = workbook.worksheets.add("Checks");
checks.showGridLines = false;
checks.getRange("A1:F2").merge();
checks.getRange("A1").values = [["Reproducibility and scope checks"]];
checks.getRange("A1:F2").format = { fill: "#102A43", font: { name: "Aptos Display", size: 18, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" };
checks.getRange("A4:E4").values = [["Check", "Actual", "Expected", "Tolerance", "Status"]];
const checkRows = [
  ["Reference N", sourceFormula("Baseline", baseline, 1, "N"), 42, 0, "=IF(ABS(B5-C5)<=D5,\"PASS\",\"FAIL\")"],
  ["Reference wins", sourceFormula("Baseline", baseline, 1, "net_wins"), 17, 0, "=IF(ABS(B6-C6)<=D6,\"PASS\",\"FAIL\")"],
  ["Reference losses", sourceFormula("Baseline", baseline, 1, "net_losses"), 25, 0, "=IF(ABS(B7-C7)<=D7,\"PASS\",\"FAIL\")"],
  ["Reference net TotalR", sourceFormula("Baseline", baseline, 1, "net_TotalR"), -0.3551214629203526, 1e-9, "=IF(ABS(B8-C8)<=D8,\"PASS\",\"FAIL\")"],
  ["Reference net PF", sourceFormula("Baseline", baseline, 1, "net_PF"), 0.9836932374533185, 1e-9, "=IF(ABS(B9-C9)<=D9,\"PASS\",\"FAIL\")"],
  ["Reference net MaxDD", sourceFormula("Baseline", baseline, 1, "net_MaxDD_R"), 8.371281287974549, 1e-9, "=IF(ABS(B10-C10)<=D10,\"PASS\",\"FAIL\")"],
  ["H1 predefined cells", "=COUNTA('H1 Grid'!A2:A37)", 36, 0, "=IF(B11=C11,\"PASS\",\"FAIL\")"],
  ["H2 predefined cells", "=COUNTA('H2 Grid'!A2:A37)", 36, 0, "=IF(B12=C12,\"PASS\",\"FAIL\")"],
  ["H3 predefined cells", "=COUNTA('H3 Matrix'!A2:A22)", 21, 0, "=IF(B13=C13,\"PASS\",\"FAIL\")"],
  ["Total predefined cells", "=B11+B12+B13", 93, 0, "=IF(B14=C14,\"PASS\",\"FAIL\")"],
  ["FDR survivors", "=COUNTIF(FDR!N2:N94,TRUE)", 0, 0, "=IF(B15=C15,\"PASS\",\"FAIL\")"],
];
checks.getRange("A5:A15").values = checkRows.map((row) => [row[0]]);
checks.getRange("C5:D15").values = checkRows.map((row) => [row[2], row[3]]);
checks.getRange("B5:B15").formulas = checkRows.map((row) => [row[1]]);
checks.getRange("E5:E15").formulas = checkRows.map((row) => [row[4]]);
checks.getRange("A4:E4").format = { fill: "#17324D", font: { name: "Aptos", size: 10, bold: true, color: "#FFFFFF" }, rowHeight: 27 };
checks.getRange("A5:E15").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 24, font: { name: "Aptos", size: 10, color: "#1F2937" } };
checks.getRange("B5:D15").format.numberFormat = "0.000000000";
checks.getRange("E5:E15").conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#D4EDDA", font: { color: "#176B3A", bold: true } } });
checks.getRange("E5:E15").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#F8D7DA", font: { color: "#B42318", bold: true } } });
checks.getRange("A1:A15").format.columnWidth = 30;
checks.getRange("B1:D15").format.columnWidth = 18;
checks.getRange("E1:E15").format.columnWidth = 16;
checks.freezePanes.freezeRows(4);

const inspect = await workbook.inspect({ kind: "workbook,sheet,formula", maxChars: 20000, tableMaxRows: 8, tableMaxCols: 14 });
const formulaErrors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, maxChars: 6000 });
const inspectText = `${inspect.ndjson || inspect}\n${formulaErrors.ndjson || formulaErrors}\n`;
await fs.writeFile(inspectPath, inspectText);
console.log(inspectText);

const summaryPreview = await workbook.render({ sheetName: "Summary", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await summaryPreview.arrayBuffer()));
for (const [sheetName, range] of Object.entries({
  Baseline: "A1:W3",
  Candidates: "A1:AO4",
  "H1 Grid": "A1:X37",
  "H2 Grid": "A1:Z37",
  "H3 Matrix": "A1:X22",
  Stability: "A1:Y30",
  Outliers: "A1:Y21",
  FDR: "A1:P94",
  Methodology: "A1:B18",
  Checks: "A1:E15",
})) {
  const rendered = await workbook.render({ sheetName, range, scale: 0.6, format: "png" });
  await fs.writeFile(path.join(qaDir, `${sheetName.toLowerCase().replaceAll(" ", "_")}.png`), new Uint8Array(await rendered.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, previewPath, inspectPath, qaDir }));
