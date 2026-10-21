// Two research papers from the KAIROS project, with distinct content:
//   IEEE (two-column conference format, max 6 pages): causal root-cause analysis + verified reporting
//   APA 7 (student paper):                            low-cost multi-source ingestion and large-file transfer
// usage: node build_papers.js <ieee.docx> <apa.docx>
const fs = require("fs");
const path = require("path");
const D = require("docx");
const { byKey } = require("./refs");

const [IEEE_OUT, APA_OUT] = process.argv.slice(2);
if (!IEEE_OUT || !APA_OUT || !/\.docx$/i.test(IEEE_OUT) || !/\.docx$/i.test(APA_OUT)) throw new Error("usage: node build_papers.js <ieee.docx> <apa.docx>");
const FIG = path.resolve(__dirname, "..", "report", "figures");
const FONT = "Times New Roman";
const AUTHORS = ["Palla Chetana Reddy", "Varshini Yadav Nasaram", "Obulagari Nandini"];
const MENTOR = "Dr. K RajKumar";
const AFFIL = "School of Technology, Woxsen University, Hyderabad, Telangana, India";

function pngSize(file) { const b = fs.readFileSync(file); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; }
// Minimal TeX-like syntax for Word (OMML) equations: x_{t}, e^{W∘W}, \frac{a}{b}, \tr{...}, \min{limit}{body}
function mathParse(s) {
  const out = [];
  let i = 0, buf = "";
  const flush = () => { if (buf) { out.push(new D.MathRun(buf)); buf = ""; } };
  const group = () => {
    let depth = 0, j = i;
    for (; j < s.length; j++) { if (s[j] === "{") depth++; else if (s[j] === "}" && --depth === 0) break; }
    const g = s.slice(i + 1, j); i = j + 1; return g;
  };
  while (i < s.length) {
    if (s.startsWith("\\frac", i)) { i += 5; const a = group(), b = group(); flush(); out.push(new D.MathFraction({ numerator: mathParse(a), denominator: mathParse(b) })); continue; }
    if (s.startsWith("\\tr", i)) { i += 3; const a = group(); flush(); out.push(new D.MathFunction({ name: [new D.MathRun("tr")], children: mathParse(a) })); continue; }
    if (s.startsWith("\\min", i)) { i += 4; const lim = group(), body = group(); flush(); out.push(new D.MathFunction({ name: [new D.MathLimitLower({ children: [new D.MathRun("min")], limit: mathParse(lim) })], children: mathParse(body) })); continue; }
    let base = null, ch = "";
    if (s[i] === "{") base = mathParse(group()); else ch = s[i++];
    let sub = null, sup = null;
    while (s[i] === "_" || s[i] === "^") { const t = s[i++]; const g = s[i] === "{" ? group() : s[i++]; if (t === "_") sub = g; else sup = g; }
    if (sub === null && sup === null) { if (base) { flush(); out.push(...base); } else buf += ch; continue; }
    flush();
    const b = base || [new D.MathRun(ch)];
    if (sub !== null && sup !== null) out.push(new D.MathSubSuperScript({ children: b, subScript: mathParse(sub), superScript: mathParse(sup) }));
    else if (sub !== null) out.push(new D.MathSubScript({ children: b, subScript: mathParse(sub) }));
    else out.push(new D.MathSuperScript({ children: b, superScript: mathParse(sup) }));
  }
  flush();
  return out;
}
function runs(text, base) {
  const out = [], re = /(\$[^$]+\$|\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0, m;
  const mk = (t, x = {}) => new D.TextRun({ font: FONT, ...base, ...x, text: t });
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(mk(text.slice(last, m.index)));
    const t = m[0];
    if (t.startsWith("$")) out.push(new D.Math({ children: mathParse(t.slice(1, -1)) }));
    else if (t.startsWith("**")) out.push(mk(t.slice(2, -2), { bold: true }));
    else if (t.startsWith("`")) out.push(mk(t.slice(1, -1), { font: "Consolas", size: base.size - 2 }));
    else out.push(mk(t.slice(1, -1), { italics: !base.italics }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(mk(text.slice(last)));
  return out;
}
const countWords = (arr) => arr.join(" ").replace(/[*`]/g, "").split(/\s+/).filter((w) => /[A-Za-z0-9]/.test(w)).length;

// ════════════════════════════════════════════════════════════════════════════
// IEEE PAPER
// ════════════════════════════════════════════════════════════════════════════
function buildIEEE() {
  const order = [];
  const cite = (t) => t.replace(/\{([a-z0-9_,\s]+)\}/g, (whole, keys) => {
    const ks = keys.split(",").map((k) => k.trim());
    if (!ks.every((k) => byKey[k])) return whole;
    return ks.map((k) => { if (!order.includes(k)) order.push(k); return `[${order.indexOf(k) + 1}]`; }).join(", ");
  });
  const S = 20;   // 10 pt
  const words = [];
  const P = (t, o = {}) => { const c = cite(t); words.push(c); return new D.Paragraph({ alignment: D.AlignmentType.JUSTIFIED, spacing: { line: 240, after: 0 }, indent: o.noIndent ? undefined : { firstLine: 202 }, children: runs(c, { size: S }) }); };
  let eqN = 0;
  const EQ = (tex) => { eqN++; return new D.Paragraph({ spacing: { before: 60, after: 60 }, tabStops: [{ type: D.TabStopType.CENTER, position: 2520 }, { type: D.TabStopType.RIGHT, position: 5040 }],
    children: [new D.TextRun({ text: "\t", font: FONT, size: S }), new D.Math({ children: mathParse(tex) }), new D.TextRun({ text: `\t(${eqN})`, font: FONT, size: S })] }); };
  const H1 = (n, t) => new D.Paragraph({ alignment: D.AlignmentType.CENTER, keepNext: true, spacing: { before: 160, after: 80 }, children: [new D.TextRun({ text: n ? `${n}. ${t}` : t, font: FONT, size: S, smallCaps: true })] });
  const H2 = (n, t) => new D.Paragraph({ keepNext: true, spacing: { before: 100, after: 40 }, children: [new D.TextRun({ text: `${n}. ${t}`, font: FONT, size: S, italics: true })] });
  const bullets = (items) => items.map((t) => { const c = cite(t); words.push(c); return new D.Paragraph({ numbering: { reference: "ib", level: 0 }, alignment: D.AlignmentType.JUSTIFIED, spacing: { line: 240, after: 0 }, children: runs(c, { size: S }) }); });
  let figN = 0, tabN = 0;
  const ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
  // a figure; `wide` figures span both columns (placed in their own one-column section, like figure* in LaTeX)
  const fig = (file, widthIn, cap, wide = false) => {
    figN++;
    const full = path.join(FIG, file), { w, h } = pngSize(full), wpx = Math.round(widthIn * 96);
    const els = [
      new D.Paragraph({ alignment: D.AlignmentType.CENTER, keepNext: true, spacing: { before: 100, after: 40 }, children: [new D.ImageRun({ type: "png", data: fs.readFileSync(full), transformation: { width: wpx, height: Math.round((wpx * h) / w) } })] }),
      new D.Paragraph({ alignment: wide ? D.AlignmentType.CENTER : D.AlignmentType.JUSTIFIED, spacing: { after: 120 }, children: [new D.TextRun({ text: `Fig. ${figN}. `, font: FONT, size: 16 }), ...runs(cite(cap), { size: 16 })] }),
    ];
    return wide ? [{ wide: els }] : els;
  };
  const SYM = /^[✓✗◐—]$/;
  const table = (cap, headers, rows, widths, align = [], total = 5040) => {
    tabN++;
    const sc = total / widths.reduce((a, b) => a + b, 0);
    const W = widths.map((x) => Math.round(x * sc)); W[W.length - 1] += total - W.reduce((a, b) => a + b, 0);
    const line = { style: D.BorderStyle.SINGLE, size: 4, color: "000000" }, none = { style: D.BorderStyle.NONE, size: 0, color: "FFFFFF" };
    const cell = (t, i, head, last, shade) => new D.TableCell({
      width: { size: W[i], type: D.WidthType.DXA }, margins: { top: 20, bottom: 20, left: 50, right: 50 },
      shading: shade ? { type: D.ShadingType.CLEAR, color: "auto", fill: "E8E8E8" } : undefined,
      borders: { top: head ? line : none, bottom: head || last ? line : none, left: none, right: none },
      children: [new D.Paragraph({ alignment: i === 0 ? D.AlignmentType.LEFT : (align[i] || D.AlignmentType.CENTER), spacing: { after: 0, line: 220 }, keepNext: !last,
        children: SYM.test(String(t)) ? [new D.TextRun({ text: String(t), font: "Segoe UI Symbol", size: 15 })] : runs(cite(String(t)), { size: 15, bold: head || undefined }) })],
    });
    return [
      new D.Paragraph({ alignment: D.AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 0 }, children: [new D.TextRun({ text: `TABLE ${ROMAN[tabN - 1]}`, font: FONT, size: 16 })] }),
      new D.Paragraph({ alignment: D.AlignmentType.CENTER, keepNext: true, spacing: { after: 60 }, children: [new D.TextRun({ text: cap, font: FONT, size: 16, smallCaps: true })] }),
      new D.Table({ width: { size: total, type: D.WidthType.DXA }, columnWidths: W, alignment: D.AlignmentType.CENTER, borders: D.TableBorders.NONE,
        rows: [new D.TableRow({ cantSplit: true, tableHeader: true, children: headers.map((h, i) => cell(h, i, true, false)) }),
          ...rows.map((r, ri) => new D.TableRow({ cantSplit: true, children: r.map((v, i) => cell(v, i, false, ri === rows.length - 1, /KAIROS/.test(String(r[0])))) }))] }),
      new D.Paragraph({ spacing: { after: 100 }, children: [] }),
    ];
  };

  const title = "KAIROS: Proactive Causal Root-Cause Analysis of Business Metrics with DYNOTEARS and Verified LLM Reporting";
  const PEOPLE = [
    ...AUTHORS.map((a) => [a, "School of Technology", "Woxsen University", "Hyderabad, India"]),
    [MENTOR, "Associate Professor, HOD", "Department of CSE and BIC", "Woxsen University", "Hyderabad, India"],
  ];
  const noB = { style: D.BorderStyle.NONE, size: 0, color: "FFFFFF" };
  const head = [
    new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { after: 200 }, children: [new D.TextRun({ text: title, font: FONT, size: 44 })] }),
    new D.Table({
      width: { size: 10440, type: D.WidthType.DXA }, columnWidths: [2610, 2610, 2610, 2610], borders: D.TableBorders.NONE, alignment: D.AlignmentType.CENTER,
      rows: [new D.TableRow({ children: PEOPLE.map(([name, ...lines]) => new D.TableCell({ width: { size: 2610, type: D.WidthType.DXA }, borders: { top: noB, bottom: noB, left: noB, right: noB },
        children: [
          new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { after: 0 }, children: [new D.TextRun({ text: name, font: FONT, size: 22 })] }),
          ...lines.map((l, li) => new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { after: 0 }, children: [new D.TextRun({ text: l, font: FONT, size: 18, italics: li < lines.length - 1 })] })),
        ] })) })],
    }),
    new D.Paragraph({ spacing: { after: 200 }, children: [] }),
  ];

  const ABS = "Business intelligence dashboards wait for a person to ask a question, and the explanations they give for a sudden change are correlations. This paper presents KAIROS, an autonomous multi-agent system that monitors business metrics without being asked, finds the causal origin of each anomaly and reports it in plain language whose numbers have been checked. Anomalies are scored with a seasonal robust z-score; DYNOTEARS learns a lagged causal graph of the metrics, which is walked backwards from each anomaly and ranked by strength, bootstrap stability and timing; an LLM-Modulo verifier rejects any report whose numbers or metric names do not match the computed facts; and a low-cost ingestion layer with a chunked, parallel Fast Transfer service feeds the system from SQL, SFTP/FTP, files, REST APIs and edge agents. On a benchmark of 15 metrics with 12 known causal edges over ten seeds, DYNOTEARS reached an F1 score of 0.974, which is 8.1% higher than Granger regression, 12.2% higher than VARLiNGAM and 95.6% higher than correlation, with 79–91% fewer structural errors. KAIROS named both true incident origins in 100% of runs, against 70% for a top-movers dashboard heuristic and 60%, 40% and 30% when the same ranking used Granger, VARLiNGAM or correlation graphs. The verifier caught 98.5% of corrupted numbers, against 59.5% for a tolerance rule, while accepting every faithful report, and Fast Transfer moved a 106 MB export 6.1 times faster than FTP.";
  const KEYWORDS = ["Business Intelligence", "Anomaly Detection", "Causal Discovery", "DYNOTEARS", "Root Cause Analysis", "Large Language Models", "LLM Verification", "Multi-Agent Systems", "Data Ingestion"];
  const abstract = [
    new D.Paragraph({ alignment: D.AlignmentType.JUSTIFIED, spacing: { after: 80, line: 228 }, children: [new D.TextRun({ text: "Abstract", font: FONT, size: 18, bold: true, italics: true }), new D.TextRun({ text: "—", font: FONT, size: 18, bold: true }), ...runs(ABS, { size: 18, bold: true })] }),
    new D.Paragraph({ alignment: D.AlignmentType.JUSTIFIED, spacing: { after: 120, line: 228 }, children: [new D.TextRun({ text: "Index Terms", font: FONT, size: 18, bold: true, italics: true }), new D.TextRun({ text: `—${KEYWORDS.join(", ")}.`, font: FONT, size: 18, bold: true })] }),
  ];
  words.push(ABS);

  const Y = "✓", N = "✗", H = "◐", NA = "—";
  const body = [
    ...abstract,
    H1("I", "Introduction"),
    P("Business intelligence (BI) platforms such as Power BI and Tableau are the standard way for managers to follow revenue, orders, churn and operational metrics, and two decades of research link their use to better decisions {j_ain}. They are, however, reactive: a problem is found only when someone opens the right dashboard and notices it. Augmented analytics adds automatic insights {j_prat}, but these rank fields by statistical association, which cannot tell a cause from its effect or from a shared driver {j_scholkopf}. An analyst who sees revenue fall must still trace by hand whether the cause was fewer visitors, a broken checkout or a paused campaign, and by the time the cause is found the loss has already grown."),
    P("Three research threads make an autonomous alternative possible. Robust and forecasting-based detectors monitor seasonal series reliably {j_prophet, j_rh, j_blazquez}. Continuous-optimisation structure learning, NOTEARS {x_notears} and its time-series form DYNOTEARS {x_dynotears}, recovers directed and lagged dependencies from observational data and has since been applied to real time series {j_thomas}. Large language models (LLMs) {j_chang} turn findings into readable text but also produce fluent statements that are not supported by their input {j_halluc, j_huang}. No existing system joins the three for business metrics: BI tools stop at association, root-cause tools from IT operations target server telemetry {j_soldani}, and LLM-based analysts are not checked against the data."),
    P("This paper combines these threads into KAIROS and makes four contributions:"),
    ...bullets([
      "a five-agent pipeline that runs on a schedule, stores every anomaly and alerts only on first sightings, so monitoring needs no human trigger;",
      "a root-cause procedure on top of a DYNOTEARS graph of business metrics that ranks causal chains by edge strength, bootstrap stability and anomaly timing, and names the origin of an incident;",
      "a deterministic verifier, following the LLM-Modulo principle of sound external critics {j_kamb}, that checks every number at the precision written and every metric name before a report is delivered;",
      "a low-cost ingestion layer of five protocol adapters and a resumable, parallel Fast Transfer service, delivered with a working web dashboard.",
    ]),
    P("Against six baselines on a benchmark with known ground truth, KAIROS gives the most accurate causal graph, the only perfect origin localisation and a verifier that misses 96% fewer corrupted numbers than a tolerance rule. Section II reviews related work, Section III compares KAIROS with existing systems, Sections IV and V describe the system and its methods, Sections VI and VII report the evaluation, and Sections VIII to X discuss the results, future scope and conclusions."),

    H1("II", "Related Work"),
    P("**Anomaly detection.** Recent surveys group time-series detectors into statistical, forecasting-based and learned families {j_blazquez, j_choi}. Prophet {j_prophet} models trend and seasonality and flags points outside its forecast band, and robust statistics such as the median absolute deviation give scale estimates that the outliers themselves do not inflate {j_rh}. Deep detectors, reviewed by Pang et al. {j_pang} and Zamanzadeh Darban et al. {j_darban}, perform well on public benchmarks but need training for each dataset and give no causal explanation."),
    P("**Causal discovery.** Reviews by Glymour et al. {j_glymour}, Vowels et al. {j_vowels}, Zanga et al. {j_zanga} and Nogueira et al. {j_nogueira} cover constraint-based, score-based, functional and continuous-optimisation methods. For time series, Granger causality {j_shojaie} tests whether past values of one series improve the prediction of another, VARLiNGAM {j_varlingam} identifies a structural vector autoregression, PCMCI {j_pcmci} uses conditional-independence tests with lagged conditioning sets {j_runge_nc} and TCDF {j_tcdf} uses attention in convolutional networks. DYNOTEARS {x_dynotears} learns same-step and lagged weights jointly under a smooth acyclicity constraint; its behaviour on real data has been studied in recent journal work {j_thomas, j_kaiser}. Surveys of temporal causal discovery {j_assaad, j_hasan, j_moraffah, j_gong} compare these families, causal-learn {j_causallearn} implements many of them, and DoWhy-GCM {j_dowhygcm} estimates effects once a graph is known."),
    P("**Root-cause analysis.** HotSpot {j_hotspot} localises a change in an additive KPI to the dimension values, such as a region or a browser, that explain it; it answers *where* a total changed, not *which other metric* caused it. In IT operations, the survey by Soldani and Brogi {j_soldani} reviews dozens of methods. CauseInfer {j_causeinfer} builds a hierarchical causality graph of cloud services, CausalRCA {j_causalrca} learns weighted causal graphs from microservice metrics, Żurkowski and Zieliński {j_zurkowski} localise faults in cloud-native applications and DGERCL {j_dgercl} uses dynamic graph embeddings. All of them target infrastructure telemetry and engineers rather than business KPIs and managers."),
    P("**LLMs for analysis and their verification.** LLMs are now used as software and data assistants {j_hou}, for example to translate business questions into SQL {j_hong, j_liusql}, and Kıcıman et al. {j_kiciman} study their causal reasoning. Because LLMs hallucinate {j_halluc, j_huang}, detection methods such as semantic entropy {j_farquhar} and fact-checking pipelines {j_augenstein} have been proposed. These estimate the reliability of an answer statistically, whereas Kambhampati {j_kamb} argues that LLM output should be checked by sound external critics, the principle that KAIROS applies to numbers."),
    P("**Agents and data movement.** Surveys of LLM-based agents {j_wangagents, j_xi} describe how planning, memory and tools are combined into multi-step agents, which KAIROS runs as a state machine. For data movement, edge computing moves computation next to the data {j_cao}, and parallel streams with tuned concurrency are the established way to accelerate large transfers over wide-area links {j_nine}."),

    H1("III", "Comparison with Existing Work"),
    P("Table I compares KAIROS with representative tools and research systems on six properties that a business user needs. A tick means that the property is a design goal of the published system, a half circle means partial support and a dash means not applicable."),
    { wide: table("Comparison of KAIROS with existing BI tools and root-cause analysis systems",
      ["System", "Domain", "Runs unprompted", "Directed causal graph", "Lagged effects", "Business KPIs", "Plain-language report", "Report checked against data"], [
        ["Power BI Key Influencers", "BI tool", H, N, N, Y, H, NA],
        ["Tableau Explain Data", "BI tool", N, N, N, Y, H, NA],
        ["HotSpot {j_hotspot}", "Additive KPIs", Y, N, N, Y, N, NA],
        ["CauseInfer {j_causeinfer}", "Cloud services", Y, Y, N, N, N, NA],
        ["CausalRCA {j_causalrca}", "Microservices", Y, Y, N, N, N, NA],
        ["PCMCI {j_pcmci}", "Earth science", N, Y, Y, N, N, NA],
        ["LLM text-to-SQL {j_hong, j_liusql}", "Databases", N, N, N, Y, Y, H],
        ["**KAIROS (this work)**", "Business KPIs", Y, Y, Y, Y, Y, Y],
      ], [2500, 1400, 950, 950, 850, 850, 950, 1100], [], 10440) },
    P("Three gaps stand out. First, BI tools explain by association and wait for the user, so a manager learns of a problem late and receives a list of correlated fields. Second, KPI localisers find the slice of the data in which a total changed, and AIOps systems find the faulty service, but neither connects business metrics such as advertising spend, conversion, delivery delay and churn into one directed, lagged graph. Third, LLM data assistants answer a question that the user must first think to ask, and their explanations are not checked against the data. KAIROS is the only system in Table I with all six properties, and it is built only from free, open components. Section VII measures the gain: against the graph learners used by prior causal methods, KAIROS raises exact origin localisation from 40–60% to 100%."),

    H1("IV", "System Architecture"),
    H2("A", "Agent Pipeline"),
    P("Fig. 1 shows the architecture. Data from every source is normalised to rows of (source, metric, timestamp, value) and upserted into an embedded DuckDB store on that key, so repeated loads never duplicate data. A LangGraph state machine runs five agents every 15 minutes: collect, detect, investigate, report and alert {j_wangagents}. The graph ends after detection when no new alert-worthy anomaly exists, which keeps quiet cycles cheap and prevents repeated alerts. A FastAPI service exposes the results, and alerts are sent through Telegram, e-mail or the dashboard."),
    ...fig("pfig_architecture.png", 2.9, "KAIROS pipeline. The investigation stage (bold) is the focus of this paper."),
    H2("B", "Low-Cost Ingestion and Fast Transfer"),
    P("Instead of one connector per product, KAIROS uses five protocol adapters that cover almost every company system. The SQL adapter pushes the aggregation query into the source database, so a large table returns a few kilobytes of KPIs. The SFTP/FTP adapter fetches only files that are new since the last sync. The file adapter reads CSV, Excel and Parquet from disk or cloud storage, the REST adapter handles authentication, paging and incremental queries, and push clients or an edge agent {j_cao} post KPIs that are aggregated next to the data. Column names are mapped to metrics by rule-based schema matching."),
    P("When a raw file must move, the Fast Transfer service splits it into chunks of 1 to 32 MB, compresses each chunk with gzip or Zstandard, hashes it with SHA-256 and uploads the chunks over parallel HTTPS connections with retries {j_nine}. The server checks every chunk, writes it at its offset and, after a dropped connection, asks only for the missing chunks. This gives the speed of commercial transfer accelerators at no cost and without per-row connector fees. Fig. 2 shows both parts running in the dashboard."),
    ...fig("pui_ingestion.png", 5.6, "Ingestion in the dashboard: (a) five sources registered through the SQL, SFTP/FTP, file, push and REST adapters, synced incrementally; (b) measured transfer of the same export by FTP, Fast Transfer and the edge agent.", true),
    H2("C", "Dashboard"),
    P("The React dashboard has five pages. The Overview (Fig. 3) shows the monitored metrics, the anomalies by severity, a detail chart and recent pipeline runs. Causal Analysis draws the learned graph and the ranked chains (Fig. 4). Reports & Alerts shows the verified executive report (Fig. 5), and Data Sources and Fast Transfer manage ingestion (Fig. 2). All figures are screenshots of the running system on simulated company data."),
    ...fig("pui_overview.png", 6.3, "KAIROS Overview dashboard: 17 metrics from 5 sources are monitored without a user query; anomalies are listed by severity with observed value, expected value and robust z-score, and the selected metric is plotted with its anomalies.", true),

    H1("V", "Method"),
    H2("A", "Seasonal Robust Detection"),
    P("For a metric series $x_{t}$, the expected value $m_{t}$ is a centred rolling median plus an hour-of-day profile of the residuals, kept only when it reduces their spread. The residual $r_{t} = x_{t} − m_{t}$ is scaled by the median absolute deviation (MAD) {j_rh}, which the outliers themselves do not inflate, giving the robust score"),
    EQ("z_{t} = \\frac{x_{t} − m_{t}}{1.4826 · MAD(r)}"),
    P("A point is anomalous when $|z_{t}| ≥ 3.5$; severity is medium from 4.5, high from 6 and critical from 9. Prophet {j_prophet} can be added as a second detector. Anomalies are stored with their key, so a point is reported as new only once.", { noIndent: true }),
    H2("B", "Causal Discovery with DYNOTEARS"),
    P("The metrics are aligned to a common grid, winsorised at 3.5 robust standard deviations so that the anomalies do not shape the learned structure, and standardised. DYNOTEARS {x_dynotears} models them as a structural vector autoregression"),
    EQ("X_{t} = X_{t}W + X_{t−1}A + E"),
    P("where $X_{t}$ is the $n × d$ matrix of the $d$ metrics, $W$ ($d × d$) holds same-step edges, $A$ holds one-step lagged edges and $E$ is noise. With the squared loss", { noIndent: true }),
    EQ("ℓ(W,A) = \\frac{1}{2n}‖X_{t} − X_{t}W − X_{t−1}A‖_{F}^{2}"),
    P("the weights solve the sparse problem", { noIndent: true }),
    EQ("\\min{W,A}{ℓ(W,A) + λ_{W}‖W‖_{1} + λ_{A}‖A‖_{1}}"),
    P("subject to the smooth acyclicity constraint of NOTEARS {x_notears}", { noIndent: true }),
    EQ("h(W) = \\tr{(e^{W∘W})} − d = 0"),
    P("where ∘ is the element-wise product. The problem is solved by an augmented Lagrangian with L-BFGS-B on the positive and negative parts of the weights, implemented directly in NumPy {j_numpy} and SciPy {j_scipy}. Edges with $|w| ≥ τ = 0.15$ form the Causal Business Metric Graph (CBMG), with $λ_{W} = λ_{A} = 0.05$. Each edge receives a confidence equal to the fraction of block-bootstrap refits, on 75% windows, that keep it.", { noIndent: true }),
    H2("C", "Root-Cause Ranking"),
    P("For every anomalous metric $e$, each ancestor $c$ in the CBMG is a candidate cause. The strongest path from $c$ to $e$ is found, and its strength $S$ is the product of the edge weights along it. A candidate is *temporally supported* if $c$ itself was anomalous at most one path lag plus two steps before an anomaly of $e$. The chain score is"),
    EQ("R(c,e) = S^{1/k} · κ · α · β · (1 + 0.05k)"),
    P("where $k$ is the path length, $κ$ is the mean edge confidence, $α = 1.5$ if the cause is temporally supported and 1 otherwise, and $β = 2$ if the cause is an *origin*, that is, a supported cause with no anomalous, supported ancestor of its own, and 1 otherwise. The geometric mean $S^{1/k}$ prevents long chains, which explain more of a cascade, from being penalised merely for their length. DoWhy {j_dowhygcm} estimates a back-door adjusted effect for each direct edge.", { noIndent: true }),
    H2("D", "LLM-Modulo Report Verification"),
    P("The LLM receives only computed facts: values, expectations, percentage changes, severities and the ranked chains. Its draft is checked by a deterministic critic {j_kamb}. Every number in the text must equal a fact once the fact is rounded to the number of decimals written, so 3.97 may be written 3.97, 4.0 or 4, but never 3.78. Every snake_case identifier must be a known metric. A failing draft is returned once with the list of errors, and a second failure falls back to a template that is correct by construction."),

    H1("VI", "Experimental Setup"),
    P("Real business data with labelled root causes is not publicly available, so a benchmark with known structure was generated. It has 15 hourly metrics from four simulated sources over 336 hours, linked by 12 lagged causal edges in two chains. The marketing chain runs from advertising spend through click-through and conversion to orders and revenue; the operations chain runs from delivery delay through support tickets and response time to NPS and churn. Daily seasonality is added. Two incidents are injected in the last 24 hours, a three-hour collapse in advertising spend and a spike in delivery delay, plus six isolated anomalies of graded size. Every experiment is repeated over ten seeds."),
    P("Causal discovery is scored against the 12 true edges with precision, recall, F1 and structural Hamming distance (SHD). The baselines are lagged OLS (Granger) {j_shojaie}, VARLiNGAM {j_varlingam} from causal-learn {j_causallearn}, and Pearson correlation with |r| ≥ 0.3. Origin localisation compares KAIROS with six strategies that receive the same detector output: the two metrics with the largest |z| (the top movers a dashboard shows), the two earliest anomalies, the KAIROS ranking applied to Granger, VARLiNGAM and correlation graphs, and KAIROS without bootstrap confidence. Detection is scored by event recall and point precision. The ingestion benchmark moves a raw export of 2,000,000 order rows (105.6 MB) over a 50 Mbit/s link per connection, emulated on one machine, with Fast Transfer using 8 streams and 4 MB chunks. All runs used a laptop, and every script is released with the system."),

    H1("VII", "Results"),
    H2("A", "Causal Discovery"),
    ...table("Causal discovery over ten seeds (mean ± s.d.)", ["Method", "Precision", "Recall", "F1", "SHD", "F1 gain of KAIROS"], [
      ["**KAIROS (DYNOTEARS)**", "**1.000 ± 0.000**", "0.950 ± 0.041", "**0.974 ± 0.021**", "**0.6**", "—"],
      ["Granger {j_shojaie}", "0.835 ± 0.128", "0.992 ± 0.025", "0.901 ± 0.082", "2.8", "+8.1%"],
      ["VARLiNGAM {j_varlingam}", "0.778 ± 0.113", "0.992 ± 0.025", "0.868 ± 0.077", "3.7", "+12.2%"],
      ["Correlation", "0.437 ± 0.007", "0.583 ± 0.075", "0.498 ± 0.031", "7.0", "+95.6%"],
    ], [1500, 1050, 1050, 1050, 500, 900]),
    P("Table II shows that DYNOTEARS added no false edge in any of the ten runs, a precision of 1.000 against 0.835 for Granger and 0.778 for VARLiNGAM. Its F1 score is 8.1%, 12.2% and 95.6% higher than the three baselines, and its structural Hamming distance of 0.6 is 78.6%, 83.8% and 91.4% lower. Its occasional miss was the weakest true link, from average order value to revenue. Granger regression and VARLiNGAM found nearly every true edge but also linked metrics that share a driver, and correlation, which has no direction, was worst. The acyclicity constraint and the joint fit of same-step and lagged weights are what remove these spurious edges."),
    H2("B", "Origin Localisation"),
    ...table("Incident origin localisation over ten seeds", ["Strategy", "Exact origins", "Origin F1", "Top-5 chain precision"], [
      ["Largest deviation (top movers)", "70%", "85.0%", "—"],
      ["Earliest anomaly", "0%", "35.0%", "—"],
      ["Correlation graph + ranking", "30%", "73.7%", "30.0%"],
      ["Granger graph + ranking", "60%", "86.7%", "98.0%"],
      ["VARLiNGAM graph + ranking", "40%", "80.0%", "98.0%"],
      ["KAIROS without bootstrap", "100%", "100%", "100%"],
      ["**KAIROS (full)**", "**100%**", "**100%**", "**100%**"],
    ], [2200, 900, 900, 1100]),
    P("Table III reports how often each strategy named exactly the two injected origins. KAIROS did so in all ten runs, 30 percentage points more than the best non-causal heuristic and 40 to 70 points more than the same ranking on the baseline graphs. The top-movers heuristic failed in three runs because a downstream metric, support tickets, deviated more than its cause. The earliest-anomaly rule never succeeded, because an unrelated isolated anomaly occurred before both incidents. On the Granger and VARLiNGAM graphs, spurious edges gave a true origin an apparent anomalous parent, so it was demoted and origin recall fell to 80% and 70%. The correlation graph, having no direction, produced correct top-five chains only 30% of the time, against 100% for KAIROS. A full investigation took 0.95 s on average. Fig. 4 shows the result in the dashboard: both origins are starred and the chain from delivery delay to churn is ranked first."),
    H2("C", "Detection and Sensitivity"),
    ...table("Sensitivity (mean of ten seeds)", ["Setting", "Values", "Result"], [
      ["τ (λ = 0.05)", "0.10 / 0.15 / 0.20 / 0.30", "F1 0.93 / 0.97 / 0.94 / 0.90"],
      ["λ (τ = 0.15)", "0.01 / 0.05 / 0.10", "F1 0.85 / 0.97 / 0.94"],
      ["z threshold", "3.0 / 3.5 / 4.0 / 5.0", "Prec. 0.54 / 0.77 / 0.93 / 1.00"],
      ["z threshold", "3.0 / 3.5 / 4.0 / 5.0", "Recall 1.00 / 1.00 / 0.99 / 0.99"],
    ], [1100, 1700, 2100]),
    P("The robust detector found every injected event (event recall 100%) with point precision of 77.2 ± 6.2%, in 0.23 s per cycle. Adding Prophet gave 75.2% precision at 14.3 times the cost, so the robust detector is both 2.0 points more precise and an order of magnitude faster, and Prophet is kept optional. Table IV shows that the chosen settings sit in a stable region: F1 stays above 0.89 for τ between 0.10 and 0.30, and raising z to 4.0 lifts precision by 15.7 points to 92.9% while event recall stays at 99.4%."),
    ...fig("pui_causal.png", 6.3, "Causal Analysis page: the learned Causal Business Metric Graph (red nodes are anomalous, starred nodes are the origins found) and the ranked root-cause chains with strength, bootstrap confidence, lag and temporal evidence.", true),
    H2("D", "Verifier"),
    ...table("LLM-Modulo verifier stress test", ["Test", "Cases", "Tolerance rule", "KAIROS"], [
      ["Corrupted numbers caught", "200", "59.5%", "**98.5%**"],
      ["Invented metric names caught", "50", "—", "**100%**"],
      ["Faithful rounding accepted", "200", "100%", "**100%**"],
      ["Faithful reports accepted", "5", "100%", "**100%**"],
    ], [2200, 700, 1100, 900]),
    P("Correct reports were corrupted by scaling and shifting one number, by renaming a metric, or by rounding a number to one decimal, which is faithful. A tolerance rule that accepts any value within 2% of a fact or with the same integer part caught only 59.5% of corrupted numbers, for instance accepting 7.03 for 6.71. Comparing at the written precision raised this to 98.5% (Table V), 39 points higher, so 96.3% fewer corrupted numbers reach a reader, without rejecting a single faithful rounding. In a live run on simulated company data, an LLM served through the Groq API produced a report that passed on the first attempt (Fig. 5)."),
    H2("E", "Ingestion and Large-File Transfer"),
    ...table("Moving a 2,000,000-row (105.6 MB) export", ["Method", "Time (s)", "On wire", "Speed-up"], [
      ["FTP, raw CSV", "16.90", "105.6 MB", "1.0×"],
      ["FTP, gzip CSV", "9.18", "27.1 MB", "1.8×"],
      ["**KAIROS Fast Transfer (gzip)**", "**2.76**", "27.1 MB", "**6.1×**"],
      ["**KAIROS Fast Transfer (zstd)**", "**2.63**", "29.4 MB", "**6.4×**"],
      ["**Fast Transfer, resumed after a 50% drop**", "1.65", "13.6 MB", "10.2×"],
      ["**KAIROS edge agent (KPIs only)**", "**1.34**", "**192.7 KB**", "**12.6×**"],
    ], [2300, 800, 900, 800]),
    P("Table VI and Fig. 2(b) show that Fast Transfer cut the transfer time by 83.7% compared with plain FTP and was 3.3 times faster than FTP with compression, while sending 74.3% fewer bytes and verifying every chunk with SHA-256. After a connection was dropped halfway, only the 14 missing chunks out of 27 were sent again. When only KPIs are needed, the edge agent reduced 2,000,000 rows to 2,160 KPI records and the bytes on the wire by 99.8%."),

    ...fig("pui_reports.png", 5.6, "Reports & Alerts page: an executive report written by an LLM and marked as verified by the LLM-Modulo critic, with delivery channels and the de-duplicated alert history.", true),
    H1("VIII", "Discussion"),
    P("The results show that a causal graph turns a list of correlated anomalies into a short, ordered explanation that matches the analyst's question: *what moved first?* The quality of the graph decides the quality of the answer. With the same ranking, the precise DYNOTEARS graph gave 100% exact origins, while graphs with spurious edges gave 40–60%, and simple heuristics were misled by large downstream effects or unrelated early anomalies. These are the situations that a manager meets every day, which is why a correlation-based dashboard often points to the symptom rather than the cause."),
    P("The verifier makes the plain-language report safe to send: the LLM supplies the wording, but every number and metric name is checked against computed facts, so a manager never acts on an invented figure. The ingestion layer keeps the cost close to zero, since one adapter per protocol replaces paid per-product connectors and Fast Transfer replaces slow FTP uploads. The complete cycle, from new data to a verified alert, finishes in a few seconds on a laptop, against hours of manual dashboard tracing."),

    H1("IX", "Future Scope"),
    P("KAIROS can be extended in several directions:", { noIndent: true }),
    ...bullets([
      "**Nonlinear and confounder-aware discovery** with PCMCI {j_pcmci}, TCDF {j_tcdf} and FCI-style search, so that the graph also captures threshold and saturation effects;",
      "**Pilot deployments** with partner companies and public e-commerce data, with a study of how much faster managers act on KAIROS alerts;",
      "**Claim-level verification** that checks qualitative statements, such as severity words and causal claims, building on recent fact-checking research {j_augenstein, j_farquhar};",
      "**Drill-down by dimension**, combining the causal graph with HotSpot-style localisation {j_hotspot} to say both which metric and which region or product caused a change;",
      "**What-if simulation** with DoWhy {j_dowhygcm} to estimate the effect of an action, such as restoring advertising spend, before it is taken;",
      "**Streaming ingestion** with change data capture and multi-tenant cloud deployment, and deep learned detectors {j_darban} for high-dimensional metrics.",
    ]),

    H1("X", "Conclusion"),
    P("KAIROS shows that business monitoring can be proactive, causal and verifiable using free, open components. DYNOTEARS recovered the benchmark structure with an F1 score of 0.974, 8.1–95.6% higher than three baselines; the ranking named every incident origin in 100% of runs, against at most 70% for the alternatives; the LLM-Modulo verifier stopped 98.5% of numerical errors, against 59.5% for a tolerance rule; and Fast Transfer moved large exports 6.1 times faster than FTP. The working dashboard brings these results to managers without a single query."),

    H1("", "Acknowledgment"),
    P(`The authors thank their faculty mentor, ${MENTOR}, School of Technology, Woxsen University, for the guidance and support given throughout this project.`),
  ];

  const refs = [
    new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { before: 160, after: 80 }, children: [new D.TextRun({ text: "References", font: FONT, size: S, smallCaps: true })] }),
    ...order.map((k, i) => new D.Paragraph({ alignment: D.AlignmentType.JUSTIFIED, spacing: { after: 20, line: 216 }, indent: { left: 400, hanging: 400 }, tabStops: [{ type: D.TabStopType.LEFT, position: 400 }],
      children: [new D.TextRun({ text: `[${i + 1}]\t`, font: FONT, size: 16 }), ...runs(byKey[k].ieee, { size: 16 })] })),
  ];

  // split the flow into two-column sections, with one-column sections for wide figures and tables
  const page = { size: { width: 12240, height: 15840 }, margin: { top: 1080, bottom: 1440, left: 900, right: 900 } };
  const two = { page, type: D.SectionType.CONTINUOUS, column: { count: 2, space: 360, equalWidth: true } };
  const one = { page, type: D.SectionType.CONTINUOUS, column: { count: 1 } };
  const sections = [{ properties: { page }, children: head }];
  let cur = [];
  for (const el of [...body, ...refs]) {
    if (el && el.wide) {
      if (cur.length) sections.push({ properties: two, children: cur });
      sections.push({ properties: one, children: el.wide });
      cur = [];
    } else cur.push(el);
  }
  sections.push({ properties: two, children: cur });
  sections.push({ properties: one, children: [new D.Paragraph({ children: [] })] });   // balances the last page's columns

  const doc = new D.Document({
    creator: [...AUTHORS, MENTOR].join(", "), title, keywords: KEYWORDS.join(", "),
    styles: { default: { document: { run: { font: FONT, size: S } } } },
    numbering: { config: [{ reference: "ib", levels: [{ level: 0, format: D.LevelFormat.BULLET, text: "•", alignment: D.AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 180 } } } }] }] },
    sections,
  });
  return D.Packer.toBuffer(doc).then(async (raw) => {
    const zip = await require("jszip").loadAsync(raw);
    const xml = (await zip.file("word/document.xml").async("string"))
      .replace(/<m:r><m:t>(min|tr|MAD)<\/m:t><\/m:r>/g, '<m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>$1</m:t></m:r>')
      .replace(/<m:r><m:t>([^<]*?)MAD\(/g, '<m:r><m:t>$1</m:t></m:r><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>MAD</m:t></m:r><m:r><m:t>(');
    zip.file("word/document.xml", xml);
    return zip.generateAsync({ type: "nodebuffer" });
  }).then((buf) => { fs.writeFileSync(IEEE_OUT, buf); console.log(`IEEE: ${IEEE_OUT}  words=${countWords(words)} refs=${order.length} figs=${figN} tables=${tabN}`); });
}

// ════════════════════════════════════════════════════════════════════════════
// APA 7 STUDENT PAPER
// ════════════════════════════════════════════════════════════════════════════
function buildAPA() {
  const used = new Set();
  const author = (k) => byKey[k].cite.replace(/, (n\.d\.|\d{4})$/, "").replace(" & ", " and ");
  const year = (k) => byKey[k].cite.match(/(n\.d\.|\d{4})$/)[1];
  // {a, b} -> (A, 2020; B, 2019)   {@a} -> A (2020)
  const cite = (t) => t
    .replace(/\{@([a-z0-9_]+)\}/g, (w, k) => { if (!byKey[k]) return w; used.add(k); return `${author(k)} (${year(k)})`; })
    .replace(/\{([a-z0-9_,\s]+)\}/g, (w, keys) => {
      const ks = keys.split(",").map((k) => k.trim());
      if (!ks.every((k) => byKey[k])) return w;
      ks.forEach((k) => used.add(k));
      return "(" + ks.map((k) => byKey[k].cite).join("; ") + ")";
    });
  const S = 24, L = 480;   // 12 pt, double spaced
  const words = [];
  const P = (t, o = {}) => { const c = cite(t); if (o.count !== false) words.push(c); return new D.Paragraph({ alignment: o.align || D.AlignmentType.LEFT, spacing: { line: L, after: 0 }, indent: o.noIndent ? undefined : { firstLine: 720 }, keepNext: o.keepNext, children: runs(c, { size: S }) }); };
  const C = (t, o = {}) => new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { line: L, after: 0 }, pageBreakBefore: o.pb, keepNext: true, children: runs(t, { size: S, bold: o.bold }) });
  const H1 = (t) => new D.Paragraph({ heading: D.HeadingLevel.HEADING_1, alignment: D.AlignmentType.CENTER, keepNext: true, spacing: { line: L, after: 0 }, children: [new D.TextRun({ text: t, font: FONT, size: S, bold: true })] });
  const H2 = (t) => new D.Paragraph({ heading: D.HeadingLevel.HEADING_2, keepNext: true, spacing: { line: L, after: 0 }, children: [new D.TextRun({ text: t, font: FONT, size: S, bold: true })] });
  const H3 = (t, rest) => { const c = cite(rest); words.push(c); return new D.Paragraph({ spacing: { line: L, after: 0 }, indent: { firstLine: 720 }, children: [new D.TextRun({ text: t + " ", font: FONT, size: S, bold: true, italics: true }), ...runs(c, { size: S })] }); };
  let tabN = 0, figN = 0;
  const table = (titleText, headers, rows, widths, note, align = []) => {
    tabN++;
    const total = 9360, sc = total / widths.reduce((a, b) => a + b, 0);
    const W = widths.map((x) => Math.round(x * sc)); W[W.length - 1] += total - W.reduce((a, b) => a + b, 0);
    const line = { style: D.BorderStyle.SINGLE, size: 6, color: "000000" }, none = { style: D.BorderStyle.NONE, size: 0, color: "FFFFFF" };
    const cell = (t, i, head, last) => new D.TableCell({ width: { size: W[i], type: D.WidthType.DXA }, margins: { top: 40, bottom: 40, left: 80, right: 80 },
      borders: { top: head ? line : none, bottom: head || last ? line : none, left: none, right: none },
      children: [new D.Paragraph({ alignment: i === 0 ? D.AlignmentType.LEFT : (align[i] || D.AlignmentType.CENTER), spacing: { line: 240, after: 0 }, children: runs(cite(String(t)), { size: 22 }) })] });
    return [
      new D.Paragraph({ keepNext: true, spacing: { line: L, after: 0, before: 240 }, children: [new D.TextRun({ text: `Table ${tabN}`, font: FONT, size: S, bold: true })] }),
      new D.Paragraph({ keepNext: true, spacing: { line: L, after: 0 }, children: [new D.TextRun({ text: titleText, font: FONT, size: S, italics: true })] }),
      new D.Table({ width: { size: total, type: D.WidthType.DXA }, columnWidths: W, borders: D.TableBorders.NONE,
        rows: [new D.TableRow({ tableHeader: true, cantSplit: true, children: headers.map((h, i) => cell(h, i, true, false)) }), ...rows.map((r, ri) => new D.TableRow({ cantSplit: true, children: r.map((v, i) => cell(v, i, false, ri === rows.length - 1)) }))] }),
      note ? new D.Paragraph({ spacing: { line: L, after: 240 }, children: [new D.TextRun({ text: "Note. ", font: FONT, size: 22, italics: true }), ...runs(cite(note), { size: 22 })] }) : new D.Paragraph({ spacing: { after: 240 }, children: [] }),
    ];
  };
  const fig = (file, widthIn, titleText, note) => {
    figN++;
    const full = path.join(FIG, file), { w, h } = pngSize(full), wpx = Math.round(widthIn * 96);
    return [
      new D.Paragraph({ keepNext: true, spacing: { line: L, after: 0, before: 240 }, children: [new D.TextRun({ text: `Figure ${figN}`, font: FONT, size: S, bold: true })] }),
      new D.Paragraph({ keepNext: true, spacing: { line: L, after: 0 }, children: [new D.TextRun({ text: titleText, font: FONT, size: S, italics: true })] }),
      new D.Paragraph({ alignment: D.AlignmentType.CENTER, keepNext: !!note, spacing: { after: 0 }, children: [new D.ImageRun({ type: "png", data: fs.readFileSync(full), transformation: { width: wpx, height: Math.round((wpx * h) / w) } })] }),
      note ? new D.Paragraph({ spacing: { line: L, after: 240 }, children: [new D.TextRun({ text: "Note. ", font: FONT, size: 22, italics: true }), ...runs(cite(note), { size: 22 })] }) : new D.Paragraph({ spacing: { after: 240 }, children: [] }),
    ];
  };

  const TITLE = "Moving Metrics, Not Data: Low-Cost Ingestion From Heterogeneous Sources for Proactive Business Intelligence";
  const titlePage = [
    new D.Paragraph({ spacing: { before: 2400, after: 0 }, children: [] }),
    C(`**${TITLE}**`),
    new D.Paragraph({ spacing: { line: L, after: 0 }, children: [] }),
    C(AUTHORS.join(", ")),
    C("School of Technology, Woxsen University"),
    C("Capstone Project-I"),
    C("[Instructor name]"),
    C("October 7, 2026"),
  ];

  const ABS = "Business intelligence systems that monitor metrics on their own must first collect data from systems that differ from company to company, and this step is usually the most expensive one. Managed extract-load tools charge by the number of rows copied, self-hosted platforms are heavy to operate, and bulk file transfer over a single FTP connection is slow for large exports. This paper describes the ingestion layer of KAIROS, an autonomous business intelligence agent, which is built on one principle: move computed metrics rather than raw data. Five protocol-level adapters (SQL, SFTP/FTP, files and object storage, REST, and push) replace per-product connectors; incremental watermarks and idempotent upserts make every sync repeatable; aggregation runs inside the source database or in an edge agent next to large files; and a chunked, compressed, parallel and resumable transfer service handles the cases in which a raw file must move. In a live demonstration, a 100,305-row ERP table was synchronised by sending 19.5 KB, and only one new file was downloaded from an FTP server holding fifteen. For a 105.6 MB export over links capped at 50 Mbit/s, the transfer service was 6.4 times faster than single-stream FTP, and edge aggregation sent 193 KB in 1.3 s.";
  const abstract = [
    C("**Abstract**", { pb: true }),
    P(ABS, { noIndent: true, count: false }),
    new D.Paragraph({ spacing: { line: L, after: 0 }, indent: { firstLine: 720 }, children: [new D.TextRun({ text: "Keywords: ", font: FONT, size: S, italics: true }), new D.TextRun({ text: "data ingestion, ELT, FTP, edge computing, file transfer, business intelligence, schema matching", font: FONT, size: S })] }),
  ];
  words.push(ABS);

  const body = [
    C(`**${TITLE}**`, { pb: true }),
    P("A business intelligence (BI) agent that watches metrics without being asked is only as useful as the data it can reach. In a typical mid-sized company, orders sit in an ERP database, marketing exports land in a shared folder every night, a logistics partner drops compressed files on an FTP server, and the support platform offers a paged REST API. Connecting all of these is often the costliest part of a BI project. Managed extract-load-transform (ELT) services such as Fivetran charge per monthly active row {fivetran}, open-source platforms such as Airbyte need several containers per connection {airbyte}, and each company combines different products, so a catalogue of per-product connectors never covers everyone."),
    P("This question was raised directly during the mid-term review of KAIROS, an autonomous causal BI agent built as a capstone project. The reviewers asked how data could come from any source when connectors are heavy and expensive, whether FTP could be used, and how large files would be handled, since FTP is slow for them. They also mentioned a tool built by another student that transfers large files directly. This paper answers those questions with the design and measurements of the KAIROS ingestion layer."),
    P("The central observation is that a monitoring system needs metrics, not records. Fifty key performance indicators at 15-minute resolution amount to about 4,800 rows a day, whereas the underlying order table may grow by millions of rows. If the aggregation runs where the data lives, the transfer problem largely disappears, a principle long used in large-scale data processing {mapreduce, dremel}. The rest of the design follows from this observation."),

    H1("Related Work"),
    P("Managed ELT services copy whole tables into a warehouse with maintained connectors {fivetran}; they are reliable but priced by volume and lock the customer to a vendor. Airbyte offers a large open-source connector catalogue but is designed for container platforms {airbyte}. Change data capture tools such as Debezium stream row-level changes from database logs {debezium}, which is efficient for replication but still moves raw rows. {@kleppmann} describes idempotent writes and incremental processing as the basis of reliable data pipelines, and both are used here."),
    P("For large files, FTP {rfc959} and its secure variants run over a single TCP connection whose throughput is bounded by window size and round-trip time {mathis}; opening several parallel connections raises throughput on long or lossy paths {hacker}. Commercial tools such as IBM Aspera combine their own transport protocol with resume and encryption {aspera}. Edge computing moves processing towards the data source to reduce bandwidth and latency {edge}. Automatic schema matching, as surveyed by {@rahm}, reduces the manual effort of mapping new sources; KAIROS applies a lightweight version of it."),

    H1("Design"),
    P("Figure 1 shows how the ingestion layer routes a source according to where its data lives and how large it is. Every route ends in the same canonical form, rows of source, metric name, timestamp and value, which are upserted into an embedded DuckDB store {duckdb} with that tuple as the primary key."),
    ...fig("fig_ingestion.png", 6.3, "Ingestion Routes by Data Location and Size", "Bottom row: results measured in the live demonstration described under Evaluation."),
    H2("Protocol Adapters Instead of Product Connectors"),
    P("Almost every business system exposes data through a small number of protocols, so KAIROS implements protocols rather than products. A SQL adapter covers any database with a SQLAlchemy driver; a file adapter reads CSV, Excel, Parquet and JSON, compressed or not, from local paths, globs, S3 or HTTPS; an SFTP/FTP adapter fetches scheduled exports {ssh}; a configurable REST adapter handles authentication headers, pagination and incremental parameters {rest}; and a push endpoint accepts records from webhooks and from the edge agent. Every adapter implements one contract that returns canonical rows and an updated state. A new company is therefore added by configuration, with secrets read from environment variables."),
    H2("Incremental, Repeatable Synchronisation"),
    P("Each source keeps a small state between runs. Database and REST sources keep a timestamp watermark that is passed to the next query as a `:since` parameter. File and FTP sources keep the name, size and modification time of every file already processed, so a sync downloads only files it has not seen; half-written files are skipped until they are older than a set age or a marker file appears. Because writes are upserts on the primary key, re-reading an overlapping window, which is necessary when the last hourly bucket was still filling, updates values instead of duplicating them {kleppmann}. Sources run in parallel with individual timeouts, so one slow system cannot delay the others."),
    H2("Aggregation Push-Down and the Edge Agent"),
    P("For database sources, the configured query performs the aggregation, for example summing order amounts by hour, so the database returns KPI rows instead of order rows. For large files, the file adapter asks DuckDB to aggregate while it streams the file, and a stand-alone edge agent does the same inside the company network before pushing only the resulting KPIs to KAIROS. Raw data never leaves the company in this route, which also helps with privacy."),
    H2("Fast Transfer for Raw Files"),
    P("Some cases still require the raw file, for example a historical backfill. The transfer service splits the file into chunks of 1 to 32 MB. Each chunk is compressed with gzip or Zstandard {zstd}, hashed with SHA-256 and uploaded over several parallel connections, with retries and exponential back-off for each chunk. The server checks the length and hash of every chunk, writes it at its offset in a pre-sized file and only then records it as received. After a dropped connection, the client asks for the list of missing chunks and sends only those. On completion, the server re-hashes the whole file and can ingest it immediately."),
    H2("Semantic Mapping of New Sources"),
    P("When a source is added, a Semantic Layer Auto-Construction (SLAC) step inspects a sample. It identifies the timestamp column, decides whether the data is in long form (one row per metric and time) or wide form (one column per metric), excludes identifier columns such as order numbers, and detects irregular timestamps that indicate raw records needing aggregation. It then proposes a complete mapping that the user can accept or edit, in the spirit of automatic schema matching {rahm}."),

    H1("Evaluation"),
    H2("Method"),
    P("Four simulated company systems were set up on one machine: a SQLite ERP database of 100,305 orders, a folder of three weekly marketing CSV exports, an FTP server holding fourteen daily compressed logistics files, and a paged REST API. Their schemas differ, so each needed its own mapping. For the transfer benchmark, a raw export of two million orders (105.6 MB as CSV) was moved by each method between two separate processes, with every TCP connection capped at 50 Mbit/s to emulate a wide-area link. The cap was applied in the same way to FTP and to the transfer service, and byte counts are exact."),
    H2("Results"),
    P("Table 1 lists the steps of the live demonstration. The first synchronisation collected 4,704 KPI rows from the four systems, and the ERP route sent only 19.5 KB because the grouping ran inside the database. A second synchronisation moved no new rows from the file, FTP or REST sources. When a new file was placed on the FTP server, only that file was downloaded."),
    ...table("Live Ingestion Demonstration", ["Step", "Result"], [
      ["First sync of four sources", "4,704 KPI rows; ERP sent 19.5 KB for 100,305 raw rows"],
      ["Second sync", "No new rows from FTP, files or REST; nothing duplicated"],
      ["New file on the FTP server", "Only that file (130 bytes) downloaded; 14 skipped"],
      ["Edge agent on a 105.6 MB export", "94.1 KB pushed (1,149 times less data)"],
      ["Fast Transfer of the same file", "28.7 MB sent in 1.7 s; SHA-256 verified"],
      ["Connection cut after 13 of 27 chunks", "Only the 14 missing chunks re-sent"],
    ], [3600, 5760], null, [D.AlignmentType.LEFT, D.AlignmentType.LEFT]),
    P("Table 2 and Figure 2 compare the transfer methods. Compressing the file before a single FTP upload almost halved the time, but most of the gain was spent on compression. The parallel transfer service was 6.1 times faster than plain FTP with gzip and 6.4 times faster with Zstandard, sending about a quarter of the bytes. After a simulated failure halfway through, completing the transfer took 1.65 s, because only the missing half was sent. The edge agent was the fastest route of all and reduced traffic by a factor of about 550."),
    ...table("Transfer of a 105.6 MB Raw Export Over Links Capped at 50 Mbit/s", ["Method", "Time (s)", "Bytes sent", "Speed-up"], [
      ["FTP, single stream, raw CSV", "16.90", "105.6 MB", "1.0×"],
      ["FTP, single stream, gzip", "9.18", "27.1 MB", "1.8×"],
      ["Fast Transfer, 8 streams, gzip", "2.76", "27.1 MB", "6.1×"],
      ["Fast Transfer, 8 streams, zstd", "2.63", "29.4 MB", "6.4×"],
      ["Fast Transfer, resumed after 50%", "1.65", "13.6 MB", "10.2×"],
      ["Edge agent (KPIs only)", "1.34", "192.7 KB", "12.6×"],
    ], [4400, 1500, 1700, 1760], "The gzip FTP time includes 4.8 s of compression. Speed-up is relative to single-stream FTP of the raw file.", [D.AlignmentType.LEFT, D.AlignmentType.RIGHT, D.AlignmentType.RIGHT, D.AlignmentType.RIGHT]),
    ...fig("pfig_benchmark.png", 5.2, "Transfer Time and Bytes on the Wire for Each Method", "FT = Fast Transfer. The right panel uses a logarithmic scale."),

    H1("Discussion"),
    P("The measurements support a simple answer to the review questions. Data can come from almost any system through five protocol adapters, configured rather than coded, at no licence cost. FTP is a valid route, and it is fast when it carries small, compressed, new files only. Large data should usually not be transferred at all: aggregating in the source database or with an edge agent turned a 105.6 MB problem into a few hundred kilobytes. When a raw file is genuinely needed, chunking, compression, parallel connections and resume recover most of the gap to the link capacity, which is the same set of techniques used by commercial high-speed transfer tools {aspera, hacker}."),
    P("The work has limitations. The benchmark ran on one machine with an emulated link, and real long-distance links with packet loss may show a different speed-up. The demonstration systems were simulated rather than taken from a partner company. Plain FTP was used in the demonstration for convenience, although production use requires SFTP or FTPS with read-only accounts. Change data capture was not implemented, and the SLAC mapping relies on rules for English column names."),

    H1("Conclusion"),
    P("The cost and speed of BI ingestion depend mostly on how much data is moved rather than on the protocol used to move it. By moving computed metrics instead of raw records, and by providing a resumable parallel transfer for the remaining cases, KAIROS connects heterogeneous company systems at negligible cost. Future work will measure the transfer service over real wide-area links, add change data capture for databases, and evaluate the approach with a partner company."),
  ];

  // APA reference list: alphabetical, hanging indent, double spaced
  const refs = [...used].sort((a, b) => byKey[a].apa.localeCompare(byKey[b].apa));
  const refParas = [
    C("**References**", { pb: true }),
    ...refs.map((k) => new D.Paragraph({ spacing: { line: L, after: 0 }, indent: { left: 720, hanging: 720 }, children: runs(byKey[k].apa, { size: S }) })),
  ];

  const header = new D.Header({ children: [new D.Paragraph({ alignment: D.AlignmentType.RIGHT, children: [new D.TextRun({ children: [D.PageNumber.CURRENT], font: FONT, size: S })] })] });
  const page = { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440, header: 720 } };
  const doc = new D.Document({
    creator: AUTHORS.join(", "), title: TITLE,
    styles: { default: { document: { run: { font: FONT, size: S } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", run: { font: FONT, size: S, bold: true, color: "000000" }, paragraph: { outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", run: { font: FONT, size: S, bold: true, color: "000000" }, paragraph: { outlineLevel: 1 } },
      ] },
    sections: [{ properties: { page }, headers: { default: header }, children: [...titlePage, ...abstract, ...body, ...refParas] }],
  });
  return D.Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(APA_OUT, buf); console.log(`APA:  ${APA_OUT}  words=${countWords(words)} refs=${refs.length}`); });
}

buildIEEE().then(buildAPA);
