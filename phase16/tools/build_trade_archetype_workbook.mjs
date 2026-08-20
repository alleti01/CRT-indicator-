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
const inputDir = path.join(projectRoot, "phase16/results/trade_archetype_decomposition");
const outputDir = path.join(projectRoot, "outputs/trade_archetype_decomposition");
const outputPath = path.join(outputDir, "TRADE_ARCHETYPE_DECOMPOSITION.xlsx");
const previewPath = path.join(outputDir, "TRADE_ARCHETYPE_DECOMPOSITION_SUMMARY.png");
const inspectPath = path.join(outputDir, "TRADE_ARCHETYPE_DECOMPOSITION.xlsx.inspect.ndjson");
const qaDir = "/private/tmp/trade_archetype_decomposition_qa";
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(qaDir, { recursive: true });

for (const fileName of [
  "TRADE_ARCHETYPE_DECOMPOSITION.md",
  "trade_archetype_features.csv",
  "archetype_summary.csv",
  "archetype_year_stability.csv",
  "archetype_complements.csv",
  "archetype_cumulative_curves.csv",
  "baseline_trade_reconciliation.csv",
  "baseline_summary.csv",
  "analysis_manifest.json",
]) {
  await fs.copyFile(path.join(inputDir, fileName), path.join(outputDir, fileName));
}

const manifest = JSON.parse(await fs.readFile(path.join(inputDir, "analysis_manifest.json"), "utf8"));
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
  if (name === "n" || name.endsWith("_n") || name.includes("wins") || name.includes("losses") || name.includes("flats") || name.includes("count") || name.includes("bars")) return "0";
  if (name.includes("pct") || name.includes("rate")) return '0.00"%"';
  if (name.includes("timestamp")) return "yyyy-mm-dd hh:mm";
  if (name.includes("pf") || name.includes("fdr") || name.includes("p_two")) return "0.0000";
  if (name.includes("avgr") || name.includes("totalr") || name.includes("drawdown") || name.includes("median") || name.includes("atr") || name.includes("mfe") || name.includes("mae") || name.endsWith("_r")) return "0.0000";
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
    rowHeight: 46,
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.freezePanes.freezeRows(1);
  for (let column = 0; column < values[0].length; column += 1) {
    const field = String(values[0][column] || "");
    const lower = field.toLowerCase();
    let width = Math.min(25, Math.max(10, field.length + 2));
    if (lower.includes("timestamp")) width = 23;
    if (lower.includes("definition") || lower.includes("family_id")) width = 45;
    if (lower.includes("json")) width = 34;
    sheet.getRangeByIndexes(0, column, values.length, 1).format.columnWidth = width;
    if (values.length > 1) sheet.getRangeByIndexes(1, column, values.length - 1, 1).format.numberFormat = formatFor(field);
  }
  const headers = values[0].map(String);
  for (const field of ["net_AvgR", "net_TotalR", "net_PF", "family_net_AvgR", "family_net_TotalR", "family_net_PF", "net_R"]) {
    if (headers.includes(field) && values.length > 1) {
      const column = fieldIndex(values, field);
      sheet.getRangeByIndexes(1, column, values.length - 1, 1).conditionalFormats.add("colorScale", {
        colors: ["#F8D7DA", "#FFF3CD", "#D4EDDA"],
      });
    }
  }
  for (const field of ["FDR_significant_0_05", "robust_positive_family", "robust_negative_family", "mismatches"]) {
    if (headers.includes(field) && values.length > 1) {
      const column = fieldIndex(values, field);
      sheet.getRangeByIndexes(1, column, values.length - 1, 1).conditionalFormats.add("containsText", {
        text: field === "mismatches" ? "0" : "TRUE",
        format: { fill: "#D4EDDA", font: { color: "#176B3A", bold: true } },
      });
    }
  }
  return sheet;
}

const executive = workbook.worksheets.add("Executive");
executive.showGridLines = false;
await addCsvSheet("Trade Features", "trade_archetype_features.csv", { fontSize: 7 });
await addCsvSheet("Factor Summary", "archetype_summary.csv", { fontSize: 7 });
await addCsvSheet("Family Tests", "archetype_complements.csv", { fontSize: 7 });
await addCsvSheet("Stability", "archetype_year_stability.csv", { fontSize: 7 });
await addCsvSheet("Cumulative", "archetype_cumulative_curves.csv", { fontSize: 7 });
await addCsvSheet("Baseline", "baseline_summary.csv");
await addCsvSheet("Reconciliation", "baseline_trade_reconciliation.csv");

const baseline = datasets.get("Baseline");
const summaries = datasets.get("Factor Summary");
const families = datasets.get("Family Tests");
const stability = datasets.get("Stability");
const cumulative = datasets.get("Cumulative");
const tradeFeatures = datasets.get("Trade Features");

function rowWhere(values, predicate) {
  const headers = values[0].map(String);
  for (let row = 1; row < values.length; row += 1) {
    const record = Object.fromEntries(headers.map((header, index) => [header, values[row][index]]));
    if (predicate(record)) return row;
  }
  throw new Error("Required source row not found");
}

function rowsWhere(values, predicate) {
  const headers = values[0].map(String);
  const matches = [];
  for (let row = 1; row < values.length; row += 1) {
    const record = Object.fromEntries(headers.map((header, index) => [header, values[row][index]]));
    if (predicate(record)) matches.push({ row, record });
  }
  return matches;
}

const baselineRow = 1;
const longRow = rowWhere(summaries, (r) => r.analysis_level === "Single factor" && r.dimension === "Direction" && r.category === "Long" && r.direction_slice === "All");
const shortRow = rowWhere(summaries, (r) => r.analysis_level === "Single factor" && r.dimension === "Direction" && r.category === "Short" && r.direction_slice === "All");
const sameBarRow = rowWhere(summaries, (r) => r.analysis_level === "Single factor" && r.dimension === "Setup/BOS timing" && r.category === "Same-bar Setup+BOS" && r.direction_slice === "All");
const delayedRow = rowWhere(summaries, (r) => r.analysis_level === "Single factor" && r.dimension === "Setup/BOS timing" && r.category === "Delayed BOS" && r.direction_slice === "All");
const bestFamilyRow = rowWhere(families, (r) => r.family_id === manifest.best_family_id);
const worstFamilyRow = rowWhere(families, (r) => r.family_id === manifest.worst_family_id);

executive.getRange("A1:N2").merge();
executive.getRange("A1").values = [["Trade Archetype / Setup-Family Decomposition"]];
executive.getRange("A1:N2").format = { fill: "#102A43", font: { name: "Aptos Display", size: 20, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" };
executive.getRange("A3:N3").merge();
executive.getRange("A3").values = [["Development data only · 2024-01-01 through 2026-06-26 CT · 705 verified Confirm trades · $14.50/trade · No Pine or frozen-engine changes"]];
executive.getRange("A3:N3").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 10, italic: true, color: "#334E68" }, rowHeight: 25 };

executive.getRange("A5:C5").values = [["Baseline metric", "Value", "Guard"]];
const baselineMetrics = [
  ["N", "N", 705, "0"],
  ["Wins after cost", "net_wins", 284, "0"],
  ["Losses after cost", "net_losses", 421, "0"],
  ["Win rate", "net_win_rate_pct", 40.283687943262414, '0.00"%"'],
  ["Net Avg R", "net_AvgR", -0.06957314333917415, "0.00000"],
  ["Net Total R", "net_TotalR", -49.04906605411777, "0.00000"],
  ["Net PF", "net_PF", 0.8717849563156026, "0.00000"],
  ["Net Max DD (R)", "net_MaxDD_R", 60.29673416610867, "0.00000"],
];
executive.getRange("A6:A13").values = baselineMetrics.map((row) => [row[0]]);
for (let index = 0; index < baselineMetrics.length; index += 1) {
  const row = 6 + index;
  const [, field, expected, numberFormat] = baselineMetrics[index];
  executive.getRange(`B${row}`).formulas = [[sourceFormula("Baseline", baseline, baselineRow, field)]];
  executive.getRange(`C${row}`).formulas = [[`=IF(ABS(B${row}-${expected})<0.000000001,"PASS","FAIL")`]];
  executive.getRange(`B${row}`).format = { numberFormat, font: { name: "Aptos", size: 10, color: "#008000" } };
}

executive.getRange("E5:N5").merge();
executive.getRange("E5").values = [["Decision"]];
executive.getRange("E6:F13").values = [
  ["Baseline reproduced", "YES"],
  ["705 trades verified", "YES"],
  ["Adequate families", manifest.adequate_N_family_tests],
  ["FDR survivors", manifest.FDR_survivors],
  ["Robust positive", manifest.robust_positive_families],
  ["Robust negative", manifest.robust_negative_families],
  ["Final class", manifest.classification],
  ["Action", "DO NOT FILTER OR OPTIMIZE"],
];
executive.getRange("G6:N13").merge();
executive.getRange("G6").values = [["The least-negative adequate family was Short × Same-bar Setup+BOS × Penetration without same-bar reclaim (N=31), but it was negative after costs, changed sign across years and halves, failed outlier removal, and did not survive FDR. No family is robust enough to alter the strategy."]];
executive.getRange("G6:N13").format = { fill: "#FFF7D6", wrapText: true, verticalAlignment: "top", font: { name: "Aptos", size: 10, color: "#5C4813" } };

executive.getRange("A16:N16").merge();
executive.getRange("A16").values = [["Required headline decomposition — after $14.50 round-turn costs"]];
executive.getRange("A17:G17").values = [["Slice", "N", "Retention %", "Win %", "Avg R", "Total R", "PF"]];
const headlineRows = [
  ["Long", summaries, longRow, "N", "pct_all_trades", "net_win_rate_pct", "net_AvgR", "net_TotalR", "net_PF"],
  ["Short", summaries, shortRow, "N", "pct_all_trades", "net_win_rate_pct", "net_AvgR", "net_TotalR", "net_PF"],
  ["Same-bar Setup+BOS", summaries, sameBarRow, "N", "pct_all_trades", "net_win_rate_pct", "net_AvgR", "net_TotalR", "net_PF"],
  ["Delayed BOS", summaries, delayedRow, "N", "pct_all_trades", "net_win_rate_pct", "net_AvgR", "net_TotalR", "net_PF"],
  ["Least-negative adequate family", families, bestFamilyRow, "family_N", "family_pct_all_trades", "family_net_win_rate_pct", "family_net_AvgR", "family_net_TotalR", "family_net_PF"],
  ["Its complement", families, bestFamilyRow, "complement_N", "complement_pct_all_trades", "complement_net_win_rate_pct", "complement_net_AvgR", "complement_net_TotalR", "complement_net_PF"],
  ["Largest loss contributor", families, worstFamilyRow, "family_N", "family_pct_all_trades", "family_net_win_rate_pct", "family_net_AvgR", "family_net_TotalR", "family_net_PF"],
];
for (let index = 0; index < headlineRows.length; index += 1) {
  const row = 18 + index;
  const [label, values, sourceRow, ...fields] = headlineRows[index];
  executive.getRange(`A${row}`).values = [[label]];
  for (let column = 0; column < fields.length; column += 1) {
    executive.getRangeByIndexes(row - 1, column + 1, 1, 1).formulas = [[sourceFormula(values === summaries ? "Factor Summary" : "Family Tests", values, sourceRow, fields[column])]];
  }
}
executive.getRange("B18:B24").format.numberFormat = "0";
executive.getRange("C18:D24").format.numberFormat = '0.00"%"';
executive.getRange("E18:G24").format.numberFormat = "0.0000";

for (const address of ["A5:C5", "E5:N5", "A16:N16"]) {
  executive.getRange(address).format = { fill: "#17324D", font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" }, rowHeight: 28, verticalAlignment: "center" };
}
executive.getRange("A17:G17").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 9, bold: true, color: "#334E68" }, rowHeight: 32, wrapText: true };
executive.getRange("A6:C13").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 23, font: { name: "Aptos", size: 10, color: "#1F2937" } };
executive.getRange("E6:F13").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 28, wrapText: true, font: { name: "Aptos", size: 10, color: "#1F2937" } };
executive.getRange("F6:F13").format.font = { name: "Aptos", size: 10, bold: true, color: "#B42318" };
executive.getRange("A18:G24").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 23, font: { name: "Aptos", size: 9, color: "#1F2937" } };
executive.getRange("C6:C13").conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#D4EDDA", font: { color: "#176B3A", bold: true } } });
executive.getRange("C6:C13").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#F8D7DA", font: { color: "#B42318", bold: true } } });
executive.getRange("A1:A25").format.columnWidth = 31;
executive.getRange("B1:C25").format.columnWidth = 18;
executive.getRange("D1:D25").format.columnWidth = 14;
executive.getRange("E1:N25").format.columnWidth = 16;
executive.freezePanes.freezeRows(3);

function setupDashboard(sheet, title, subtitle) {
  sheet.showGridLines = false;
  sheet.getRange("A1:P2").merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1:P2").format = { fill: "#102A43", font: { name: "Aptos Display", size: 18, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" };
  sheet.getRange("A3:P3").merge();
  sheet.getRange("A3").values = [[subtitle]];
  sheet.getRange("A3:P3").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 9, italic: true, color: "#334E68" }, rowHeight: 24 };
  sheet.freezePanes.freezeRows(3);
}

function formatHelper(sheet, address) {
  const range = sheet.getRange(address);
  range.format.font = { name: "Aptos", size: 8, color: "#1F2937" };
  range.getRow(0).format = { fill: "#17324D", font: { name: "Aptos", size: 8, bold: true, color: "#FFFFFF" }, rowHeight: 32, wrapText: true };
}

const familyCharts = workbook.worksheets.add("Family Charts");
setupDashboard(familyCharts, "Structural family comparison", "Five adequate-N three-factor families · after costs · descriptive forensic comparison, not a candidate filter");
familyCharts.getRange("A30:K30").values = [["Family", "Net Avg R", "", "Family", "Net Total R", "", "Family", "Net PF", "", "Family", "N"]];
for (let index = 0; index < families.length - 1; index += 1) {
  const sourceRow = index + 1;
  const row = 31 + index;
  const definition = String(families[sourceRow][fieldIndex(families, "family_definition")]);
  const shortLabel = definition.replace("Same-bar Setup+BOS", "Same").replace("Penetration + same-bar reclaim", "Reclaim").replace("Penetration without same-bar reclaim", "No reclaim").replace("Tolerance-only shallow touch", "Shallow");
  for (const column of ["A", "D", "G", "J"]) familyCharts.getRange(`${column}${row}`).values = [[shortLabel]];
  for (const [column, field] of [["B", "family_net_AvgR"], ["E", "family_net_TotalR"], ["H", "family_net_PF"], ["K", "family_N"]]) {
    familyCharts.getRange(`${column}${row}`).formulas = [[sourceFormula("Family Tests", families, sourceRow, field)]];
    familyCharts.getRange(`${column}${row}`).format.font = { name: "Aptos", size: 8, color: "#008000" };
  }
}
for (const address of [`A30:B${29 + families.length}`, `D30:E${29 + families.length}`, `G30:H${29 + families.length}`, `J30:K${29 + families.length}`]) formatHelper(familyCharts, address);
for (const [chartType, source, title, start, end, format] of [
  ["bar", `A30:B${29 + families.length}`, "1. Net Avg R by adequate structural family (R/trade)", "A5", "H15", "0.000"],
  ["bar", `D30:E${29 + families.length}`, "2. Net Total R by adequate structural family (R)", "I5", "P15", "0.0"],
  ["column", `G30:H${29 + families.length}`, "3. Net profit factor by adequate structural family", "A17", "H27", "0.00"],
  ["column", `J30:K${29 + families.length}`, "4. Trade count by adequate structural family (N)", "I17", "P27", "0"],
]) {
  const chart = familyCharts.charts.add(chartType, familyCharts.getRange(source));
  chart.title = title;
  chart.titleTextStyle.fontSize = 11;
  chart.hasLegend = false;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 7 } };
  chart.yAxis = { numberFormatCode: format };
  chart.setPosition(start, end);
}

const cumulativeCharts = workbook.worksheets.add("Cumulative Charts");
setupDashboard(cumulativeCharts, "Cumulative performance and time stability", "The least-negative family is not profitable and is not stable; curves are shown for diagnosis only");
const maximumSequence = cumulative.length;
const bestFamilyN = Number(families[bestFamilyRow][fieldIndex(families, "family_N")]);
const longCount = cumulative.slice(1).filter((row) => row[fieldIndex(cumulative, "long_cumulative_net_R")] !== "" && row[fieldIndex(cumulative, "long_cumulative_net_R")] != null).length;
const shortCount = cumulative.slice(1).filter((row) => row[fieldIndex(cumulative, "short_cumulative_net_R")] !== "" && row[fieldIndex(cumulative, "short_cumulative_net_R")] != null).length;
const directionSequence = Math.max(longCount, shortCount);
for (let column = 0; column < cumulative[0].length; column += 1) cumulativeCharts.getRangeByIndexes(29, column, 1, 1).values = [[cumulative[0][column]]];
for (let sourceRow = 1; sourceRow < cumulative.length; sourceRow += 1) {
  const row = sourceRow + 30;
  for (let column = 0; column < cumulative[0].length; column += 1) {
    cumulativeCharts.getRangeByIndexes(row - 1, column, 1, 1).formulas = [[sourceFormula("Cumulative", cumulative, sourceRow, String(cumulative[0][column]))]];
  }
  cumulativeCharts.getRange(`A${row}:E${row}`).format.font = { name: "Aptos", size: 7, color: "#008000" };
}
formatHelper(cumulativeCharts, `A30:E${29 + maximumSequence}`);
cumulativeCharts.getRange("G30:H30").values = [["Trade sequence", "Complement cumulative net R"]];
cumulativeCharts.getRange("J30:L30").values = [["Trade sequence", "Long cumulative net R", "Short cumulative net R"]];
for (let sourceRow = 1; sourceRow < cumulative.length; sourceRow += 1) {
  const row = sourceRow + 30;
  for (const [column, field] of [["G", "trade_sequence"], ["H", "complement_cumulative_net_R"]]) {
    cumulativeCharts.getRange(`${column}${row}`).formulas = [[sourceFormula("Cumulative", cumulative, sourceRow, field)]];
  }
  if (sourceRow <= directionSequence) {
    cumulativeCharts.getRange(`J${row}`).formulas = [[sourceFormula("Cumulative", cumulative, sourceRow, "trade_sequence")]];
    cumulativeCharts.getRange(`K${row}`).formulas = [[sourceRow <= longCount ? sourceFormula("Cumulative", cumulative, sourceRow, "long_cumulative_net_R") : `=K${row - 1}`]];
    cumulativeCharts.getRange(`L${row}`).formulas = [[sourceRow <= shortCount ? sourceFormula("Cumulative", cumulative, sourceRow, "short_cumulative_net_R") : `=L${row - 1}`]];
  }
  cumulativeCharts.getRange(`G${row}:L${row}`).format.font = { name: "Aptos", size: 7, color: "#008000" };
}
formatHelper(cumulativeCharts, `G30:H${29 + maximumSequence}`);
formatHelper(cumulativeCharts, `J30:L${30 + directionSequence}`);
function curveChart(sourceAddress, title, start, end, legend) {
  const chart = cumulativeCharts.charts.add("line", cumulativeCharts.getRange(sourceAddress));
  chart.title = title;
  chart.titleTextStyle.fontSize = 11;
  chart.hasLegend = legend;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 7 } };
  chart.yAxis = { numberFormatCode: "0.0" };
  chart.setPosition(start, end);
}
curveChart(`A30:B${30 + bestFamilyN}`, "5. Least-negative adequate family cumulative net R", "A5", "H15", false);
curveChart(`G30:H${29 + maximumSequence}`, "6. Complement cumulative net R", "I5", "P15", false);
curveChart(`J30:L${30 + directionSequence}`, "7. Direction-separated cumulative net R", "A17", "H27", true);

const bestYearRows = rowsWhere(stability, (r) => r.family_id === manifest.best_family_id && r.period_type === "Year");
const worstYearRows = rowsWhere(stability, (r) => r.family_id === manifest.worst_family_id && r.period_type === "Year");
cumulativeCharts.getRange("N30:P30").values = [["Year", "Least-negative family", "Largest loss contributor"]];
for (let index = 0; index < bestYearRows.length; index += 1) {
  const row = 31 + index;
  cumulativeCharts.getRange(`N${row}`).values = [[bestYearRows[index].record.period]];
  cumulativeCharts.getRange(`O${row}`).formulas = [[sourceFormula("Stability", stability, bestYearRows[index].row, "net_TotalR")]];
  cumulativeCharts.getRange(`P${row}`).formulas = [[sourceFormula("Stability", stability, worstYearRows[index].row, "net_TotalR")]];
  cumulativeCharts.getRange(`O${row}:P${row}`).format.font = { name: "Aptos", size: 8, color: "#008000" };
}
formatHelper(cumulativeCharts, `N30:P${30 + bestYearRows.length}`);
const yearChart = cumulativeCharts.charts.add("column", cumulativeCharts.getRange(`N30:P${30 + bestYearRows.length}`));
yearChart.title = "8. Year-by-year net Total R: least-negative vs largest loss family";
yearChart.titleTextStyle.fontSize = 11;
yearChart.hasLegend = true;
yearChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
yearChart.yAxis = { numberFormatCode: "0.0" };
yearChart.setPosition("I17", "P27");

const factorCharts = workbook.worksheets.add("Factor Charts");
setupDashboard(factorCharts, "Broad single-factor decomposition", "Frozen entry sessions and setup/BOS timing · causal labels only · all rows remain available in Factor Summary");
const sessionRows = rowsWhere(summaries, (r) => r.analysis_level === "Single factor" && r.dimension === "Entry session" && r.direction_slice === "All");
factorCharts.getRange("A30:C30").values = [["Entry session", "N", "Net Avg R"]];
for (let index = 0; index < sessionRows.length; index += 1) {
  const row = 31 + index;
  factorCharts.getRange(`A${row}`).values = [[sessionRows[index].record.category]];
  factorCharts.getRange(`B${row}`).formulas = [[sourceFormula("Factor Summary", summaries, sessionRows[index].row, "N")]];
  factorCharts.getRange(`C${row}`).formulas = [[sourceFormula("Factor Summary", summaries, sessionRows[index].row, "net_AvgR")]];
  factorCharts.getRange(`B${row}:C${row}`).format.font = { name: "Aptos", size: 8, color: "#008000" };
}
formatHelper(factorCharts, `A30:C${30 + sessionRows.length}`);
factorCharts.getRange("E30:F30").values = [["Entry session", "Net Avg R"]];
for (let index = 0; index < sessionRows.length; index += 1) {
  const row = 31 + index;
  factorCharts.getRange(`E${row}`).values = [[sessionRows[index].record.category]];
  factorCharts.getRange(`F${row}`).formulas = [[sourceFormula("Factor Summary", summaries, sessionRows[index].row, "net_AvgR")]];
  factorCharts.getRange(`F${row}`).format.font = { name: "Aptos", size: 8, color: "#008000" };
}
formatHelper(factorCharts, `E30:F${30 + sessionRows.length}`);
const sessionChart = factorCharts.charts.add("bar", factorCharts.getRange(`E30:F${30 + sessionRows.length}`));
sessionChart.title = "9. Entry-session decomposition: net Avg R (R/trade)";
sessionChart.titleTextStyle.fontSize = 11;
sessionChart.hasLegend = true;
sessionChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
sessionChart.yAxis = { numberFormatCode: "0.000" };
sessionChart.setPosition("A5", "H25");

factorCharts.getRange("J30:M30").values = [["Setup/BOS timing", "N", "Net Avg R", "Net Total R"]];
for (const [index, sourceRow] of [sameBarRow, delayedRow].entries()) {
  const row = 31 + index;
  factorCharts.getRange(`J${row}`).formulas = [[sourceFormula("Factor Summary", summaries, sourceRow, "category")]];
  for (const [column, field] of [["K", "N"], ["L", "net_AvgR"], ["M", "net_TotalR"]]) {
    factorCharts.getRange(`${column}${row}`).formulas = [[sourceFormula("Factor Summary", summaries, sourceRow, field)]];
  }
  factorCharts.getRange(`J${row}:M${row}`).format.font = { name: "Aptos", size: 8, color: "#008000" };
}
formatHelper(factorCharts, "J30:M32");
factorCharts.getRange("O30:P30").values = [["Setup/BOS timing", "Net Avg R"]];
for (const [index, sourceRow] of [sameBarRow, delayedRow].entries()) {
  const row = 31 + index;
  factorCharts.getRange(`O${row}`).formulas = [[sourceFormula("Factor Summary", summaries, sourceRow, "category")]];
  factorCharts.getRange(`P${row}`).formulas = [[sourceFormula("Factor Summary", summaries, sourceRow, "net_AvgR")]];
  factorCharts.getRange(`O${row}:P${row}`).format.font = { name: "Aptos", size: 8, color: "#008000" };
}
formatHelper(factorCharts, "O30:P32");
const timingChart = factorCharts.charts.add("column", factorCharts.getRange("O30:P32"));
timingChart.title = "10. Same-bar Setup+BOS versus delayed BOS";
timingChart.titleTextStyle.fontSize = 11;
timingChart.hasLegend = true;
timingChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 8 } };
timingChart.yAxis = { numberFormatCode: "0.000" };
timingChart.setPosition("I5", "P25");

const audit = workbook.worksheets.add("Audit Calc");
audit.showGridLines = false;
audit.getRange("A1:L1").values = [["Trade ID", "Direction", "Entry price", "Stop price", "Gross R", "Imported cost R", "Risk points", "Formula cost R", "Formula net R", "Imported net R", "Delta", "Status"]];
audit.getRange("A1:L1").format = { fill: "#17324D", font: { name: "Aptos", size: 9, bold: true, color: "#FFFFFF" }, rowHeight: 36, wrapText: true };
audit.getRange("N1:O3").values = [["Assumption", "Value"], ["Round-turn USD", 14.5], ["NQ USD/point", 20]];
audit.getRange("N1:O1").format = { fill: "#17324D", font: { name: "Aptos", size: 9, bold: true, color: "#FFFFFF" } };
for (let index = 1; index < tradeFeatures.length; index += 1) {
  const row = index + 1;
  for (const [column, field] of [["A", "trade_id"], ["B", "direction"], ["C", "entry_price"], ["D", "stop_price"], ["E", "gross_R"], ["F", "cost_R"], ["J", "net_R"]]) {
    audit.getRange(`${column}${row}`).formulas = [[sourceFormula("Trade Features", tradeFeatures, index, field)]];
  }
  audit.getRange(`G${row}`).formulas = [[`=ABS(C${row}-D${row})`]];
  audit.getRange(`H${row}`).formulas = [[`=IFERROR($O$2/(G${row}*$O$3),0)`]];
  audit.getRange(`I${row}`).formulas = [[`=E${row}-H${row}`]];
  audit.getRange(`K${row}`).formulas = [[`=I${row}-J${row}`]];
  audit.getRange(`L${row}`).formulas = [[`=IF(ABS(K${row})<0.000000001,"PASS","FAIL")`]];
}
audit.getRange(`A2:F${tradeFeatures.length}`).format.font = { name: "Aptos", size: 8, color: "#008000" };
audit.getRange(`J2:J${tradeFeatures.length}`).format.font = { name: "Aptos", size: 8, color: "#008000" };
audit.getRange(`G2:I${tradeFeatures.length}`).format.font = { name: "Aptos", size: 8, color: "#000000" };
audit.getRange(`K2:L${tradeFeatures.length}`).format.font = { name: "Aptos", size: 8, color: "#000000" };
audit.getRange(`C2:K${tradeFeatures.length}`).format.numberFormat = "0.000000";
audit.getRange(`L2:L${tradeFeatures.length}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#D4EDDA", font: { color: "#176B3A", bold: true } } });
audit.freezePanes.freezeRows(1);
audit.getRange("A1:A706").format.columnWidth = 11;
audit.getRange("B1:B706").format.columnWidth = 11;
audit.getRange("C1:L706").format.columnWidth = 15;
audit.getRange("N1:O3").format.columnWidth = 20;

const methodology = workbook.worksheets.add("Methodology");
methodology.showGridLines = false;
methodology.getRange("A1:H2").merge();
methodology.getRange("A1").values = [["Frozen design, causal feature rules, and robustness gates"]];
methodology.getRange("A1:H2").format = { fill: "#102A43", font: { name: "Aptos Display", size: 18, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" };
methodology.getRange("A4:B20").values = [
  ["Scope", "Development data only: 2024-01-01 through 2026-06-26. No new data, unseen OOS, Pine edit, or frozen-engine edit."],
  ["Baseline gate", "Reproduced all 705 archived Confirm trades with zero mismatches across 17 identity, event, price, result, score, regime, session, and exit fields."],
  ["Costs", "$14.50 round turn converted to R from each frozen stop distance at $20 per NQ point."],
  ["Causality", "Setup, BOS, retest, confirmation, session, HTF, volatility, liquidity, and candle-structure fields use only information available at or before entry."],
  ["Outcome labels", "MFE, MAE, exit, and outcome are evaluation labels only and do not define an archetype."],
  ["Real setup triggers", "Setup type records whether the frozen SetupEngine accepted matching BOS, matching liquidity sweep, or both. No unsupported narrative label was invented."],
  ["Liquidity context", "Recent BSL/SSL comes from the already-confirmed frozen liquidity engine. CRT-bar sweep is recorded separately from Phase-1 CRT reference behavior."],
  ["Retest behavior", "Objective categories use the frozen BOS boundary: tolerance-only shallow touch, exact BOS touch, penetration plus same-bar reclaim, or penetration without same-bar reclaim."],
  ["Family scheme", "One interpretable depth-3 scheme only: Direction × Setup/BOS timing × Retest behavior. No brute-force combination search."],
  ["Sample rule", "N≥30 is ADEQUATE N for testing; N<30 is SMALL SAMPLE and remains visible but is not promoted."],
  ["Chronological halves", "True ordered-trade split: first 352 trades versus second 353 trades."],
  ["Time stability", "Positive/negative robustness requires at least two of three years and both chronological halves with the same sign."],
  ["Outlier checks", "Adequate families are recomputed after removing the best trade, top 1% winners, and top three winners."],
  ["Complement", "Each adequate family is compared with all remaining 705-trade baseline trades."],
  ["Statistics", "Two-sided Welch family-versus-complement tests with Benjamini-Hochberg FDR at 5% across all adequate-N families."],
  ["Interpretation", "The reported 'best' family is only the least-negative adequate cell. It is not profitable or robust and must not become a filter."],
  ["Final class", manifest.classification],
];
methodology.getRange("A4:A20").format = { fill: "#D9EAF7", font: { name: "Aptos", size: 10, bold: true, color: "#334E68" }, verticalAlignment: "top" };
methodology.getRange("B4:B20").format = { font: { name: "Aptos", size: 10, color: "#1F2937" }, wrapText: true, verticalAlignment: "top" };
methodology.getRange("A4:B20").format.rowHeight = 49;
methodology.getRange("A1:A20").format.columnWidth = 25;
methodology.getRange("B1:B20").format.columnWidth = 112;
methodology.freezePanes.freezeRows(2);

const checks = workbook.worksheets.add("Checks");
checks.showGridLines = false;
checks.getRange("A1:F2").merge();
checks.getRange("A1").values = [["Formula-driven reproducibility, scope, and partition checks"]];
checks.getRange("A1:F2").format = { fill: "#102A43", font: { name: "Aptos Display", size: 18, bold: true, color: "#FFFFFF" }, verticalAlignment: "center" };
checks.getRange("A4:E4").values = [["Check", "Actual", "Expected", "Tolerance", "Status"]];
const checkRows = [
  ["Baseline N", sourceFormula("Baseline", baseline, 1, "N"), 705, 0],
  ["Baseline net wins", sourceFormula("Baseline", baseline, 1, "net_wins"), 284, 0],
  ["Baseline net losses", sourceFormula("Baseline", baseline, 1, "net_losses"), 421, 0],
  ["Baseline net Total R", sourceFormula("Baseline", baseline, 1, "net_TotalR"), -49.04906605411777, 1e-9],
  ["Baseline net PF", sourceFormula("Baseline", baseline, 1, "net_PF"), 0.8717849563156026, 1e-9],
  ["Baseline net Max DD", sourceFormula("Baseline", baseline, 1, "net_MaxDD_R"), 60.29673416610867, 1e-9],
  ["Trade feature rows", "=COUNTA('Trade Features'!A2:A706)", 705, 0],
  ["Family partition", "=SUMIF('Factor Summary'!A:A,\"Three-dimension structural family\",'Factor Summary'!H:H)", 705, 0],
  ["Adequate family tests", "=COUNTA('Family Tests'!A2:A100)", manifest.adequate_N_family_tests, 0],
  ["FDR survivors", `=COUNTIF('Family Tests'!${columnLetter(fieldIndex(families, "FDR_significant_0_05"))}2:${columnLetter(fieldIndex(families, "FDR_significant_0_05"))}100,TRUE)`, manifest.FDR_survivors, 0],
  ["Archived reconciliation mismatches", "=SUM(Reconciliation!C2:C100)", 0, 0],
  ["Audit cost/net failures", `=COUNTIF('Audit Calc'!L2:L706,\"FAIL\")`, 0, 0],
];
checks.getRange("A5:A16").values = checkRows.map((row) => [row[0]]);
checks.getRange("B5:B16").formulas = checkRows.map((row) => [row[1]]);
checks.getRange("C5:D16").values = checkRows.map((row) => [row[2], row[3]]);
checks.getRange("E5:E16").formulas = checkRows.map((_, index) => [`=IF(ABS(B${5 + index}-C${5 + index})<=D${5 + index},\"PASS\",\"FAIL\")`]);
checks.getRange("A4:E4").format = { fill: "#17324D", font: { name: "Aptos", size: 10, bold: true, color: "#FFFFFF" }, rowHeight: 28 };
checks.getRange("A5:E16").format = { borders: { preset: "inside", style: "thin", color: "#D9E2EC" }, rowHeight: 24, font: { name: "Aptos", size: 10, color: "#1F2937" } };
checks.getRange("B5:D16").format.numberFormat = "0.000000000";
checks.getRange("E5:E16").conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#D4EDDA", font: { color: "#176B3A", bold: true } } });
checks.getRange("E5:E16").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#F8D7DA", font: { color: "#B42318", bold: true } } });
checks.getRange("A1:A16").format.columnWidth = 36;
checks.getRange("B1:D16").format.columnWidth = 19;
checks.getRange("E1:E16").format.columnWidth = 16;
checks.freezePanes.freezeRows(4);

const inspect = await workbook.inspect({ kind: "workbook,sheet,drawing", maxChars: 30000, tableMaxRows: 8, tableMaxCols: 16 });
const formulaErrors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, maxChars: 6000 });
const inspectText = `${inspect.ndjson || inspect}\n${formulaErrors.ndjson || formulaErrors}\n`;
await fs.writeFile(inspectPath, inspectText);
console.log(inspectText);

const summaryPreview = await workbook.render({ sheetName: "Executive", autoCrop: "all", scale: 1, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await summaryPreview.arrayBuffer()));

const renderRanges = {
  Executive: "A1:N25",
  "Family Charts": "A1:P37",
  "Cumulative Charts": "A1:P40",
  "Factor Charts": "A1:P38",
  "Trade Features": "A1:P18",
  "Factor Summary": "A1:AC18",
  "Family Tests": "A1:P8",
  Stability: "A1:Z12",
  Cumulative: "A1:E20",
  Baseline: "A1:AC3",
  Reconciliation: "A1:C20",
  "Audit Calc": "A1:O18",
  Methodology: "A1:H20",
  Checks: "A1:E16",
};
for (const [sheetName, range] of Object.entries(renderRanges)) {
  const image = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(qaDir, `${sheetName.replaceAll(" ", "_")}.png`), new Uint8Array(await image.arrayBuffer()));
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(`WROTE ${outputPath}`);
console.log(`PREVIEW ${previewPath}`);
console.log(`QA_DIR ${qaDir}`);
