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
const inputDir = path.join(projectRoot, "phase16/results/winner_loser_entry_quality");
const outputDir = path.join(projectRoot, "outputs/winner_loser_entry_quality");
const qaDir = "/private/tmp/winner_loser_entry_quality_qa";
const outputPath = path.join(outputDir, "WINNER_LOSER_ENTRY_QUALITY_FORENSICS.xlsx");
const previewPath = path.join(outputDir, "WINNER_LOSER_ENTRY_QUALITY_SUMMARY.png");
const inspectPath = path.join(outputDir, "WINNER_LOSER_ENTRY_QUALITY_FORENSICS.xlsx.inspect.ndjson");
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

function numericColumnFormat(headerName) {
  const name = headerName.toLowerCase();
  if (name === "n" || name.endsWith("_n") || name.includes("count") || name.includes("bars") || name.includes("wins") || name.includes("losses")) return "0";
  if (name.includes("pct") || name.includes("rate")) return "0.0";
  if (name === "pf" || name.includes("profit_factor")) return "0.000";
  if (name.includes("timestamp")) return "yyyy-mm-dd hh:mm";
  return "0.000";
}

async function addCsvSheet(name, fileName, options = {}) {
  const text = await fs.readFile(path.join(inputDir, fileName), "utf8");
  const imported = await Workbook.fromCSV(text, { sheetName: name });
  const source = imported.worksheets.getItemAt(0);
  const values = source.getUsedRange(true).values;
  datasets.set(name, values);
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  if (!values.length || !values[0].length) return sheet;
  const range = sheet.getRangeByIndexes(0, 0, values.length, values[0].length);
  range.values = values;
  range.format.font = { name: "Aptos", size: options.fontSize || 8, color: "#1F2937" };
  range.format.rowHeight = 18;
  const header = sheet.getRangeByIndexes(0, 0, 1, values[0].length);
  header.format = {
    fill: "#17324D",
    font: { name: "Aptos Display", size: 9, bold: true, color: "#FFFFFF" },
    rowHeight: 44,
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.freezePanes.freezeRows(1);
  for (let column = 0; column < values[0].length; column += 1) {
    const headerName = String(values[0][column] || "");
    const lower = headerName.toLowerCase();
    let width = Math.min(23, Math.max(10, headerName.length + 2));
    if (lower.includes("timestamp")) width = 24;
    if (lower.includes("feature_label") || lower.includes("characteristic") || lower.includes("interaction")) width = 34;
    if (lower.includes("definition") || lower.includes("condition_") || lower.includes("warning")) width = 48;
    if (lower.includes("relationship") || lower.includes("dependence")) width = 30;
    sheet.getRangeByIndexes(0, column, values.length, 1).format.columnWidth = width;
    if (values.length > 1 && !lower.includes("timestamp")) {
      sheet.getRangeByIndexes(1, column, values.length - 1, 1).format.numberFormat = numericColumnFormat(headerName);
    }
  }
  const headers = values[0].map((value) => String(value));
  for (const field of ["net_R", "AvgR", "TotalR", "standardized_effect_Cohen_d", "absolute_effect", "Both_minus_Neither_AvgR"]) {
    if (headers.includes(field) && values.length > 1) {
      const column = fieldIndex(values, field);
      sheet.getRangeByIndexes(1, column, values.length - 1, 1).conditionalFormats.add("colorScale", {
        colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"],
      });
    }
  }
  for (const field of ["PF", "profit_factor"]) {
    if (headers.includes(field) && values.length > 1) {
      const column = fieldIndex(values, field);
      sheet.getRangeByIndexes(1, column, values.length - 1, 1).conditionalFormats.add("colorScale", {
        colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"],
      });
    }
  }
  return sheet;
}

const summary = workbook.worksheets.add("Summary");
summary.showGridLines = false;

await addCsvSheet("Current Metrics", "current_summary.csv");
await addCsvSheet("Trade Features", "trade_level_features.csv", { fontSize: 7 });
await addCsvSheet("Continuous", "winner_loser_comparison.csv");
await addCsvSheet("Categorical", "categorical_comparison.csv");
await addCsvSheet("Distributions", "distribution_analysis.csv");
await addCsvSheet("Dist Summary", "distribution_summary.csv");
await addCsvSheet("Interactions", "interaction_analysis.csv");
await addCsvSheet("Characteristics", "winner_loser_characteristics.csv");

const currentValues = datasets.get("Current Metrics");
const comparisonValues = datasets.get("Continuous");
const interactionValues = datasets.get("Interactions");
const characteristicValues = datasets.get("Characteristics");

summary.getRange("A1:P2").merge();
summary.getRange("A1").values = [["Winner vs Loser Entry-Quality Forensics"]];
summary.getRange("A1:P2").format = {
  fill: "#102A43",
  font: { name: "Aptos Display", size: 20, bold: true, color: "#FFFFFF" },
  verticalAlignment: "center",
};
summary.getRange("A3:P3").merge();
summary.getRange("A3").values = [[
  "Development window only · 2026-06-29 through 2026-08-18 CT · 10,164 bars · 42 frozen Confirm trades · $14.50 round-turn cost · No unseen OOS access",
]];
summary.getRange("A3:P3").format = {
  fill: "#D9EAF7",
  font: { name: "Aptos", size: 10, italic: true, color: "#334E68" },
  rowHeight: 25,
};

summary.getRange("A5:B5").values = [["Current net metric", "Value"]];
const metricRows = [
  ["Trades", "N", "0"],
  ["Wins", "wins", "0"],
  ["Losses", "losses", "0"],
  ["Win rate", "win_pct", "0.00\"%\""],
  ["Average R", "avg_R", "0.00000"],
  ["Total R", "total_R", "0.00000"],
  ["Profit factor", "profit_factor", "0.00000"],
  ["Max drawdown R", "max_drawdown_R", "0.00000"],
];
summary.getRange("A6:A13").values = metricRows.map((row) => [row[0]]);
for (let index = 0; index < metricRows.length; index += 1) {
  const [, field, format] = metricRows[index];
  const row = 6 + index;
  summary.getRange(`B${row}`).formulas = [[sourceFormula("Current Metrics", currentValues, 1, field)]];
  summary.getRange(`B${row}`).format.numberFormat = format;
}

summary.getRange("D5:H5").merge();
summary.getRange("D5").values = [["Conclusion and guardrails"]];
summary.getRange("D6:E10").values = [
  ["Evidence grade", "WEAK"],
  ["Monotonic bucket studies", "0 of 7"],
  ["Pine / frozen baseline changed", "NO"],
  ["Unseen OOS accessed", "NO"],
  ["Recommended action", "Preregister hypotheses; do not filter yet"],
];
summary.getRange("F6:H10").merge();
summary.getRange("F6").values = [[
  "Observed separation exists, but the sample is only 42 development-window trades. Entry ATR was the strongest durable single feature. The clearest joint pattern was stronger BOS displacement plus higher causal relative volume. Every requested distribution study was non-monotonic, so no cutoff is proposed.",
]];
summary.getRange("F6:H10").format = { fill: "#FFF7D6", wrapText: true, verticalAlignment: "top", font: { name: "Aptos", size: 10, color: "#5C4813" } };

for (const address of ["A5:B5", "D5:H5", "J5:K5", "A16:H16", "J16:P16", "A30:P30"]) {
  summary.getRange(address).format = {
    fill: "#17324D",
    font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" },
    rowHeight: 27,
    verticalAlignment: "center",
  };
}
summary.getRange("A6:B13").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 22, font: { name: "Aptos", size: 10, color: "#1F2937" } };
summary.getRange("D6:E10").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 34, wrapText: true, verticalAlignment: "center", font: { name: "Aptos", size: 10, color: "#1F2937" } };
summary.getRange("E6:E10").format.font = { name: "Aptos", size: 10, bold: true, color: "#B42318" };

summary.getRange("J5:K5").values = [["Top feature", "Cohen d"]];
for (let index = 0; index < 10; index += 1) {
  const row = 6 + index;
  summary.getRange(`J${row}`).formulas = [[sourceFormula("Continuous", comparisonValues, index + 1, "feature_label")]];
  summary.getRange(`K${row}`).formulas = [[sourceFormula("Continuous", comparisonValues, index + 1, "standardized_effect_Cohen_d")]];
  summary.getRange(`K${row}`).format.numberFormat = "0.000";
}
summary.getRange("J6:K15").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 20, font: { name: "Aptos", size: 9, color: "#1F2937" } };
summary.getRange("K6:K15").conditionalFormats.add("colorScale", { colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"] });
const chart = summary.charts.add("bar", summary.getRange("J5:K15"));
chart.title = "Top 10 standardized winner/loser effects";
chart.titleTextStyle.fontSize = 11;
chart.hasLegend = false;
chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
chart.yAxis = { numberFormatCode: "0.0" };
chart.setPosition("M5", "P15");

summary.getRange("A16:H16").merge();
summary.getRange("A16").values = [["Top 10 continuous pre-entry separations"]];
summary.getRange("A17:H17").values = [["Rank", "Feature", "Relationship", "Cohen d", "Winner median", "Loser median", "LOO stability", "Outlier check"]];
summary.getRange("A17:H17").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 9, bold: true, color: "#334E68" }, rowHeight: 31, wrapText: true };
for (let index = 0; index < 10; index += 1) {
  const row = 18 + index;
  summary.getRange(`A${row}`).values = [[index + 1]];
  for (const [column, field] of [["B", "feature_label"], ["C", "relationship"], ["D", "standardized_effect_Cohen_d"], ["E", "winner_median"], ["F", "loser_median"], ["G", "LOO_stability"], ["H", "outlier_dependence"]]) {
    summary.getRange(`${column}${row}`).formulas = [[sourceFormula("Continuous", comparisonValues, index + 1, field)]];
  }
  summary.getRange(`D${row}:F${row}`).format.numberFormat = "0.000";
}
summary.getRange("A18:H27").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 25, wrapText: true, verticalAlignment: "center", font: { name: "Aptos", size: 8, color: "#1F2937" } };
summary.getRange("D18:D27").conditionalFormats.add("colorScale", { colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"] });

summary.getRange("J16:P16").merge();
summary.getRange("J16").values = [["Best apparent logical interactions (Both cell)"]];
summary.getRange("J17:P17").values = [["Interaction", "N", "WR %", "AvgR", "TotalR", "PF", "AvgR vs Neither"]];
summary.getRange("J17:P17").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 9, bold: true, color: "#334E68" }, rowHeight: 31, wrapText: true };
const bothRows = interactionValues
  .map((row, index) => ({ row, index }))
  .filter(({ row }) => String(row[fieldIndex(interactionValues, "cell")]) === "Both" && Number(row[fieldIndex(interactionValues, "N")]) >= 3)
  .sort((a, b) => Number(b.row[fieldIndex(interactionValues, "AvgR")]) - Number(a.row[fieldIndex(interactionValues, "AvgR")]))
  .slice(0, 5);
for (let index = 0; index < bothRows.length; index += 1) {
  const sourceRow = bothRows[index].index;
  const row = 18 + index;
  for (const [column, field] of [["J", "interaction"], ["K", "N"], ["L", "win_rate_pct"], ["M", "AvgR"], ["N", "TotalR"], ["O", "PF"], ["P", "Both_minus_Neither_AvgR"]]) {
    summary.getRange(`${column}${row}`).formulas = [[sourceFormula("Interactions", interactionValues, sourceRow, field)]];
  }
  summary.getRange(`K${row}`).format.numberFormat = "0";
  summary.getRange(`L${row}`).format.numberFormat = "0.0";
  summary.getRange(`M${row}:P${row}`).format.numberFormat = "0.000";
}
summary.getRange("J18:P22").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 29, wrapText: true, verticalAlignment: "center", font: { name: "Aptos", size: 8, color: "#1F2937" } };
summary.getRange("M18:P22").conditionalFormats.add("colorScale", { colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"] });

summary.getRange("A30:P30").merge();
summary.getRange("A30").values = [["Preregistered hypotheses for a later untouched test"]];
summary.getRange("A31:P36").merge();
summary.getRange("A31").values = [[
  "H1: jointly stronger causal BOS displacement and relative volume.  H2: stronger accepted-retest body/range expansion and a close farther back onto the intended side of stored BOS.  H3: higher already-known volatility together with the frozen core session. These are hypotheses only; no profit-selected cutoff is recommended.",
]];
summary.getRange("A31:P36").format = { fill: "#EEF5F9", wrapText: true, verticalAlignment: "top", font: { name: "Aptos", size: 11, color: "#334E68" } };

summary.getRange("A1:A36").format.columnWidth = 9;
summary.getRange("B1:B36").format.columnWidth = 29;
summary.getRange("C1:C36").format.columnWidth = 28;
summary.getRange("D1:D36").format.columnWidth = 25;
summary.getRange("E1:E36").format.columnWidth = 27;
summary.getRange("F1:H36").format.columnWidth = 18;
summary.getRange("I1:I36").format.columnWidth = 3;
summary.getRange("J1:J36").format.columnWidth = 32;
summary.getRange("K1:P36").format.columnWidth = 12;
summary.freezePanes.freezeRows(3);

const methodology = workbook.worksheets.add("Methodology");
methodology.showGridLines = false;
methodology.getRange("A1:H2").merge();
methodology.getRange("A1").values = [["Methodology, feature definitions, and leakage controls"]];
methodology.getRange("A1:H2").format = { fill: "#102A43", font: { name: "Aptos Display", size: 18, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" };
methodology.getRange("A4:B20").values = [
  ["Scope", "Development window only: 2026-06-29 through 2026-08-18 America/Chicago. Warm-up history begins 2026-05-31 19:00 CT. Unseen OOS files were not accessed."],
  ["Baseline", "Exactly 42 frozen Confirm trades: 17 wins, 25 losses, AvgR -0.00846, TotalR -0.35512, PF 0.98369, MaxDD 8.37128R after the existing $14.50 cost assumption."],
  ["Frozen logic", "Phase 3 structure, Phase 4 liquidity, Phase 5 scoring/Variant-C, funnel, entries, stops, targets, sessions, HTF rules, cooldown, anti-chase, and Pine remained unchanged."],
  ["Timing", "Setup <= BOS < Retest < Confirmation = Entry is asserted trade by trade. All features use data known by the entry-bar close."],
  ["Score components", "Attributed from the frozen SetupEngine state after each exact canonical setup; the five components are asserted to sum to the frozen canonical score."],
  ["BOS displacement", "Direction-signed BOS close change from the prior bar close. Close distance beyond stored structure is reported separately."],
  ["Relative volume", "BOS volume divided by the mean of the prior 20 completed bars. The BOS bar is excluded from the denominator."],
  ["Retest penetration", "Measured causally from BOS+1 through the accepted retest. Touch count includes the accepted touch."],
  ["ATR percentile", "Known entry-bar ATR compared with up to 100 completed prior bars; current entry bar is excluded from the reference distribution."],
  ["Session extremes", "Cumulative CME-session high and low through the entry bar only."],
  ["Outcome labels", "Win/loss, gross/net R, MFE, MAE, exit timestamp, and exit reason are labels only and are excluded from the feature registry."],
  ["Effect size", "Cohen d is descriptive, not a significance test."],
  ["LOO stability", "STABLE: all leave-one-out signs agree and minimum absolute effect >=75% of full. PARTIALLY STABLE: >=90% sign agreement and >=50% effect retention."],
  ["Outlier checks", "Remove best trade, worst trade, top two winners, and top two losers separately."],
  ["Buckets", "Quantiles and simple fixed delay/score bands are descriptive only. Every requested bucket study was non-monotonic."],
  ["Interactions", "Exactly 10 economically justified pairs using median or existing structural splits; no unrestricted combination search."],
  ["Feature dependence", "Setup and BOS share the same bar in 41 of 42 trades, so most setup/BOS candle-shape fields are duplicates rather than independent evidence. Raw upper/lower wick effects also require direction-aware interpretation."],
];
methodology.getRange("A4:A20").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 10, bold: true, color: "#334E68" }, verticalAlignment: "top" };
methodology.getRange("B4:B20").format = { font: { name: "Aptos", size: 10, color: "#1F2937" }, wrapText: true, verticalAlignment: "top" };
methodology.getRange("A4:B20").format.rowHeight = 44;
methodology.getRange("A1:A20").format.columnWidth = 24;
methodology.getRange("B1:B20").format.columnWidth = 105;
methodology.freezePanes.freezeRows(2);

const inspect = await workbook.inspect({
  kind: "workbook,sheet,formula,drawing",
  maxChars: 18000,
  tableMaxRows: 8,
  tableMaxCols: 12,
});
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  maxChars: 6000,
});
const inspectText = `${inspect.ndjson || inspect}\n${formulaErrors.ndjson || formulaErrors}\n`;
await fs.writeFile(inspectPath, inspectText);
console.log(inspectText);

const preview = await workbook.render({ sheetName: "Summary", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
for (const [sheetName, range] of Object.entries({
  "Current Metrics": "A1:Q3",
  "Trade Features": "A1:BX43",
  "Continuous": "A1:V53",
  "Categorical": "A1:I47",
  "Distributions": "A1:O31",
  "Dist Summary": "A1:G8",
  "Interactions": "A1:N41",
  "Characteristics": "A1:N21",
  "Methodology": "A1:B20",
})) {
  const rendered = await workbook.render({ sheetName, range, scale: 0.7, format: "png" });
  await fs.writeFile(path.join(qaDir, `${sheetName.toLowerCase().replaceAll(" ", "_")}.png`), new Uint8Array(await rendered.arrayBuffer()));
}

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(JSON.stringify({ outputPath, previewPath, inspectPath, qaDir }));
