import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const sourceDir = path.join(projectRoot, "phase16/results/bos_semantic_audit");
const outputDir = path.join(projectRoot, "outputs/bos_semantic_audit");
const previewDir = path.join(outputDir, "previews");
await fs.mkdir(previewDir, { recursive: true });

const colors = {
  navy: "#17324D",
  teal: "#117A8B",
  lightTeal: "#DDEFF2",
  pale: "#F4F7FA",
  gray: "#667085",
  grid: "#D0D5DD",
  red: "#B42318",
  paleRed: "#FEE4E2",
  green: "#027A48",
  paleGreen: "#D1FADF",
  amber: "#B54708",
  paleAmber: "#FEF0C7",
  white: "#FFFFFF",
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field.replace(/\r$/, ""));
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ""));
    rows.push(row);
  }
  return rows;
}

function valueOf(raw) {
  if (raw === "") return null;
  if (raw === "True") return true;
  if (raw === "False") return false;
  if (raw === "nan" || raw === "NaN") return null;
  if (/^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw)) return Number(raw);
  return raw;
}

async function readCsv(name) {
  const text = await fs.readFile(path.join(sourceDir, name), "utf8");
  const rows = parseCsv(text);
  return { headers: rows[0], rows: rows.slice(1).filter((row) => row.some((cell) => cell !== "")).map((row) => row.map(valueOf)) };
}

function columnName(number) {
  let result = "";
  let value = number;
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

function writeMatrix(sheet, startRow, startCol, matrix) {
  if (!matrix.length || !matrix[0].length) return;
  sheet.getRangeByIndexes(startRow, startCol, matrix.length, matrix[0].length).values = matrix;
}

function titleBand(sheet, range, title, subtitle = "") {
  sheet.getRange(range).merge();
  sheet.getRange(range).values = [[title]];
  sheet.getRange(range).format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 18 },
    verticalAlignment: "center",
    rowHeight: 34,
  };
  if (subtitle) {
    const start = Number(range.match(/\d+/)?.[0] ?? 1) + 2;
    sheet.getRange(`A${start}:L${start + 1}`).merge();
    sheet.getRange(`A${start}:L${start + 1}`).values = [[subtitle]];
    sheet.getRange(`A${start}:L${start + 1}`).format = {
      fill: colors.pale,
      font: { color: colors.gray, italic: true, size: 10 },
      wrapText: true,
      verticalAlignment: "center",
    };
  }
  sheet.showGridLines = false;
}

function styleTable(sheet, range, headerRow = 1) {
  const used = sheet.getRange(range);
  used.format.borders = { preset: "all", style: "thin", color: colors.grid };
  const columns = used.columnCount;
  sheet.getRangeByIndexes(headerRow - 1, used.columnIndex, 1, columns).format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: colors.grid },
  };
  used.format.autofitColumns();
  used.format.autofitRows();
}

function capWidths(sheet, columns, width = 18) {
  for (const column of columns) sheet.getRange(`${column}:${column}`).format.columnWidth = width;
}

function addCsvSheet(workbook, name, csv, selectedHeaders = null) {
  const sheet = workbook.worksheets.add(name);
  let headers = csv.headers;
  let rows = csv.rows;
  if (selectedHeaders) {
    const indexes = selectedHeaders.map((header) => headers.indexOf(header));
    if (indexes.some((index) => index < 0)) throw new Error(`Missing selected column on ${name}`);
    headers = selectedHeaders;
    rows = rows.map((row) => indexes.map((index) => row[index]));
  }
  writeMatrix(sheet, 0, 0, [headers, ...rows]);
  const end = `${columnName(headers.length)}${rows.length + 1}`;
  styleTable(sheet, `A1:${end}`, 1);
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;
  return sheet;
}

const comparisonCsv = await readCsv("structural_bos_comparison.csv");
const stabilityCsv = await readCsv("structural_bos_year_stability.csv");
const swingCsv = await readCsv("bos_swing_quality.csv");
const eventOrderCsv = await readCsv("bos_event_order_summary.csv");
const redundancyCsv = await readCsv("bos_setup_redundancy.csv");
const bosEventsCsv = await readCsv("bos_event_audit.csv");
const caseCsv = await readCsv("bos_case_studies.csv");

const tradeSources = [
  ["Current BOS 5/5 (same-bar allowed)", "trades_current_bos_5_5_same-bar_allowed.csv"],
  ["Structural BOS 2/2 (later only)", "trades_structural_bos_2_2_later_only.csv"],
  ["Structural BOS 3/3 (later only)", "trades_structural_bos_3_3_later_only.csv"],
  ["Structural BOS 5/5 (later only)", "trades_structural_bos_5_5_later_only.csv"],
];
const tradeRows = [];
for (const [model, file] of tradeSources) {
  const csv = await readCsv(file);
  const index = Object.fromEntries(csv.headers.map((header, position) => [header, position]));
  for (const row of csv.rows) {
    tradeRows.push([
      model,
      row[index.direction],
      row[index.entry_timestamp],
      row[index.exit_timestamp],
      row[index.gross_R],
      row[index.cost_R],
      row[index.net_R],
      row[index.outcome],
      row[index.MFE_R],
      row[index.MAE_R],
    ]);
  }
}

const workbook = Workbook.create();

const overview = workbook.worksheets.add("Overview");
// Create formula-referenced sheets before assigning cross-sheet formulas.
const comparison = workbook.worksheets.add("Comparison");
titleBand(
  overview,
  "A1:L2",
  "BOS Semantic / Market-Structure Audit",
  "Frozen 705-trade development baseline • causal confirmed-pivot diagnostics • no Pine or frozen-engine changes"
);
overview.getRange("A5:L6").merge();
overview.getRange("A5:L6").values = [["VERDICT — B: CURRENT BOS IS PARTIALLY REDUNDANT"]];
overview.getRange("A5:L6").format = {
  fill: colors.paleAmber,
  font: { bold: true, color: colors.amber, size: 15 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
overview.getRange("A8:C12").values = [
  ["Guardrail", "Result", "Meaning"],
  ["Baseline reconciliation", "PASS", "705/705 trades, zero field mismatches"],
  ["Lookahead assertions", "PASS", "Pivot known only after right-side closes"],
  ["Pine modified", "NO", "Audit/research branch only"],
  ["Frozen engine modified", "NO", "Imports and replays frozen modules"],
];
styleTable(overview, "A8:C12", 8);
overview.getRange("B9:B10").format = { fill: colors.paleGreen, font: { bold: true, color: colors.green } };
overview.getRange("B11:B12").format = { fill: colors.pale, font: { bold: true, color: colors.navy } };
overview.getRange("E8:H13").values = [
  ["Semantic fact", "N", "%", "Conclusion"],
  ["Setup == BOS", 664, 664 / 705, "Same directional event reused"],
  ["Current break is Phase 3 BOS", 301, 301 / 705, "Trend-labelled"],
  ["Current break is Phase 3 CHoCH", 404, 404 / 705, "Still called BOS by funnel"],
  ["Also breaks causal 2/2 swing", 533, 533 / 705, "75.60%"],
  ["Also breaks causal 3/3 swing", 615, 615 / 705, "87.23%"],
];
styleTable(overview, "E8:H13", 8);
overview.getRange("G9:G13").format.numberFormat = "0.00%";
overview.getRange("A15:L18").merge();
overview.getRange("A15:L18").values = [[
  "Mechanism: Phase 5 can create Setup from bullBreakEvent/bearBreakEvent. Phase 12 starts WAIT_BOS and immediately evaluates a separate same-bar BOS if-block, consuming that same still-true event. The level itself is a genuine previously confirmed 5/5 pivot and was never stale/pre-crossed in the audited 705 trades."
]];
overview.getRange("A15:L18").format = { fill: colors.lightTeal, font: { color: colors.navy, size: 11 }, wrapText: true, verticalAlignment: "center" };
overview.getRange("A20:F25").values = [
  ["Model", "N", "Net AvgR", "Net TotalR", "Net PF", "MaxDD R"],
  ["Current BOS", null, null, null, null, null],
  ["Structural 2/2", null, null, null, null, null],
  ["Structural 3/3", null, null, null, null, null],
  ["Structural 5/5", null, null, null, null, null],
  ["Conclusion", "2/2 is marginally positive; 3/3 and 5/5 remain negative", null, null, null, null],
];
styleTable(overview, "A20:F25", 20);
overview.getRange("B21:F21").formulas = [["=Comparison!C7", "=Comparison!H7", "=Comparison!J7", "=Comparison!K7", "=Comparison!L7"]];
overview.getRange("B22:F22").formulas = [["=Comparison!C10", "=Comparison!H10", "=Comparison!J10", "=Comparison!K10", "=Comparison!L10"]];
overview.getRange("B23:F23").formulas = [["=Comparison!C13", "=Comparison!H13", "=Comparison!J13", "=Comparison!K13", "=Comparison!L13"]];
overview.getRange("B24:F24").formulas = [["=Comparison!C16", "=Comparison!H16", "=Comparison!J16", "=Comparison!K16", "=Comparison!L16"]];
overview.getRange("B21:B24").format.numberFormat = "0";
overview.getRange("C21:F24").format.numberFormat = "0.0000";
overview.getRange("B25:F25").merge();
overview.getRange("B25:F25").format = { fill: colors.paleRed, font: { bold: true, color: colors.red }, wrapText: true };
overview.getRange("H20:L25").values = [
  ["Required question", "Answer", null, null, null],
  ["Is current BOS structural?", "YES — causal 5/5 close break", null, null, null],
  ["Is it independent of Setup?", "Usually NO — 94.18% same bar", null, null, null],
  ["Does later structural BOS help?", "2/2 is marginally positive; effect is not broad/stable", null, null, null],
  ["Stable across definitions/time?", "NO", null, null, null],
  ["Implementation recommendation", "Do not implement from this audit", null, null, null],
];
for (let row = 20; row <= 25; row += 1) overview.getRange(`I${row}:L${row}`).merge();
styleTable(overview, "H20:L25", 20);
overview.freezePanes.freezeRows(4);
capWidths(overview, ["A", "B", "C", "E", "F", "G", "H"], 20);

const dataTrades = workbook.worksheets.add("Data Trades");
const tradeHeaders = ["Model", "Direction", "Entry Timestamp", "Exit Timestamp", "Gross R", "Cost R", "Net R", "Outcome", "MFE R", "MAE R"];
writeMatrix(dataTrades, 0, 0, [tradeHeaders, ...tradeRows]);
styleTable(dataTrades, `A1:J${tradeRows.length + 1}`, 1);
dataTrades.getRange(`E2:G${tradeRows.length + 1}`).format.numberFormat = "0.0000";
dataTrades.getRange(`I2:J${tradeRows.length + 1}`).format.numberFormat = "0.0000";
dataTrades.freezePanes.freezeRows(1);
dataTrades.showGridLines = false;
capWidths(dataTrades, ["A"], 37);
capWidths(dataTrades, ["C", "D"], 25);

titleBand(comparison, "A1:L2", "Formula-Driven Model Comparison", "Counts and net metrics calculate from Data Trades; median and MaxDD are audited source outputs.");
const allRows = comparisonCsv.rows;
const cidx = Object.fromEntries(comparisonCsv.headers.map((header, position) => [header, position]));
const comparisonMatrix = [["Model", "Scope", "N", "Retention", "Wins", "Losses", "Win %", "Net AvgR", "Net MedianR", "Net TotalR", "Net PF", "MaxDD R"]];
for (const row of allRows) {
  comparisonMatrix.push([
    row[cidx.model], row[cidx.scope], null, null, null, null, null, null,
    row[cidx.net_median_R], null, null, row[cidx.net_MaxDD_R],
  ]);
}
writeMatrix(comparison, 5, 0, comparisonMatrix);
const tradeEnd = tradeRows.length + 1;
for (let r = 7; r < 7 + allRows.length; r += 1) {
  const modelRange = `'Data Trades'!$A$2:$A$${tradeEnd}`;
  const dirRange = `'Data Trades'!$B$2:$B$${tradeEnd}`;
  const netRange = `'Data Trades'!$G$2:$G$${tradeEnd}`;
  const allScope = `$B${r}="All"`;
  comparison.getRange(`C${r}`).formulas = [[`=IF(${allScope},COUNTIF(${modelRange},$A${r}),COUNTIFS(${modelRange},$A${r},${dirRange},$B${r}))`]];
  comparison.getRange(`D${r}`).formulas = [[`=C${r}/$C$7`]];
  comparison.getRange(`E${r}`).formulas = [[`=IF(${allScope},COUNTIFS(${modelRange},$A${r},${netRange},">0"),COUNTIFS(${modelRange},$A${r},${dirRange},$B${r},${netRange},">0"))`]];
  comparison.getRange(`F${r}`).formulas = [[`=IF(${allScope},COUNTIFS(${modelRange},$A${r},${netRange},"<0"),COUNTIFS(${modelRange},$A${r},${dirRange},$B${r},${netRange},"<0"))`]];
  comparison.getRange(`G${r}`).formulas = [[`=IFERROR(E${r}/C${r},0)`]];
  comparison.getRange(`H${r}`).formulas = [[`=IFERROR(IF(${allScope},SUMIF(${modelRange},$A${r},${netRange})/C${r},SUMIFS(${netRange},${modelRange},$A${r},${dirRange},$B${r})/C${r}),0)`]];
  comparison.getRange(`J${r}`).formulas = [[`=IF(${allScope},SUMIF(${modelRange},$A${r},${netRange}),SUMIFS(${netRange},${modelRange},$A${r},${dirRange},$B${r}))`]];
  comparison.getRange(`K${r}`).formulas = [[`=IFERROR(IF(${allScope},SUMIFS(${netRange},${modelRange},$A${r},${netRange},">0")/-SUMIFS(${netRange},${modelRange},$A${r},${netRange},"<0"),SUMIFS(${netRange},${modelRange},$A${r},${dirRange},$B${r},${netRange},">0")/-SUMIFS(${netRange},${modelRange},$A${r},${dirRange},$B${r},${netRange},"<0")),0)`]];
}
styleTable(comparison, `A6:L${6 + allRows.length}`, 6);
comparison.getRange(`D7:D${6 + allRows.length}`).format.numberFormat = "0.00%";
comparison.getRange(`G7:G${6 + allRows.length}`).format.numberFormat = "0.00%";
comparison.getRange(`H7:L${6 + allRows.length}`).format.numberFormat = "0.0000";
comparison.freezePanes.freezeRows(6);
capWidths(comparison, ["A"], 38);
const allModelRows = [7, 10, 13, 16];
comparison.getRange("N6:O10").values = [
  ["Model", "Net AvgR"],
  ["Current", null],
  ["2/2", null],
  ["3/3", null],
  ["5/5", null],
];
allModelRows.forEach((sourceRow, index) => {
  comparison.getRange(`O${7 + index}`).formulas = [[`=H${sourceRow}`]];
});
const comparisonChart = comparison.charts.add("bar", comparison.getRange("N6:O10"));
comparisonChart.title = "Only 2/2 is marginally positive after costs";
comparisonChart.hasLegend = false;
comparisonChart.yAxis = { numberFormatCode: "0.00" };
comparisonChart.setPosition("N12", "V27");

const stability = addCsvSheet(workbook, "Time Stability", stabilityCsv, [
  "model", "period_type", "period", "N", "net_win_rate_pct", "net_AvgR", "net_TotalR", "net_PF", "net_MaxDD_R",
]);
stability.getRange(`E2:I${stabilityCsv.rows.length + 1}`).format.numberFormat = "0.0000";
capWidths(stability, ["A"], 38);
stability.getRange("K1:L13").values = [
  ["Year / Model", "Net AvgR"],
  ["2024 Current", null], ["2025 Current", null], ["2026 Current", null],
  ["2024 2/2", null], ["2025 2/2", null], ["2026 2/2", null],
  ["2024 3/3", null], ["2025 3/3", null], ["2026 3/3", null],
  ["2024 5/5", null], ["2025 5/5", null], ["2026 5/5", null],
];
const stabilityYearRows = [2, 3, 4, 7, 8, 9, 12, 13, 14, 17, 18, 19];
stabilityYearRows.forEach((sourceRow, index) => {
  stability.getRange(`L${index + 2}`).formulas = [[`=F${sourceRow}`]];
});
const stabilityChart = stability.charts.add("bar", stability.getRange("K1:L13"));
stabilityChart.title = "Net AvgR changes sign across years";
stabilityChart.hasLegend = false;
stabilityChart.yAxis = { numberFormatCode: "0.00" };
stabilityChart.setPosition("K15", "S34");

const swingQuality = addCsvSheet(workbook, "Swing Quality", swingCsv, [
  "timing", "swing_model", "diagnostic_state", "N", "net_win_rate_pct", "net_AvgR", "net_median_R", "net_TotalR", "net_PF", "avg_MFE_R", "avg_MAE_R",
]);
swingQuality.getRange(`E2:K${swingCsv.rows.length + 1}`).format.numberFormat = "0.0000";
capWidths(swingQuality, ["A", "C"], 24);

const eventOrder = addCsvSheet(workbook, "Event Order", eventOrderCsv);
eventOrder.getRange(`D2:D${eventOrderCsv.rows.length + 1}`).format.numberFormat = "0.00";
capWidths(eventOrder, ["A"], 28);
const eventChart = eventOrder.charts.add("bar", eventOrder.getRange(`A1:C${eventOrderCsv.rows.length + 1}`));
eventChart.title = "Event-gap counts and same-bar collapses";
eventChart.hasLegend = false;
eventChart.setPosition("F2", "N20");

const redundancy = addCsvSheet(workbook, "Setup Redundancy", redundancyCsv, [
  "setup_id", "setup_timestamp", "direction", "score", "status", "bos_timestamp", "setup_to_bos_bars", "opposite_bos_timestamp",
]);
capWidths(redundancy, ["B", "F", "H"], 26);
capWidths(redundancy, ["E"], 24);
redundancy.getRange("J1:K5").values = [
  ["Status", "N"],
  ["Immediate same-bar", 2277],
  ["Later under frozen order", 120],
  ["Never/opposite first", 958],
  ["Total canonical setups", 3355],
];
const redundancyChart = redundancy.charts.add("bar", redundancy.getRange("J1:K4"));
redundancyChart.title = "Immediate BOS occurs for 67.87% of all valid setups";
redundancyChart.hasLegend = false;
redundancyChart.setPosition("J7", "R23");

const bosEvents = addCsvSheet(workbook, "BOS Events", bosEventsCsv, [
  "trade_id", "direction", "setup_timestamp", "bos_timestamp", "same_bar_setup_bos", "bos_break_type",
  "bos_reference_level", "bos_reference_timestamp", "bos_reference_confirmation_timestamp", "bars_confirmation_to_bos",
  "reference_already_crossed_on_prior_bar", "swing_2_2_break_same_bar", "swing_3_3_break_same_bar", "swing_5_5_break_same_bar",
  "retest_timestamp", "confirmation_timestamp", "entry_timestamp", "stop_price", "target_price", "gross_R", "cost_R", "net_R", "MFE_R", "MAE_R",
]);
bosEvents.getRange(`G2:G${bosEventsCsv.rows.length + 1}`).format.numberFormat = "0.00";
bosEvents.getRange(`R2:S${bosEventsCsv.rows.length + 1}`).format.numberFormat = "0.00";
bosEvents.getRange(`T2:X${bosEventsCsv.rows.length + 1}`).format.numberFormat = "0.0000";
capWidths(bosEvents, ["C", "D", "H", "I", "O", "P", "Q"], 25);

const caseData = addCsvSheet(workbook, "Case Data", caseCsv, [
  "case_category", "case_number", "trade_id", "direction", "setup_timestamp", "bos_timestamp", "same_bar_setup_bos",
  "bos_reference_level", "swing_3_3_break_same_bar", "swing_3_3_level", "swing_3_3_pivot_timestamp",
  "swing_3_3_confirmation_timestamp", "retest_timestamp", "confirmation_timestamp",
  "entry_timestamp", "entry_price", "stop_price", "target_price", "net_R", "MFE_R", "MAE_R",
]);
capWidths(caseData, ["A"], 35);
capWidths(caseData, ["E", "F", "K", "L", "M"], 25);

const methodology = workbook.worksheets.add("Methodology");
titleBand(methodology, "A1:L2", "Methodology and Read-Me", "This workbook is an audit package, not a strategy optimizer.");
methodology.getRange("A5:C19").values = [
  ["Topic", "Frozen / diagnostic rule", "Audit conclusion"],
  ["Baseline", "705 Confirm trades; archived timestamp/direction/field identity", "PASS — zero mismatches"],
  ["Long BOS", "close > most recent confirmed unused 5/5 pivot high", "Real causal swing break"],
  ["Short BOS", "close < most recent confirmed unused 5/5 pivot low", "Exact mirror"],
  ["Wicks", "Do not qualify under Close mode", "Close required"],
  ["Pivot knowability", "T pivot available after T+right closes", "No retroactive use"],
  ["Phase 3 ordering", "Break test before same-bar pivot ingestion", "No same-confirmation-bar break"],
  ["Setup trigger", "directional break OR matching liquidity sweep", "Can reuse BOS event"],
  ["Funnel ordering", "Start WAIT_BOS, then separate same-bar BOS if", "Causes 664 same-bar paths"],
  ["Retest", "Strictly after BOS; frozen tolerance/invalidation", "Preserved"],
  ["Confirm", "Strictly after Retest", "Preserved"],
  ["Entry", "Confirmation close", "Confirm == Entry by design"],
  ["Counterfactual", "Later-only 2/2, 3/3, 5/5 causal swing break", "Research only"],
  ["Costs", "$14.50 round turn converted to R", "Preserved"],
  ["Recommendation", "No implementation from this audit", "No broad stable positive expectancy"],
];
styleTable(methodology, "A5:C19", 5);
capWidths(methodology, ["A"], 25);
capWidths(methodology, ["B", "C"], 58);
methodology.getRange("A21:L27").merge();
methodology.getRange("A21:L27").values = [[
  "Code references: Pine break logic outputs/CRT_Core_RETEST_GATED_LIVE.pine lines 471–477; Pine setup trigger lines 870–890; canonical feed lines 2216–2222; Phase 12 same-bar state transition lines 2602–2636. Python mirrors: phase16/structure.py lines 35–77, phase16/setup_engine.py lines 131–153, phase16/entry_models.py lines 90–129. Frozen Pine and Python files were not edited."
]];
methodology.getRange("A21:L27").format = { fill: colors.pale, font: { color: colors.gray }, wrapText: true, verticalAlignment: "center" };

const imageSheets = [
  ["Cases Same Winners", "same-bar_winners.png", "10 deterministic same-bar winners"],
  ["Cases Same Losers", "same-bar_losers.png", "10 deterministic same-bar losers"],
  ["Cases Delayed", "delayed_bos.png", "10 deterministic delayed-BOS trades"],
  ["Cases No 3-3", "no_3_3_structural_break_on_bos_bar.png", "10 trades without a simultaneous 3/3 break"],
  ["Cases Did 3-3", "did_break_3_3_structure_on_bos_bar.png", "10 trades with a simultaneous 3/3 break"],
];
for (const [sheetName, file, title] of imageSheets) {
  const sheet = workbook.worksheets.add(sheetName);
  titleBand(sheet, "A1:L2", title, "Vertical: purple Setup, blue BOS, orange Retest, green Confirm/Entry • Horizontal: blue 5/5 reference, purple 3/3 swing, dotted red/green Stop/Target");
  const bytes = await fs.readFile(path.join(sourceDir, "case_study_charts", file));
  sheet.images.add({
    dataUrl: `data:image/png;base64,${bytes.toString("base64")}`,
    anchor: { from: { row: 4, col: 0 }, extent: { widthPx: 1500, heightPx: 1660 } },
  });
  sheet.showGridLines = false;
}

// Verification: inspect every sheet and render every sheet at a conservative
// scale. Data sheets use selected audit columns to keep previews tractable.
const sheetNames = workbook.worksheets.items.map((sheet) => sheet.name);
const inspection = [];
for (const sheetName of sheetNames) {
  const info = await workbook.inspect({ kind: "region", sheetId: sheetName, range: "A1:L25", maxChars: 1200 });
  inspection.push({ sheetName, preview: info.ndjson?.slice(0, 240) ?? "" });
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 0.25, format: "png" });
  await fs.writeFile(path.join(previewDir, `${sheetName.replaceAll(" ", "_")}.png`), new Uint8Array(await preview.arrayBuffer()));
}
await fs.writeFile(path.join(outputDir, "workbook_inspection.json"), JSON.stringify(inspection, null, 2));

const formulaAudit = await workbook.inspect({ kind: "formula", sheetId: "Comparison", range: "A1:L30", maxChars: 8000 });
await fs.writeFile(path.join(outputDir, "formula_audit.ndjson"), formulaAudit.ndjson ?? "");

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, "BOS_SEMANTIC_AUDIT.xlsx"));
console.log(JSON.stringify({ output: path.join(outputDir, "BOS_SEMANTIC_AUDIT.xlsx"), sheets: sheetNames }, null, 2));
