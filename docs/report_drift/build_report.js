// KAIROS Capstone Project-I report, laid out like DRIFT_Project_Report.pdf
// (page border, logo header, certificate/declaration, chapter-numbered tables and figures
// with captions below, uppercase chapter headings).  node build_report.js <out.docx>
const fs = require("fs");
const path = require("path");
const D = require("docx");
const { byKey } = require("./refs");

const OUT = process.argv[2];
if (!OUT || !/\.docx$/i.test(OUT)) throw new Error("usage: node build_report.js <out.docx>");
const FIG = path.resolve(__dirname, "..", "report", "figures");
const FONT = "Times New Roman";
const SZ = 24;                 // 12 pt body
const LINE = 312;              // 1.3 line spacing
const CONTENT_W = 9360;        // Letter 8.5" − 2 × 1" margins, in DXA

// ── project facts ───────────────────────────────────────────────────────────
const TITLE = "KAIROS: An Autonomous Causal Business Intelligence Agent for Proactive Multi-Source Metric Monitoring and Root Cause Analysis";
const TEAM = [["Palla Chetana Reddy", "23WU0104050"], ["Varshini Yadav Nasaram", "23WU0104067"], ["Obulagari Nandini", "23WU0104049"]];
const GUIDE = "Dr. K RajKumar";
const GUIDE_DESIG = "Assistant Professor";
const DATE = "07-10-2026";

// ── citations: write {key} in text, numbered by first appearance ───────────
const citeOrder = [];
function cite(text) {
  return text.replace(/\{([a-z0-9_,\s]+)\}/g, (whole, keys) => {
    const ks = keys.split(",").map((k) => k.trim());
    if (!ks.every((k) => byKey[k])) return whole;      // e.g. "/sources/{name}/sync" in API paths
    return ks.map((k) => {
    if (!citeOrder.includes(k)) citeOrder.push(k);
    return `[${citeOrder.indexOf(k) + 1}]`;
    }).join(", ");
  });
}

// ── inline markup: **bold**, *italic*, `code` ──────────────────────────────
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0, m;
  const mk = (t, extra = {}) => new D.TextRun({ font: FONT, size: SZ, ...base, ...extra, text: t });
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(mk(text.slice(last, m.index)));
    const t = m[0];
    if (t.startsWith("**")) out.push(mk(t.slice(2, -2), { bold: true }));
    else if (t.startsWith("`")) out.push(mk(t.slice(1, -1), { font: "Consolas", size: (base.size || SZ) - 4 }));
    else out.push(mk(t.slice(1, -1), { italics: true }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(mk(text.slice(last)));
  return out;
}

// ── figure / table numbering by chapter ─────────────────────────────────────
const FIGS = {
  3: ["arch", "pipeline", "ingest", "transfer", "gantt"],
  4: ["ui_a", "ui_b", "bench", "detect", "causal_eval", "ui_causal"],
};
const TABS = {
  1: ["scope"],
  2: ["tr_a", "tr_b", "tr_c", "compare", "gaps"],
  3: ["smart", "tools"],
  4: ["tests", "demo", "bench", "detect", "causal", "sens", "verifier"],
  5: ["achieved"],
};
const num = (map, key, label) => {
  for (const [ch, keys] of Object.entries(map)) {
    const i = keys.indexOf(key);
    if (i >= 0) return ch === "0" ? `C.${i + 1}` : `${ch}.${i + 1}`;
  }
  throw new Error(`unknown ${label} ${key}`);
};
const F = (k) => `Figure ${num(FIGS, k, "figure")}`;
const T = (k) => `Table ${num(TABS, k, "table")}`;

// ── paragraph builders ──────────────────────────────────────────────────────
const words = [];
function P(text, opts = {}) {
  const t = cite(text);
  if (opts.count !== false) words.push(t);
  return new D.Paragraph({
    alignment: opts.align || D.AlignmentType.JUSTIFIED,
    spacing: { line: opts.line || LINE, after: opts.after ?? 120, before: opts.before || 0 },
    keepNext: opts.keepNext,
    children: runs(t, opts.run || {}),
  });
}
function bullets(items, ref = "bullets") {
  return items.map((raw) => {
    const t = cite(raw);
    words.push(t);
    return new D.Paragraph({ numbering: { reference: ref, level: 0 }, alignment: D.AlignmentType.JUSTIFIED, spacing: { line: LINE, after: 40 }, children: runs(t) });
  });
}
const H1 = (t, pageBreak = false) => new D.Paragraph({ heading: D.HeadingLevel.HEADING_1, pageBreakBefore: pageBreak, keepNext: true, spacing: { before: 360, after: 160, line: 300 }, children: [new D.TextRun({ text: t.toUpperCase(), font: FONT, size: 32, bold: true })] });
const H2 = (t) => new D.Paragraph({ heading: D.HeadingLevel.HEADING_2, keepNext: true, spacing: { before: 240, after: 100, line: 300 }, children: [new D.TextRun({ text: t, font: FONT, size: 28, bold: true })] });
const H3 = (t) => new D.Paragraph({ heading: D.HeadingLevel.HEADING_3, keepNext: true, spacing: { before: 180, after: 60, line: 300 }, children: [new D.TextRun({ text: t, font: FONT, size: 24, bold: true })] });
const pageTitle = (t, pageBreak = true) => new D.Paragraph({ heading: D.HeadingLevel.HEADING_1, pageBreakBefore: pageBreak, alignment: D.AlignmentType.CENTER, spacing: { before: 240, after: 320 }, children: [new D.TextRun({ text: t, font: FONT, size: 28, bold: true })] });
const blank = (after = 120) => new D.Paragraph({ spacing: { after }, children: [] });
const center = (t, size = SZ, o = {}) => new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { before: o.before || 0, after: o.after ?? 80, line: 276 }, children: [new D.TextRun({ text: t, font: FONT, size, bold: o.bold, italics: o.italics })] });

function pngSize(file) { const b = fs.readFileSync(file); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; }
function caption(kind, number, text) {
  return new D.Paragraph({
    style: kind === "Figure" ? "FigCaption" : "TabCaption", alignment: D.AlignmentType.CENTER,
    spacing: { before: 60, after: 240, line: 240 },
    children: [new D.TextRun({ text: `${kind} ${number}: `, font: FONT, size: 20, bold: true }), ...runs(cite(text), { size: 20 })],
  });
}
function figure(key, file, widthIn, text) {
  const full = path.join(FIG, file);
  const { w, h } = pngSize(full);
  const wpx = Math.round(widthIn * 96);
  return [
    new D.Paragraph({ alignment: D.AlignmentType.CENTER, keepNext: true, spacing: { before: 160, after: 40, line: 240 },
      children: [new D.ImageRun({ type: "png", data: fs.readFileSync(full), transformation: { width: wpx, height: Math.round((wpx * h) / w) } })] }),
    caption("Figure", num(FIGS, key, "figure"), text),
  ];
}
function figurePair(key, a, b, text) {
  const none = { style: D.BorderStyle.NONE, size: 0, color: "FFFFFF" };
  const cell = ([file, label]) => {
    const full = path.join(FIG, file), { w, h } = pngSize(full), wpx = Math.round(3.0 * 96);
    return new D.TableCell({ width: { size: CONTENT_W / 2, type: D.WidthType.DXA }, borders: { top: none, bottom: none, left: none, right: none }, margins: { left: 40, right: 40 },
      children: [
        new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { after: 20 }, children: [new D.ImageRun({ type: "png", data: fs.readFileSync(full), transformation: { width: wpx, height: Math.round((wpx * h) / w) } })] }),
        new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { after: 0, line: 240 }, children: runs(label, { size: 18 }) }),
      ] });
  };
  return [
    new D.Table({ width: { size: CONTENT_W, type: D.WidthType.DXA }, columnWidths: [CONTENT_W / 2, CONTENT_W / 2], borders: D.TableBorders.NONE, alignment: D.AlignmentType.CENTER,
      rows: [new D.TableRow({ cantSplit: true, children: [cell(a), cell(b)] })] }),
    caption("Figure", num(FIGS, key, "figure"), text),
  ];
}

function table(key, text, headers, rows, widths, o = {}) {
  const scale = CONTENT_W / widths.reduce((a, b) => a + b, 0);
  const W = widths.map((w) => Math.round(w * scale));
  W[W.length - 1] += CONTENT_W - W.reduce((a, b) => a + b, 0);
  const border = { style: D.BorderStyle.SINGLE, size: 4, color: "7F7F7F" };
  const borders = { top: border, bottom: border, left: border, right: border };
  const size = o.size || 20;
  const cell = (t, i, head) => new D.TableCell({
    width: { size: W[i], type: D.WidthType.DXA }, borders,
    shading: head ? { fill: "D9E2F3", type: D.ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 40, bottom: 40, left: 80, right: 80 }, verticalAlign: D.VerticalAlign.CENTER,
    children: String(cite(String(t))).split("\n").map((line) => new D.Paragraph({
      alignment: head ? D.AlignmentType.CENTER : ((o.align && o.align[i]) || D.AlignmentType.LEFT),
      spacing: { line: 240, after: 0 },
      children: runs(line, { size, bold: head || (o.boldFirst && i === 0) || undefined }),
    })),
  });
  const tbl = new D.Table({
    width: { size: CONTENT_W, type: D.WidthType.DXA }, columnWidths: W, alignment: D.AlignmentType.CENTER,
    rows: [new D.TableRow({ tableHeader: true, cantSplit: true, children: headers.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r) => new D.TableRow({ cantSplit: true, children: r.map((v, i) => cell(v, i, false)) }))],
  });
  if (!key) return [tbl, blank(160)];
  return [tbl, caption("Table", num(TABS, key, "table"), text)];
}
function code(lines) {
  return lines.map((l, i) => new D.Paragraph({
    spacing: { line: 240, after: 0 }, keepLines: true, keepNext: i < lines.length - 1,
    shading: { fill: "F2F2F2", type: D.ShadingType.CLEAR, color: "auto" },
    children: [new D.TextRun({ text: l.length ? l : " ", font: "Consolas", size: 17 })],
  })).concat([blank(160)]);
}

// ════════════════════════════════════════════════════════════════════════════
// FRONT MATTER
// ════════════════════════════════════════════════════════════════════════════
const titlePage = [
  blank(600),
  center("WOXSEN UNIVERSITY", 36, { bold: true, after: 80 }),
  center("SCHOOL OF TECHNOLOGY", 26, { bold: true, after: 720 }),
  center("A PROJECT REPORT", 28, { bold: true, after: 60 }),
  center("on", 22, { italics: true, after: 240 }),
  center(TITLE.toUpperCase(), 30, { bold: true, after: 240 }),
  center("Capstone Project-I", 24, { italics: true, after: 600 }),
  center("Bachelor of Technology (B.Tech.)", 24, { bold: true, after: 60 }),
  center("Computer Science and Engineering", 24, { after: 480 }),
  center("Submitted by", 24, { bold: true, after: 120 }),
  ...TEAM.map(([n, r]) => center(`${n} – ${r}`, 24, { after: 60 })),
  center("Under the guidance of", 24, { bold: true, before: 400, after: 120 }),
  center(GUIDE, 24, { after: 60 }),
  center(GUIDE_DESIG + ",", 24, { after: 60 }),
  center("Woxsen University.", 24, { after: 600 }),
  center("School of Technology, Woxsen University, Hyderabad", 24, { after: 60 }),
  center("October 2026", 24, { after: 0 }),
];

const teamInline = TEAM.map(([n, r]) => `${n} (${r})`).join(", ");
const certificate = [
  pageTitle("CERTIFICATE", false),
  P(`This is to certify that the project report entitled **“${TITLE}”** submitted by ${teamInline}, Bachelor of Technology, Woxsen University, is a bonafide record of work carried out by the students under my supervision and guidance in the course Capstone Project-I during the 7th semester of the academic year 2026–2027. The work embodied in this report has not been submitted elsewhere for a degree.`, { count: false }),
  blank(1600),
  P("Signature of Mentor", { count: false, align: D.AlignmentType.LEFT, after: 40 }),
  P(`Name: ${GUIDE}`, { count: false, align: D.AlignmentType.LEFT, after: 40 }),
  P(`Designation: ${GUIDE_DESIG}`, { count: false, align: D.AlignmentType.LEFT, after: 40 }),
  P(`Date: ${DATE}`, { count: false, align: D.AlignmentType.LEFT, after: 40 }),
];

const declaration = [
  pageTitle("DECLARATION OF THE CANDIDATES"),
  P(`We hereby declare that the project work entitled **“${TITLE}”** submitted to the School of Technology, Woxsen University, for the degree of Bachelor of Technology is our original work, carried out under the guidance of ${GUIDE}. We further declare that the work reported in this project has not been submitted and will not be submitted, either in part or in full, for the award of any other degree or diploma in this institute or any other institute or university.`, { count: false }),
  blank(600),
  ...TEAM.flatMap(([n, r]) => [
    P("Signature of Student", { count: false, align: D.AlignmentType.LEFT, after: 20, line: 276 }),
    P(`Name: ${n}`, { count: false, align: D.AlignmentType.LEFT, after: 20, line: 276 }),
    P(`Roll Number: ${r}`, { count: false, align: D.AlignmentType.LEFT, after: 480, line: 276 }),
  ]),
  P(`Date: ${DATE}`, { count: false, align: D.AlignmentType.LEFT }),
];

const acknowledgment = [
  pageTitle("ACKNOWLEDGMENT"),
  P(`We express our sincere gratitude to our project guide, ${GUIDE}, for the guidance, feedback and encouragement provided throughout this project, and for the questions raised during the reviews that shaped the most important parts of this work. We thank the evaluation panel of the second review, whose comments on data ingestion and large-file transfer led directly to the ingestion layer and the Fast Transfer service described in this report.`, { count: false }),
  P("We thank the School of Technology, Woxsen University, for the computing resources, library access and the opportunity to carry out the Capstone Project. We acknowledge the open-source communities behind DuckDB, FastAPI, LangGraph, Prophet, DoWhy, causal-learn, pandas, React and Recharts, and the authors of the DYNOTEARS and LLM-Modulo papers, without whom this work would not have been possible. Classmates who tried early versions of the dashboard gave useful feedback on its design. Finally, we thank our families and friends for their patience and support.", { count: false }),
  blank(240),
  ...TEAM.map(([n]) => P(n, { count: false, align: D.AlignmentType.LEFT, after: 20, line: 276 })),
];

const ABSTRACT = [
  "Business intelligence (BI) tools such as Power BI and Tableau answer questions only after a person opens a dashboard and asks one. Problems can stay unnoticed for hours, and the explanations these tools offer are correlations rather than causes. This project presents **KAIROS**, an autonomous five-agent system that watches business metrics from many sources, detects anomalies, traces them to their causal origin and sends a verified plain-English alert without being asked.",
  "Data enters through five lightweight protocol adapters (SQL, SFTP/FTP, files and object storage, REST and push), with aggregation pushed down to the source and a chunked, parallel, resumable transfer service for large files. Anomalies are scored with a robust seasonal z-score and an optional Prophet ensemble, DYNOTEARS learns a lagged causal graph of the metrics, and an LLM-Modulo verifier checks every number in the generated report before it is sent.",
  "On a synthetic benchmark with known ground truth, causal discovery reached an F1 score of 0.97 against 0.90 for Granger regression and 0.50 for correlation, and the true incident origin was identified in all ten runs. A 106 MB raw export was transferred 6.4 times faster than single-stream FTP, or reduced to 193 KB by edge aggregation. The verifier caught 98.5% of corrupted numbers. The whole system runs on free, open-source software.",
];
const abstract = [
  pageTitle("ABSTRACT"),
  ...ABSTRACT.map((t) => P(t, { count: false })),
  P("**Keywords:** proactive business intelligence, anomaly detection, causal discovery, DYNOTEARS, root cause analysis, multi-agent systems, LLM verification, data ingestion.", { count: false, before: 120, align: D.AlignmentType.LEFT }),
];

const tocField = (styles) => new D.TableOfContents("Contents", { hyperlink: true, ...(styles ? { stylesWithLevels: styles } : { headingStyleRange: "1-2" }) });
const lists = [
  pageTitle("TABLE OF CONTENTS"), tocField(),
  pageTitle("LIST OF TABLES"), tocField([new D.StyleLevel("TabCaption", 1)]),
  pageTitle("LIST OF FIGURES", false), tocField([new D.StyleLevel("FigCaption", 1)]),
];

const ABBR = [
  ["API", "Application Programming Interface"], ["BI", "Business Intelligence"], ["CBMG", "Causal Business Metric Graph"],
  ["CDC", "Change Data Capture"], ["CSV", "Comma-Separated Values"], ["DAG", "Directed Acyclic Graph"],
  ["DYNOTEARS", "Dynamic NOTEARS (structure learning for time series)"], ["ELT", "Extract, Load, Transform"],
  ["FTP / SFTP", "File Transfer Protocol / SSH File Transfer Protocol"], ["KPI", "Key Performance Indicator"],
  ["LLM", "Large Language Model"], ["MAD", "Median Absolute Deviation"], ["ProBI", "Proactive Business Intelligence"],
  ["RCA", "Root Cause Analysis"], ["REST", "Representational State Transfer"], ["SHD", "Structural Hamming Distance"],
  ["SLAC", "Semantic Layer Auto-Construction"], ["SMART", "Specific, Measurable, Achievable, Relevant, Time-bound"],
  ["SVAR", "Structural Vector Autoregression"], ["WAN", "Wide Area Network"],
];
const abbreviations = [pageTitle("LIST OF ABBREVIATIONS"), ...table(null, "", ["Abbreviation", "Expansion"], ABBR, [2400, 6960], { boldFirst: true, size: 20 })];

// ════════════════════════════════════════════════════════════════════════════
// CHAPTER 1
// ════════════════════════════════════════════════════════════════════════════
const ch1 = [
  H1("1. Introduction", true),
  P("Most organisations now hold their operating data in several places at once: an ERP database for orders, spreadsheets kept by the customer-support team, CSV exports from marketing tools, and REST APIs offered by logistics or payment providers. Business intelligence (BI) platforms such as Microsoft Power BI and Tableau {powerbi} bring this data together into dashboards and have become standard equipment for managers. Their working model, however, has not changed in two decades: a person opens a dashboard, looks at a chart and decides whether something is wrong. If nobody looks, nothing is found."),
  H2("1.1 Background"),
  P("Two developments make a different model possible. Time-series anomaly detection has matured to the point where seasonal business metrics can be monitored automatically {prophet, leys, chandola}. Causal discovery methods such as NOTEARS and its time-series extension DYNOTEARS learn directed, lagged relationships between variables from observational data {notears, dynotears}. Large language models (LLMs) {gpt3} can turn numerical findings into readable text, although they are known to state numbers that are not in their input {halluc}. Agent designs built on the ReAct pattern {react} and graph-based orchestration {langgraph} make it practical to chain these steps into one autonomous loop."),
  H2("1.2 Problem Statement"),
  P("Current BI practice has three linked weaknesses. First, monitoring is reactive: an incident that starts on a Friday evening may only be seen on Monday. Second, the explanation features that do exist, such as Key Influencers in Power BI or Explain Data in Tableau, rank correlated fields and cannot say which metric moved first or which one caused the other. Third, connecting the data is expensive: managed ELT services charge by data volume, every company uses a different mix of systems, and moving large exports over FTP is slow."),
  P("During the second evaluation of this project, the review panel asked specifically how data from any source would be transferred, given that connectors are heavy and costly and FTP is slow for large files. The problem addressed is therefore to build a system that monitors multi-source business metrics without human initiation, identifies the causal origin of an anomaly, explains it accurately, and ingests data from heterogeneous systems at negligible cost."),
  H2("1.3 Significance"),
  P("Small and mid-sized businesses benefit most, because they rarely have a data team watching dashboards around the clock. Earlier detection shortens the time between a fault, such as a paused advertising campaign or a warehouse delay, and the corrective action. A causal explanation saves analysts the manual work of tracing a chain of related metrics. Because KAIROS uses only free software and moves aggregated metrics instead of raw tables, its running cost stays close to zero."),
  H2("1.4 Scope"),
  P(`The boundaries of the project are summarised in ${T("scope")}. Evaluation uses a synthetic benchmark with a known causal structure, because real company data with labelled root causes was not available within the semester.`),
  ...table("scope", "Scope of Capstone Project-I", ["Included", "Excluded"], [
    ["Numeric business metrics as time series (hourly or finer)", "Unstructured data such as text, images or documents"],
    ["Ingestion from SQL, SFTP/FTP, files and object storage, REST and push clients", "Streaming below one-minute latency"],
    ["Anomaly detection, causal discovery and root-cause ranking", "Multi-tenant deployment and billing"],
    ["Verified report generation; Telegram, e-mail and dashboard delivery", "User study with business staff"],
    ["Edge aggregation and a resumable transfer service for large files", "Deep anomaly models (Anomaly Transformer)"],
  ], [4680, 4680]),
  H2("1.5 Organisation of the Report"),
  P("Chapter 2 reviews existing technologies and identifies the research gap. Chapter 3 states the objectives and describes the methodology, architecture and novelty. Chapter 4 presents the implementation, testing and results. Chapter 5 concludes with limitations, lessons learned and the plan for Capstone Project-II."),
];

// ════════════════════════════════════════════════════════════════════════════
// CHAPTER 2
// ════════════════════════════════════════════════════════════════════════════
const CRIT = ["Description", "Key features", "Performance", "Scalability", "Cost / licensing", "Compatibility", "Ease of use", "Security", "Current market", "Limitations", "Relevance to project"];
const trRows = (cols) => CRIT.map((k, i) => [k, ...cols.map((c) => c[i])]);
const TRW = [1500, 1965, 1965, 1965, 1965];
const trA = trRows([
  ["Microsoft BI and reporting platform {powerbi}.", "Power Query connectors, DAX, Key Influencers, anomaly markers per chart.", "In-memory engine; interactive on millions of rows.", "Premium capacity for large datasets.", "Desktop free; Pro and Premium subscriptions.", "Windows, web, mobile; hundreds of connectors.", "Easy for charts; DAX is harder.", "Azure AD, row-level security, encryption.", "A market leader in enterprise BI.", "Reactive; explanations are correlational.", "Baseline of reactive BI; not used."],
  ["Visual analytics platform owned by Salesforce.", "Drag-and-drop visuals, Explain Data, Pulse digests.", "Hyper engine; fast extracts.", "Server and Cloud editions.", "Creator, Explorer and Viewer subscriptions.", "Windows, macOS, web; many connectors.", "Moderate; strong community.", "SSO, row-level security.", "Widely used in enterprises.", "Explain Data lists factors, not causal chains.", "Baseline; not used."],
  ["Additive forecasting model from Meta {prophet}.", "Trend, daily and weekly seasonality, uncertainty intervals.", "Seconds per series on a laptop.", "One model per series; parallelisable.", "Free, MIT licence.", "Python and R; Stan backend.", "Easy; few parameters.", "Library only.", "Popular for business forecasting.", "Univariate; slower than robust statistics.", "Optional ensemble member in Agent 2."],
  ["Transformer for unsupervised time-series anomaly detection {anomtrans}.", "Association discrepancy, minimax training.", "Strong results on public benchmarks.", "Needs GPU training per dataset.", "Free research code.", "Python, PyTorch.", "Hard; research-grade code.", "Not applicable.", "Academic use.", "Long training windows; tuning per metric.", "Studied; deferred to Capstone-II."],
]);
const trB = trRows([
  ["QuantumBlack library for causal reasoning, including DYNOTEARS {dynotears}.", "Structure learning, Bayesian networks, lagged graphs.", "Optimisation-based; fine for tens of variables.", "Cost grows cubically with variables.", "Free, Apache 2.0.", "Pins older Python and pandas versions.", "Moderate.", "Library only.", "Niche, mainly consulting use.", "Dependency conflicts with current stack.", "Algorithm adopted; re-implemented in NumPy/SciPy."],
  ["Tigramite package implementing PCMCI {pcmci}.", "Lagged conditional-independence tests, nonlinear tests.", "Heavy with nonlinear tests.", "Tens of variables.", "Free, GPL-3.0.", "Python.", "Moderate; good documentation.", "Library only.", "Popular in climate science.", "Copyleft licence; slow nonlinear tests.", "Candidate for Capstone-II comparison."],
  ["PyWhy library for causal effect estimation {dowhy}.", "Model, identify, estimate, refute workflow.", "Fast for linear estimators.", "Per-effect estimation.", "Free, MIT.", "Python; pandas input.", "Clear API.", "Library only.", "Widely cited in causal ML.", "Needs a graph as input; does not discover one.", "Estimates effects on discovered edges."],
  ["Graph-based orchestration for LLM agents {langgraph}.", "Typed state, conditional edges, retries.", "Negligible overhead.", "Single process or server.", "Free, MIT.", "Python and JavaScript.", "Moderate.", "No built-in auth.", "Fast-growing agent ecosystem.", "API changes between major versions.", "Orchestrates the five agents."],
]);
const trC = trRows([
  ["In-process analytical SQL database {duckdb}.", "Columnar, vectorised; reads CSV, Parquet, JSON and S3 directly.", "Tens of millions of rows per second on one core.", "Larger-than-memory processing.", "Free, MIT.", "Python, R, Java, Node; no server.", "Easy; standard SQL.", "File-level; no user management.", "Rapidly growing adoption.", "Single node; one writer process.", "Metric store and file engine."],
  ["Managed ELT service {fivetran}.", "Hundreds of maintained connectors, schema-drift handling.", "Reliable scheduled syncs.", "Fully managed.", "Priced per monthly active row.", "Cloud warehouses as destination.", "Very easy.", "SOC 2, encryption.", "Market leader in managed ELT.", "Cost grows with volume; copies whole tables.", "Rejected on cost."],
  ["Open-source ELT platform {airbyte}.", "Large connector catalogue, connector builder.", "Depends on connector.", "Kubernetes deployment.", "Open-source core; paid cloud.", "Docker or Kubernetes required.", "Heavy to self-host.", "Self-managed.", "Large open-source community.", "Several containers per sync.", "Optional route for rare systems."],
  ["IBM high-speed transfer based on FASP {aspera}.", "UDP transfer, rate control, resume, encryption.", "Near line rate on long links.", "Enterprise scale.", "Proprietary, licensed.", "Dedicated clients and servers.", "Moderate.", "Encryption in transit and at rest.", "Media and life sciences.", "Licence cost; proprietary protocol.", "Design reference for Fast Transfer."],
]);

const ch2 = [
  H1("2. Technology Review"),
  H2("2.1 Review Method"),
  P(`Twelve technologies were reviewed across the functions KAIROS needs: analytics and anomaly detection, causal analysis and orchestration, and data storage and transfer. Each was assessed on the eleven criteria set by the Capstone guidelines, using vendor documentation, the original research papers and hands-on trials where the software was freely available. Similar technologies are compared side by side in ${T("tr_a")}, ${T("tr_b")} and ${T("tr_c")}.`),
  H2("2.2 Related Technologies"),
  ...table("tr_a", "Technology review: BI platforms and anomaly detection", ["Criterion", "Power BI", "Tableau", "Prophet", "Anomaly Transformer"], trA, TRW, { size: 17, boldFirst: true }),
  ...table("tr_b", "Technology review: causal analysis and agent orchestration", ["Criterion", "CausalNex (DYNOTEARS)", "Tigramite (PCMCI)", "DoWhy", "LangGraph"], trB, TRW, { size: 17, boldFirst: true }),
  ...table("tr_c", "Technology review: storage, ingestion and transfer", ["Criterion", "DuckDB", "Fivetran", "Airbyte", "IBM Aspera"], trC, TRW, { size: 17, boldFirst: true }),
  H2("2.3 Comparison and Analysis"),
  P("The commercial BI platforms are strong at presenting data but share one interaction model: they wait for a question. Their automated explanations are useful starting points, yet Key Influencers and Explain Data rank fields by statistical association, which cannot separate a cause from its effect or from a common driver {pearl}. Root-cause tools from the AIOps field, such as CloudRanger {cloudranger}, MicroCause {microcause} and RCD {rcd}, do use causal graphs, but they are built for microservice telemetry such as latency and error rates, and assume engineers as users. None of them produces business-facing explanations or reads ERP tables and spreadsheets."),
  P(`Among causal discovery methods, Granger-style regression {granger} is fast but tends to add edges between variables that share a driver. VARLiNGAM {varlingam} learns lagged structure but relies on non-Gaussian noise, and PCMCI handles nonlinearity at a higher computational cost and under a copyleft licence. DYNOTEARS learns same-step and lagged edges together under an acyclicity constraint, which suits business metrics whose effects arrive with a delay. On the ingestion side, the choice is between paying per row, running a heavy self-hosted platform, or writing custom code, while transfer tools such as Aspera solve the large-file problem but are proprietary. ${T("compare")} summarises how existing approaches cover the requirements identified in Chapter 1.`),
  ...table("compare", "Coverage of project requirements by existing approaches", ["Requirement", "Dashboards (Power BI, Tableau)", "AIOps RCA tools", "ELT platforms", "KAIROS"], [
    ["Monitoring without a human request", "Partial (threshold alerts)", "Yes", "No", "Yes"],
    ["Directed, lagged causal explanation", "No (correlational)", "Yes (IT metrics)", "No", "Yes (business metrics)"],
    ["Plain-English report with fact checking", "No", "No", "No", "Yes"],
    ["Low-cost multi-source ingestion", "Licensed connectors", "No", "Paid or heavy", "Free and lightweight"],
    ["Large-file transfer strategy", "No", "No", "Bulk copy", "Push-down, edge, Fast Transfer"],
  ], [2500, 1800, 1550, 1550, 1960], { boldFirst: true, size: 19 }),
  H2("2.4 Review Summary"),
  P("Three findings stand out. Monitoring, causal reasoning and narrative explanation exist separately in different tools, but no reviewed product combines them for business metrics. The open-source building blocks are mature and free: robust statistics and Prophet for detection, DYNOTEARS and DoWhy for causality, LangGraph for orchestration and DuckDB for storage. The cost of moving data depends mainly on how much is copied rather than on the protocol {kleppmann}, so a design that moves aggregated metrics instead of raw rows can avoid both licence fees and long transfers."),
  H2("2.5 Research Gap"),
  P(`The gaps found in the review are grouped by category in ${T("gaps")}, with the evidence for each and the corresponding response in KAIROS.`),
  ...table("gaps", "Research gaps identified from the technology review", ["Category", "Gap in existing systems", "Evidence", "KAIROS response"], [
    ["Functional", "BI tools do not monitor on their own initiative", "Power BI and Tableau need a user session", "Scheduled five-agent pipeline (ProBI)"],
    ["Technical", "Explanations are correlational, not causal or lagged", "Key Influencers, Explain Data", "DYNOTEARS causal graph (CBMG) with lag-aware ranking"],
    ["Reliability", "LLM narratives can state wrong numbers", "Hallucination survey {halluc}", "LLM-Modulo verifier on every report"],
    ["Usability", "Each new source needs manual schema mapping", "ELT and semantic layers are hand-modelled", "SLAC infers timestamp, shape and metrics"],
    ["Cost", "Connectors priced by volume or heavy to host", "Fivetran pricing, Airbyte deployment", "Five protocol adapters; aggregation at source"],
    ["Performance", "Single-stream FTP is slow for large files", "TCP throughput limits {mathis}", "Edge aggregation; parallel, resumable Fast Transfer"],
  ], [1400, 2700, 2400, 2860], { boldFirst: true, size: 19 }),
];

// ════════════════════════════════════════════════════════════════════════════
// CHAPTER 3
// ════════════════════════════════════════════════════════════════════════════
const ch3 = [
  H1("3. Objectives and Methodology"),
  H2("3.1 Project Objectives"),
  P(`Five SMART objectives were set at the start of the semester and revised after the mid-term review, when the ingestion questions were raised. They are listed in ${T("smart")}.`),
  ...table("smart", "SMART objectives of the project", ["No.", "Objective", "Measure of success", "Deadline"], [
    ["O1", "Build a five-agent pipeline that runs every 15 minutes without human initiation and stores data idempotently", "Cycle under 30 s for 15 metrics; no duplicate rows on re-runs", "Week 8"],
    ["O2", "Detect injected anomalies in seasonal business metrics", "Event recall ≥ 95%; point precision ≥ 70%", "Week 10"],
    ["O3", "Identify the causal origin of an incident", "Causal F1 ≥ 0.85; origin correct in ≥ 90% of runs", "Week 10"],
    ["O4", "Generate executive reports whose numbers are verified before delivery", "≥ 95% of numeric misstatements caught", "Week 11"],
    ["O5", "Ingest from at least four source types at low cost and handle large files", "Incremental sync; a 100 MB export moved ≥ 3× faster than single-stream FTP", "Week 11"],
  ], [700, 3900, 3500, 1260], { align: [D.AlignmentType.CENTER, undefined, undefined, D.AlignmentType.CENTER], size: 19 }),
  H2("3.2 Proposed Approach"),
  P("Development followed two-week Agile sprints with a working build at the end of each sprint. The first sprints produced the five agents and the dashboard shown at the mid-term review. After that review, the work concentrated on the ingestion layer, the causal engine and report verification. Quality was maintained through automated tests that run on every change, code review within the team, and benchmark scripts that regenerate every reported number from scratch."),
  H2("3.3 System Architecture"),
  P(`The overall architecture is shown in ${F("arch")}. Data from five kinds of sources passes through an ingestion layer into a DuckDB store. Five agents then run in sequence under a LangGraph state machine, triggered every 15 minutes by a background scheduler. A FastAPI {fastapi} service exposes every function, and a React dashboard sits on top of it.`),
  ...figure("arch", "fig_architecture.png", 5.0, "KAIROS system architecture"),
  P(`The control flow of one monitoring cycle appears in ${F("pipeline")}. The graph stops after detection when no new alert-worthy anomaly is found, so a quiet cycle costs a fraction of a second and no alert is ever repeated.`),
  ...figure("pipeline", "fig_pipeline.png", 5.3, "LangGraph state machine for one monitoring cycle"),
  H3("3.3.1 Agent 1: Data Collector"),
  P("Every source implements one contract, `fetch(state)`, which returns rows in a canonical form (metric name, value, timestamp) together with an updated state. The state holds a watermark or the list of files already processed, so each cycle reads only new data. Rows are written with an upsert on the key (source, metric, timestamp), so a repeated sync updates values instead of duplicating them, a property that makes retries safe in any data pipeline {kleppmann}. Sources run in parallel with a timeout each, so one slow system cannot delay the others."),
  H3("3.3.2 Agent 2: Anomaly Watchman"),
  P("Each series is compared with an expected value made of a centred rolling median (the local level) plus an hour-of-day profile, which is kept only when it explains a meaningful share of the variation. The residual is scaled by the median absolute deviation (MAD), giving a robust z-score z = (x − m) / (1.4826 × MAD) that is not distorted by the anomalies it is looking for {leys}. Points with |z| ≥ 3.5 are flagged; severity is low below 4.5, medium from 4.5, high from 6 and critical from 9 robust standard deviations. Prophet {prophet} can be enabled as a second detector. Every anomaly is stored, so it is reported as new exactly once."),
  H3("3.3.3 Agent 3: Causal Investigator"),
  P("The metrics are aligned on a common time grid, winsorised so that the anomalies do not distort the learned structure, and standardised. DYNOTEARS {dynotears} then fits the structural vector autoregression X_t = X_t W + X_(t−1) A + e, where W holds same-step effects and A holds one-step lagged effects. It minimises the squared residual plus L1 penalties subject to the acyclicity constraint h(W) = tr(e^(W∘W)) − d = 0 {notears}, using an augmented Lagrangian with L-BFGS-B. Edges with weight of at least 0.15 form the Causal Business Metric Graph (CBMG), and edge confidence is the share of bootstrap refits that keep each edge."),
  P("For each anomalous metric, the agent walks back through its ancestors in the CBMG and scores each chain by strength, confidence and whether the cause itself was anomalous shortly before the effect. An anomalous cause with no anomalous upstream cause is marked as the origin. DoWhy {dowhy} then estimates the size of each direct effect."),
  H3("3.3.4 Agent 4: NL Reporter"),
  P("A prompt containing only computed facts is sent to an LLM, using the Groq API first and a local Ollama model as a fallback. Following the LLM-Modulo pattern {modulo}, the draft is checked by a deterministic verifier: every number must match a computed fact at the precision written, and every metric name must exist. A failed draft is returned once with the list of errors; if it fails again, a template report that is correct by construction is used instead."),
  H3("3.3.5 Agent 5: Messenger"),
  P("The verified report is sent through the Telegram Bot API {telegram} and e-mail and stored in an alert history shown on the dashboard. A cooldown prevents repeated alerts for the same metric."),
  H3("3.3.6 Ingestion Strategy for Any Source"),
  P(`The ingestion design answers the review question directly. Instead of one connector per product, KAIROS implements five protocol adapters that together cover almost any system. The guiding principle is to move the computation rather than the data. For a large table, the aggregation query runs inside the source database. For large raw files, a small edge agent aggregates them next to the data and pushes only KPIs. For small scheduled exports, SFTP/FTP {rfc959} fetches only files that have not been seen before. ${F("ingest")} shows how a source is routed. The Semantic Layer Auto-Construction (SLAC) module inspects a sample of any new source and proposes its mapping (timestamp column, long or wide shape, metric columns, and whether raw records need aggregation), which removes most of the manual setup.`),
  ...figure("ingest", "fig_ingestion.png", 5.6, "Ingestion routes by data location and size, with measured results"),
  P(`When a raw file must move, the Fast Transfer service is used (${F("transfer")}). The file is split into chunks; each chunk is compressed with gzip or Zstandard {zstd}, hashed, and sent in parallel with other chunks. A single TCP stream is limited by its window size and round-trip time {mathis}, so parallel streams use more of the link {hacker}. If the connection drops, the client asks which chunks are missing and sends only those. The server verifies each chunk, writes it in place and re-hashes the whole file before accepting it.`),
  ...figure("transfer", "fig_fast_transfer.png", 4.6, "Fast Transfer protocol, including resume after a dropped connection"),
  H2("3.4 Tools and Technologies"),
  P(`The tools selected after the review are listed in ${T("tools")}. All of them are free and open source.`),
  ...table("tools", "Tools and technologies used", ["Layer", "Tools"], [
    ["Languages", "Python 3.13, JavaScript (ES2022), SQL"],
    ["Backend and orchestration", "FastAPI, Uvicorn, LangGraph, APScheduler, Pydantic"],
    ["Data and storage", "DuckDB, pandas, PyArrow, SQLAlchemy"],
    ["Detection and causality", "NumPy, SciPy (DYNOTEARS), Prophet, DoWhy, causal-learn (VARLiNGAM baseline), NetworkX"],
    ["LLM and delivery", "Groq API, Ollama (Llama 3.1 8B), Telegram Bot API, Gmail SMTP"],
    ["Connectors and transfer", "paramiko (SFTP), ftplib (FTP), httpx (REST), gspread (Sheets), zstandard, gzip"],
    ["Frontend", "React 18, Vite, Tailwind CSS, Recharts"],
    ["Testing and tooling", "pytest, pyftpdlib (test FTP server), Docker, Git, VS Code"],
  ], [2800, 6560], { boldFirst: true }),
  H2("3.5 Implementation Plan"),
  P(`The semester plan, with milestones at the three evaluations, is shown in ${F("gantt")}. Work on the agents and the dashboard ran in parallel among the three team members, and the ingestion and verification work was added after the second evaluation in response to the review.`),
  ...figure("gantt", "fig_gantt.png", 5.2, "Project timeline (Gantt chart) for the 7th semester"),
  H2("3.6 Novelty"),
  P("The project contributes four elements that were not found together in any reviewed system:"),
  ...bullets([
    "**Proactive BI (ProBI):** a complete loop from ingestion to verified alert that runs on a schedule, stores every anomaly and alerts only on first sightings.",
    "**Causal Business Metric Graph (CBMG):** DYNOTEARS applied to business KPIs, with a ranking that combines edge strength, bootstrap confidence and the timing of anomalies to name the origin of an incident rather than a list of correlated metrics.",
    "**Verified narration:** an LLM-Modulo critic that checks numbers at the precision written, so a fluent but wrong report never reaches a manager.",
    "**Low-cost ingestion for any source:** protocol-level adapters, SLAC mapping, aggregation push-down, an edge agent and a resumable parallel transfer service, which together answer the cost and large-file concerns raised in the review.",
  ]),
  P("The evidence for each of these claims is presented in Chapter 4."),
];

// ════════════════════════════════════════════════════════════════════════════
// CHAPTER 4
// ════════════════════════════════════════════════════════════════════════════
const R = D.AlignmentType.RIGHT, C = D.AlignmentType.CENTER;
const ch4 = [
  H1("4. Implementation and Results"),
  H2("4.1 Implementation Details"),
  P("The backend consists of about 5,100 lines of Python and the dashboard of about 1,500 lines of JavaScript. Implementation proceeded in five steps: the DuckDB schema with primary keys and migrations; the connector framework and its adapters; the detection and causal models, including a NumPy/SciPy implementation of DYNOTEARS written because the existing library would not install on Python 3.13; the report verifier; and finally the transfer service, the edge agent and the dashboard. Every number in this chapter can be regenerated with two scripts in the repository, `benchmark/evaluate_models.py` and `benchmark/benchmark_ingestion.py`."),
  H2("4.2 System Features"),
  P(`The dashboard has five pages, four of which are shown in ${F("ui_a")} and ${F("ui_b")}. The Overview page shows severity counts, a filterable anomaly table and the time series of the selected metric with anomalies marked by severity. The Data Sources page lists every connected system with the rows and bytes moved in its last sync; new sources are added through a form whose Test button shows a sample and the mapping proposed by SLAC. The Fast Transfer page uploads files of any size from the browser with live chunk progress, pause and resume, and the Reports page shows the verified executive report and the alert history.`),
  ...figurePair("ui_a", ["ui_overview.png", "(a) Overview"], ["ui_sources.png", "(b) Data Sources"], "Dashboard after a monitoring cycle on live demo sources"),
  ...figurePair("ui_b", ["ui_transfer.png", "(a) Fast Transfer"], ["ui_reports.png", "(b) Reports & Alerts (LLM report marked as verified)"], "Fast Transfer and Reports pages"),
  H2("4.3 Testing and Validation"),
  P(`Testing combined automated tests, a live demonstration with simulated company systems, and two benchmark scripts. The automated suite is summarised in ${T("tests")}; all 36 tests pass. The connector tests start a real FTP server and a real HTTP server inside the test instead of using mocks.`),
  ...table("tests", "Automated test suite", ["Area", "Tests", "What is verified"], [
    ["Connectors", "14", "Long and wide mapping; CSV, gzip, Parquet and Excel; SQL push-down; REST paging; FTP new-file tracking; failure isolation"],
    ["Core models", "10", "Upsert idempotency, detection, DYNOTEARS recovery, SLAC inference, verifier, alert gating"],
    ["Fast Transfer", "5", "Chunk hashing, resume, corrupt-chunk rejection, whole-file checksum"],
    ["API end to end", "7", "Seed, pipeline, no duplicate alerts, sources, push, upload, transfer, API key"],
    ["Total", "36", "All passing"],
  ], [2000, 900, 6460], { boldFirst: true, align: [undefined, C] }),
  H2("4.4 Results and Analysis"),
  H3("4.4.1 Multi-Source Ingestion"),
  P(`Four simulated company systems were connected: an ERP database with 100,305 raw order rows, a folder of weekly marketing CSV exports, an FTP server receiving daily compressed logistics files, and a paged REST API from a support platform. ${T("demo")} records what happened during the live demonstration.`),
  ...table("demo", "Live ingestion demonstration", ["Step", "Result"], [
    ["First sync of all four sources", "4,704 KPI rows collected; the ERP sent 19.5 KB for 100,305 raw rows because the GROUP BY ran inside the database"],
    ["Second sync", "No new rows from FTP, files or REST; nothing duplicated"],
    ["New file dropped on the FTP server", "Only that file (130 bytes) downloaded; the 14 earlier files were skipped"],
    ["Edge agent on a 2-million-row export (105.6 MB)", "Aggregated locally in 0.6 s; 94.1 KB pushed, 1,149 times less data"],
    ["Fast Transfer of the same file", "Sent as 28.7 MB in 1.7 s; SHA-256 verified on the server"],
    ["Connection cut after 13 of 27 chunks", "Resume re-sent only the 14 missing chunks"],
  ], [3500, 5860], { boldFirst: true }),
  H3("4.4.2 Large-File Transfer Benchmark"),
  P(`To answer the concern about FTP, the same 2-million-row export (105.6 MB) was moved by each method between two processes on one machine, with every connection capped at 50 Mbit/s to emulate a wide-area link. The cap was applied in the same way to FTP and to Fast Transfer. The results are given in ${T("bench")} and ${F("bench")}.`),
  ...table("bench", "Ingestion benchmark for a 105.6 MB raw export", ["Method", "Time (s)", "Bytes sent", "Speed-up"], [
    ["FTP, single stream, raw CSV", "16.90", "105.6 MB", "1.0×"],
    ["FTP, single stream, gzip (incl. 4.8 s compression)", "9.18", "27.1 MB", "1.8×"],
    ["Fast Transfer, 8 streams, gzip", "2.76", "27.1 MB", "6.1×"],
    ["Fast Transfer, 8 streams, zstd", "2.63", "29.4 MB", "6.4×"],
    ["Fast Transfer, resumed after a 50% drop", "1.65", "13.6 MB", "10.2×"],
    ["Edge agent (aggregate, push KPIs)", "1.34", "192.7 KB", "12.6×"],
  ], [4700, 1400, 1700, 1560], { align: [undefined, R, R, R] }),
  ...figure("bench", "fig_benchmark.png", 5.4, "Transfer time and bytes on the wire for each method"),
  P("Fast Transfer was 6.4 times faster than plain FTP while sending about a quarter of the bytes, and an interrupted transfer cost only the missing half. Edge aggregation was faster still and reduced network traffic by a factor of about 550. This supports the central argument that most large-data cases should not transfer raw data at all."),
  H3("4.4.3 Anomaly Detection"),
  P(`Detection was evaluated over ten random seeds of the synthetic benchmark (15 metrics from four sources, 336 hourly points, two cascading incidents and six isolated anomalies). An event counts as detected if any point of the affected metric is flagged inside the event window. ${T("detect")} gives the results and ${F("detect")} shows typical output.`),
  ...table("detect", "Anomaly detection over ten seeds (mean ± standard deviation)", ["Detector", "Event recall", "Point precision", "Time per cycle (s)"], [
    ["Robust seasonal z-score", "100.0 ± 0.0%", "77.2 ± 6.2%", "0.23"],
    ["Robust z-score + Prophet ensemble (5 seeds)", "100.0 ± 0.0%", "75.2 ± 4.1%", "3.34"],
  ], [3900, 1700, 1900, 1860], { align: [undefined, C, C, C] }),
  ...figure("detect", "fig_detection.png", 5.2, "Detected anomalies on four metrics, coloured by severity"),
  P("Every injected event was found. The flags counted as false positives are mostly points just outside the event windows, where the cascade is still settling. Prophet did not improve precision on this benchmark and was about fourteen times slower, so it is kept as an option rather than the default."),
  H3("4.4.4 Causal Discovery and Root Cause"),
  P(`The learned graphs were compared with the twelve true causal edges of the benchmark. ${T("causal")} and ${F("causal_eval")} compare DYNOTEARS with three baselines.`),
  ...table("causal", "Causal discovery against ground truth over ten seeds", ["Method", "Precision", "Recall", "F1", "SHD"], [
    ["DYNOTEARS (KAIROS)", "1.00 ± 0.00", "0.95 ± 0.04", "0.97 ± 0.02", "0.6 ± 0.5"],
    ["Granger (lagged OLS)", "0.83 ± 0.13", "0.99 ± 0.03", "0.90 ± 0.08", "2.8 ± 2.5"],
    ["VARLiNGAM", "0.78 ± 0.11", "0.99 ± 0.03", "0.87 ± 0.08", "3.7 ± 2.5"],
    ["Pearson correlation", "0.44 ± 0.01", "0.58 ± 0.07", "0.50 ± 0.03", "7.0 ± 0.9"],
  ], [2960, 1600, 1600, 1600, 1600], { align: [undefined, C, C, C, C] }),
  ...figurePair("causal_eval", ["pfig_causal.png", "(a) Precision, recall and F1 (ten seeds)"], ["fig_causal_graph.png", "(b) Learned graph vs. ground truth (seed 3)"], "Causal discovery results"),
  P(`DYNOTEARS never added a false edge in ten runs; its occasional miss was the weakest true link, from average order value to revenue. The baselines found almost every true edge but added spurious ones, and correlation, which has no direction, performed worst. ${F("causal_eval")}(b) shows a learned graph against the ground truth. In the full pipeline, KAIROS named both injected origins, advertising spend and delivery delay, in all ten runs, and an investigation took 1.6 s on average.`),
  P(`The sensitivity of these results to the two main settings is shown in ${T("sens")}. The chosen values (λ = 0.05 for the L1 penalty, τ = 0.15 for the edge threshold, z = 3.5 for detection) sit in a stable region; raising the detection threshold to 4.0 trades a little recall for much higher precision.`),
  ...table("sens", "Sensitivity of causal F1 and detection to their thresholds (mean of ten seeds)", ["Setting", "Value", "Result"], [
    ["DYNOTEARS, λ = 0.05", "τ = 0.10 / 0.15 / 0.20 / 0.30", "F1 = 0.928 / 0.974 / 0.942 / 0.899"],
    ["DYNOTEARS, τ = 0.15", "λ = 0.01 / 0.05 / 0.10", "F1 = 0.845 / 0.974 / 0.942"],
    ["Detection threshold z", "3.0 / 3.5 / 4.0 / 5.0", "Precision = 0.54 / 0.77 / 0.93 / 1.00"],
    ["Detection threshold z", "3.0 / 3.5 / 4.0 / 5.0", "Event recall = 1.00 / 1.00 / 0.99 / 0.99"],
  ], [2700, 3000, 3660], { boldFirst: true }),
  P(`The same analysis as it appears on the dashboard is shown in ${F("ui_causal")}. Each chain lists its strength, bootstrap confidence, lag and whether the cause moved before the effect.`),
  ...figure("ui_causal", "ui_causal.png", 4.2, "Causal Analysis page with the CBMG and ranked root-cause chains"),
  H3("4.4.5 Report Verification"),
  P(`The verifier was tested by corrupting numbers and metric names in correct reports; the results are in ${T("verifier")}. An earlier version accepted 7.03 as a match for 6.71 because both round to 7. Comparing at the precision actually written raised the catch rate from 61% to 98.5% without rejecting faithful rounding.`),
  ...table("verifier", "LLM-Modulo verifier stress test", ["Test", "Cases", "Result"], [
    ["Faithful reports accepted", "5", "100%"],
    ["Corrupted numbers caught", "200", "98.5%"],
    ["Invented metric names caught", "50", "100%"],
    ["Faithful one-decimal rounding accepted", "200", "100%"],
  ], [5400, 1800, 2160], { align: [undefined, C, C] }),
  P(`In the live run, the report written by the Groq model passed verification on its first attempt (${F("ui_b")}(b)). The full five-agent cycle on live sources took 12.4 s.`),
  H2("4.5 Discussion"),
  P("The results support the two main claims of the project. First, causal discovery gives better explanations than the correlation logic behind current BI features: on data with a known structure it identified the origin of every incident, which is the work an analyst would otherwise do by hand. Second, the cost and speed of ingestion depend mostly on what is moved. Aggregating at the source turned the large-file problem raised in the review into a transfer of a few hundred kilobytes, and Fast Transfer covers the cases where the raw file is genuinely needed."),
  P("Two cautions apply. The benchmark data follows a linear model with known lags, which favours DYNOTEARS, and the transfer link was emulated on one machine. Both points are listed as limitations in Chapter 5."),
];

// ════════════════════════════════════════════════════════════════════════════
// CHAPTER 5
// ════════════════════════════════════════════════════════════════════════════
const ch5 = [
  H1("5. Conclusion and Future Work"),
  H2("5.1 Summary"),
  P("KAIROS shows that business monitoring can move from a pull model, in which someone has to ask, to a push model in which the system finds the problem, explains its cause and reports it in verified language. The project delivered a working five-agent system, a web dashboard, an edge agent, a transfer service, 36 automated tests and two reproducible benchmarks."),
  H2("5.2 Objectives Achievement"),
  P(`All five objectives were met, as summarised in ${T("achieved")}.`),
  ...table("achieved", "Achievement of the SMART objectives", ["Objective", "Target", "Achieved"], [
    ["O1 Autonomous pipeline", "< 30 s per cycle, no duplicates", "12.4 s; idempotent upsert verified by tests"],
    ["O2 Anomaly detection", "≥ 95% recall, ≥ 70% precision", "100% recall, 77.2% precision"],
    ["O3 Causal origin", "F1 ≥ 0.85, origin ≥ 90%", "F1 0.97, origin 100%"],
    ["O4 Verified reports", "≥ 95% misstatements caught", "98.5% caught, 100% faithful accepted"],
    ["O5 Low-cost ingestion", "≥ 4 source types, ≥ 3× faster than FTP", "5 adapter types; 6.4× (edge 12.6×)"],
  ], [2700, 3100, 3560], { boldFirst: true }),
  H2("5.3 Limitations"),
  ...bullets([
    "Evaluation used synthetic data whose linear, lagged structure matches the assumptions of DYNOTEARS; results on real company data may be lower.",
    "DYNOTEARS assumes no hidden common causes and linear effects, so a driver that KAIROS does not monitor can appear as a spurious link.",
    "The transfer benchmark ran on one machine with an emulated 50 Mbit/s link; tests over real long-distance links remain to be done.",
    "The verifier checks numbers and metric names but not qualitative claims; in one live report the LLM described all anomalies as critical, which was not fully correct and was not caught.",
    "The Anomaly Transformer was reviewed but not implemented, and no user study with business staff has been carried out.",
  ]),
  H2("5.4 Lessons Learned"),
  P("The most useful lesson came from the review itself: a question about FTP led to the realisation that the amount of data moved matters more than the protocol used to move it. Writing DYNOTEARS directly in NumPy and SciPy took longer than installing a library, but it removed a dependency conflict and made the method easier to explain. Testing against a real FTP server instead of mocks caught two bugs in file tracking, and keeping every number reproducible through scripts made the results easier to defend. Within the team, dividing the work by agent and integrating at sprint boundaries worked well, although integration should have started earlier."),
  H2("5.5 Recommendations"),
  P("Before production use, KAIROS should run in shadow mode on one real business unit for several weeks, with analysts marking each alert as useful or not. SFTP or FTPS should always be used instead of plain FTP, with read-only accounts."),
  H2("5.6 Future Scope for Capstone Project-II"),
  ...bullets([
    "Evaluate on public datasets (Olist e-commerce, Superstore) and on data from a partner company.",
    "Add nonlinear causal discovery (PCMCI) and test robustness to hidden confounders.",
    "Implement the Anomaly Transformer and compare it with the current detector.",
    "Extend the verifier to qualitative claims such as severity and direction of change.",
    "Measure Fast Transfer over real long-distance links, and add change data capture {debezium} for databases.",
    "Add multi-tenant deployment, role-based access and a user study with managers.",
  ]),
  P("In the longer term, KAIROS could become a low-cost monitoring service for small businesses that cannot afford a data team, giving them the kind of root-cause analysis that today requires an analyst."),
];

// ════════════════════════════════════════════════════════════════════════════
// APPENDICES (built before references so their citations are numbered too)
// ════════════════════════════════════════════════════════════════════════════
const A = (t) => P(t, { count: false, align: D.AlignmentType.LEFT });
const appendix = [
  H1("Appendix A: Source Code Snippets", true),
  A("**A.1 DYNOTEARS objective and gradient** (`backend/models/dynotears.py`). The weights are split into positive and negative parts so that the L1 penalty becomes linear and L-BFGS-B can be used with simple bounds."),
  ...code([
    "def objective(x, rho, alpha):",
    "    W, A = unpack(x)",
    "    R    = Xt - Xt @ W - Xlags @ A                 # SVAR residual",
    "    loss = 0.5 / n * np.sum(R ** 2)",
    "    h, E = h_func(W)                               # h(W) = tr(exp(W*W)) - d",
    "    obj  = loss + 0.5 * rho * h * h + alpha * h + l1_penalty(x)",
    "    g_w  = -1.0 / n * Xt.T @ R + (rho * h + alpha) * (E.T * 2 * W)",
    "    g_a  = -1.0 / n * Xlags.T @ R",
    "    return obj, pack_gradient(g_w, g_a)",
  ]),
  A("**A.2 Verifying a number at the precision it was written** (`backend/agents/nl_reporter.py`)."),
  ...code([
    "def _close(value: float, allowed: float, decimals: int = 2) -> bool:",
    "    # 3.97 may be written 3.97, 4.0 or 4, but never 3.78 or 7.03",
    "    step = 0.5 * 10 ** (-decimals)",
    "    return abs(value - allowed) <= step + abs(allowed) * 1e-3 + 1e-9",
  ]),
  A("**A.3 Idempotent, incremental storage** (`backend/db.py`)."),
  ...code([
    "INSERT INTO metrics (source, metric_name, timestamp, value)",
    "SELECT source, metric_name, timestamp, value FROM _kairos_batch",
    "ON CONFLICT (source, metric_name, timestamp)",
    "DO UPDATE SET value = excluded.value, ingested_at = now()",
  ]),
  H1("Appendix B: User Manual"),
  A("**B.1 Installation**"),
  ...code([
    "git clone <repository> kairos && cd kairos",
    "python -m venv backend/venv && backend\\venv\\Scripts\\activate",
    "pip install -r backend/requirements.txt",
    "cd frontend && npm install && npm run build && cd ..",
    "copy .env.example .env      # add GROQ_API_KEY, TELEGRAM_BOT_TOKEN (optional)",
    "uvicorn backend.main:app     # dashboard and API on http://127.0.0.1:8000",
  ]),
  A("**B.2 Using the dashboard**"),
  ...[
    "Open **Data Sources** and click **Add source**. Choose a type (SQL, file, SFTP/FTP, REST or push), fill in the connection details and click **Test & preview**. Apply the mapping suggested by SLAC and save.",
    "Click **Sync all** to collect data. The table shows the rows and bytes moved for each source.",
    "On **Overview**, click **Run pipeline now** or wait for the 15-minute schedule. Click any anomaly to see its chart.",
    "Open **Causal Analysis** to see the CBMG and the ranked root-cause chains; hover a chain to highlight it.",
    "Open **Reports & Alerts** to read the verified report and the alert history.",
    "For large files, use **Fast Transfer**: drop the file, choose streams and compression, start, and click **Ingest** when it completes.",
  ].map((t) => new D.Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { line: 300, after: 40 }, children: runs(t) })),
  blank(120),
  A("**B.3 Edge agent** (run next to large data inside the company network)"),
  ...code([
    "python edge_agent/kairos_edge.py aggregate --input orders.csv.gz --ts-col created_at \\",
    "    --metric amount:revenue:sum --count-metric orders --freq 1h \\",
    "    --source store_42 --server https://kairos.example.com",
    "python edge_agent/kairos_edge.py transfer --file dump.parquet --workers 8 --compress zstd --ingest",
  ]),

  H1("Appendix C: Reproducibility and Benchmark Details"),
  A("**C.1 Reproducing the results.** Every figure and table in Chapter 4 is produced by the commands below. Random seeds are fixed, so the numbers repeat exactly on the same machine; timings vary with hardware."),
  ...code([
    "python benchmark/evaluate_models.py --seeds 10",
    "python benchmark/benchmark_ingestion.py --rows 2000000 --stream-mbps 50",
    "pytest tests -q                         # 36 passed",
    "python docs/report/make_figures.py      # all figures",
  ]),
  A("**C.2 Ground-truth causal structure of the benchmark.** Marketing chain: advertising spend → click-through rate → conversion rate → order count → daily revenue, with cart abandonment (negative) into conversion, average order value into revenue, and order count into refunds. Operations chain: inventory turnover (negative) → delivery delay → open support tickets → response time → NPS (negative) → churn (negative). Gross margin is independent. Two incidents were injected in the last 24 hours (a three-hour collapse in advertising spend and a three-hour spike in delivery delay), plus six isolated anomalies of graded severity."),
  A("**C.3 Run times.** On a laptop (Python 3.13, Windows 11), detection for 15 series took 0.23 s, DYNOTEARS 0.25 s, a full investigation with two bootstrap refits and DoWhy 1.6 s, and a complete five-agent cycle including an LLM call 12.4 s."),
];

// references last: numbering follows first appearance in the body text
const references = [
  H1("References", true),
  ...citeOrder.map((k, i) => new D.Paragraph({
    alignment: D.AlignmentType.LEFT, spacing: { line: 264, after: 100 }, indent: { left: 600, hanging: 600 },
    tabStops: [{ type: D.TabStopType.LEFT, position: 600 }],
    children: [new D.TextRun({ text: `[${i + 1}]\t`, font: FONT, size: 22 }), ...runs(byKey[k].ieee, { size: 22 })],
  })),
];

// ════════════════════════════════════════════════════════════════════════════
// DOCUMENT
// ════════════════════════════════════════════════════════════════════════════
const logo = fs.readFileSync(path.join(FIG, "woxsen_logo.png"));
const { w: lw, h: lh } = pngSize(path.join(FIG, "woxsen_logo.png"));
const header = new D.Header({ children: [new D.Paragraph({ alignment: D.AlignmentType.RIGHT, spacing: { after: 0 },
  children: [new D.ImageRun({ type: "png", data: logo, transformation: { width: 72, height: Math.round((72 * lh) / lw) } })] })] });
const footer = new D.Footer({ children: [new D.Paragraph({ alignment: D.AlignmentType.CENTER, children: [new D.TextRun({ children: [D.PageNumber.CURRENT], font: FONT, size: 22 })] })] });
const pb = { style: D.BorderStyle.SINGLE, size: 6, color: "000000", space: 24 };
const page = {
  size: { width: 12240, height: 15840 },
  margin: { top: 1440, bottom: 1300, left: 1440, right: 1440, header: 560, footer: 560 },
  borders: { pageBorderTop: pb, pageBorderBottom: pb, pageBorderLeft: pb, pageBorderRight: pb,
    pageBorders: { display: D.PageBorderDisplay.ALL_PAGES, offsetFrom: D.PageBorderOffsetFrom.PAGE } },
};

const body = [...ch1, ...ch2, ...ch3, ...ch4, ...ch5];   // chapters and appendix are built above, so citation order is fixed
const doc = new D.Document({
  creator: "Palla Chetana Reddy, Varshini Yadav Nasaram, Obulagari Nandini",
  title: "KAIROS Capstone Project-I Report",
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: SZ } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 32, bold: true, color: "000000" }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 28, bold: true, color: "000000" }, paragraph: { outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 24, bold: true, color: "000000" }, paragraph: { outlineLevel: 2 } },
      { id: "TOC1", name: "toc 1", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 22 }, paragraph: { spacing: { before: 0, after: 0, line: 252 } } },
      { id: "TOC2", name: "toc 2", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 22 }, paragraph: { spacing: { before: 0, after: 0, line: 252 }, indent: { left: 240 } } },
      { id: "FigCaption", name: "FigCaption", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 20 } },
      { id: "TabCaption", name: "TabCaption", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 20 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: D.LevelFormat.BULLET, text: "•", alignment: D.AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    { reference: "steps", levels: [{ level: 0, format: D.LevelFormat.DECIMAL, text: "%1.", alignment: D.AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
  ] },
  sections: [
    { properties: { page }, headers: { default: header }, children: titlePage },
    { properties: { page: { ...page, pageNumbers: { start: 1, formatType: D.NumberFormat.DECIMAL } } }, headers: { default: header }, footers: { default: footer },
      children: [...certificate, ...declaration, ...acknowledgment, ...abstract, ...lists, ...abbreviations, ...body, ...references, ...appendix] },
  ],
});

D.Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  const n = words.join(" ").replace(/[*`]/g, "").split(/\s+/).filter((w) => /[A-Za-z0-9]/.test(w)).length;
  console.log(`wrote ${OUT}\nmain-text words: ${n}\nreferences cited: ${citeOrder.length}`);
});
