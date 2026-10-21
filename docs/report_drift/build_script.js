// Final-evaluation presentation script (Word).  node build_script.js <out.docx>
const fs = require("fs");
const D = require("docx");
const OUT = process.argv[2];
if (!OUT || !/\.docx$/i.test(OUT)) throw new Error("usage: node build_script.js <out.docx>");
const FONT = "Calibri";
const TEAL = "1E7A78", DARK = "0D3D3C";

function runs(text, base = {}) {
  const out = [], re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0, m;
  const mk = (t, x = {}) => new D.TextRun({ font: FONT, size: 23, ...base, ...x, text: t });
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(mk(text.slice(last, m.index)));
    const t = m[0];
    out.push(t.startsWith("**") ? mk(t.slice(2, -2), { bold: true }) : mk(t.slice(1, -1), { italics: true }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(mk(text.slice(last)));
  return out;
}
const p = (t, o = {}) => new D.Paragraph({ spacing: { after: o.after ?? 120, line: 288 }, indent: o.indent ? { left: o.indent } : undefined, alignment: o.align, children: runs(t, o.run || {}) });
const say = (t) => new D.Paragraph({ spacing: { after: 120, line: 300 }, indent: { left: 360 }, border: { left: { style: D.BorderStyle.SINGLE, size: 18, color: TEAL, space: 10 } }, children: runs(t, { size: 24 }) });
const note = (t) => new D.Paragraph({ spacing: { after: 120, line: 276 }, indent: { left: 360 }, shading: { fill: "FBF7F0", type: D.ShadingType.CLEAR, color: "auto" }, children: [new D.TextRun({ text: "Tip: ", font: FONT, size: 21, bold: true, color: "8A6D3B" }), ...runs(t, { size: 21, color: "5A4A2A" })] });
const bullets = (items, ref = "b") => items.map((t) => new D.Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 60, line: 288 }, children: runs(t) }));
const H1 = (t, color = DARK, pb = true) => new D.Paragraph({ heading: D.HeadingLevel.HEADING_1, pageBreakBefore: pb, spacing: { before: 120, after: 160 }, children: [new D.TextRun({ text: t, font: FONT, size: 34, bold: true, color })] });
const H2 = (t) => new D.Paragraph({ heading: D.HeadingLevel.HEADING_2, keepNext: true, spacing: { before: 240, after: 80 }, children: [new D.TextRun({ text: t, font: FONT, size: 26, bold: true, color: TEAL })] });
const slide = (n, title, time) => new D.Paragraph({ keepNext: true, spacing: { before: 280, after: 80 }, shading: { fill: "EAF5F5", type: D.ShadingType.CLEAR, color: "auto" },
  children: [new D.TextRun({ text: `  Slide ${n}  `, font: FONT, size: 24, bold: true, color: "FFFFFF", shading: { fill: TEAL, type: D.ShadingType.CLEAR, color: "auto" } }), new D.TextRun({ text: `   ${title}`, font: FONT, size: 25, bold: true, color: DARK }), new D.TextRun({ text: `   (${time})`, font: FONT, size: 21, color: "6B7280" })] });

function table(headers, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  const b = { style: D.BorderStyle.SINGLE, size: 4, color: "BBBBBB" };
  const cell = (t, i, head) => new D.TableCell({ width: { size: widths[i], type: D.WidthType.DXA }, borders: { top: b, bottom: b, left: b, right: b },
    shading: head ? { fill: DARK, type: D.ShadingType.CLEAR, color: "auto" } : undefined, margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new D.Paragraph({ spacing: { after: 0 }, children: runs(t, { size: 21, bold: head || undefined, color: head ? "FFFFFF" : undefined }) })] });
  return new D.Table({ width: { size: total, type: D.WidthType.DXA }, columnWidths: widths,
    rows: [new D.TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, i, true)) }), ...rows.map((r) => new D.TableRow({ cantSplit: true, children: r.map((v, i) => cell(v, i, false)) }))] });
}
const code = (lines) => lines.map((l) => new D.Paragraph({ spacing: { after: 0 }, shading: { fill: "F2F2F2", type: D.ShadingType.CLEAR, color: "auto" }, children: [new D.TextRun({ text: l || " ", font: "Consolas", size: 18 })] }));

// ════════════════════════════════════════════════════════════════════════════
const cover = [
  new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { before: 1600, after: 120 }, children: [new D.TextRun({ text: "KAIROS", font: FONT, size: 72, bold: true, color: DARK })] }),
  new D.Paragraph({ alignment: D.AlignmentType.CENTER, spacing: { after: 360 }, children: [new D.TextRun({ text: "Final Evaluation – Presentation Script", font: FONT, size: 34, color: TEAL })] }),
  p("Capstone Project-I · Woxsen University, School of Technology", { align: D.AlignmentType.CENTER }),
  p("Guide: Dr. K RajKumar, Assistant Professor", { align: D.AlignmentType.CENTER, after: 480 }),
  table(["Speaker", "Part", "Slides", "Time"], [
    ["**Varshini Yadav Nasaram**", "Introduction: problem, gap, objectives, system architecture", "1 – 6", "≈ 4.5 min"],
    ["**Palla Chetana Reddy**", "How the platform works + live demo on the website", "7 – 10, Demo", "≈ 6.5 min"],
    ["**Obulagari Nandini**", "Results, challenges, future scope, conclusion", "11, 12, 14, 15", "≈ 3.5 min"],
  ], [2700, 3700, 1500, 1200]),
  p(" ", { after: 200 }),
  p("**Slide order used in this script:** move the Live Demo slide (currently 13) to right after slide 10, so Chetana's part flows without interruption. Slide numbers below refer to the original numbers in the deck.", { run: { size: 21 } }),
  p("**Total:** 15 minutes of presentation + 5 minutes of questions. Text in the teal bar is what to say; shaded “Tip” boxes are for you only.", { run: { size: 21 } }),
];

// ── VARSHINI ────────────────────────────────────────────────────────────────
const varshini = [
  H1("Part 1 – Varshini: Introduction & System Overview"),
  slide(1, "Title", "20 s"),
  say("Good morning, respected panel. I am Varshini, and with me are Chetana and Nandini. Our capstone project is **KAIROS – an Autonomous Causal Business Intelligence Agent**, guided by Dr. K RajKumar."),
  say("In one line: KAIROS watches a company's business numbers on its own, finds out *why* something went wrong, and tells the manager in plain English – without anyone having to ask."),
  slide(2, "Roadmap", "15 s"),
  say("We will start with the problem and the gap in existing tools, then our objectives. Chetana will explain how the system works and show a live demo, and Nandini will present the results, challenges and future work."),
  slide(3, "Problem – BI is reactive by design", "75 s"),
  say("Every company today runs on numbers – daily revenue, orders, delivery time, customer churn. These numbers sit in many places: an ERP database, Excel sheets, marketing exports, partner systems."),
  say("Tools like Power BI and Tableau are excellent, but they have one basic limitation: *they only answer questions when someone asks.* That is why we say – Power BI answers questions when you ask; KAIROS asks the questions for you."),
  say("This creates three problems. **First, they wait.** If revenue drops on a Friday night and nobody opens the dashboard, the problem is found only on Monday."),
  say("**Second, correlation is not causation.** Even when a tool explains a change, it shows which numbers moved together. If revenue and clicks both fell, which one caused the other? Correlation cannot tell – only direction and time lag can."),
  say("**Third, data is costly.** Every company uses different systems, connector tools charge per row, and moving large files over FTP is slow."),
  say("KAIROS closes this loop: **Detect, Explain, Verify, Alert.**"),
  slide(4, "The Gap", "50 s"),
  say("We compared three kinds of existing tools. **Dashboards** like Power BI are reactive and correlational. **AIOps root-cause tools** do use causal analysis, but only for IT servers – latency and errors – not business KPIs like revenue or churn. **ELT platforms** like Fivetran move data, but they do not analyse it, and they are priced by volume."),
  say("No single tool monitors on its own, explains the real cause, fact-checks its own report *and* brings in data cheaply. Only KAIROS combines all four – that is the gap we fill."),
  slide(5, "Five measurable objectives", "50 s"),
  say("We set five SMART objectives at the start of the semester, and we met all five:"),
  ...bullets([
    "**Autonomous pipeline** – a full monitoring cycle in **12.4 seconds**, running every 15 minutes.",
    "**Anomaly detection** – **100%** of the injected incidents were found.",
    "**Causal origin** – the correct root cause in **10 out of 10** runs.",
    "**Verified reports** – **98.5%** of wrong numbers caught before sending.",
    "**Low-cost ingestion** – **6.4 times** faster than FTP, at zero licence cost.",
  ]),
  slide(6, "System Architecture", "60 s"),
  say("Before Chetana explains the details, here is the complete system at a glance. On the left, data comes from five kinds of sources – **SQL databases, FTP servers, files, REST APIs and push**. It passes through our ingestion layer into a **DuckDB** database."),
  say("Then five agents run one after another, every 15 minutes, orchestrated by **LangGraph**: **Collect** pulls new data, **Detect** finds anomalies, **Investigate** finds the cause, **Report** writes the explanation, and **Alert** sends it on Telegram, email and the dashboard."),
  say("One important design point: if there is no new anomaly, the cycle stops right after Detect – so a quiet cycle costs almost nothing, and nobody gets the same alert twice."),
  say("Now Chetana will explain how each part actually works, and show it live."),
  note("Speak slowly on slide 3 – it sets up the whole talk. Point at each card as you say “first, second, third”."),
];

// ── CHETANA ─────────────────────────────────────────────────────────────────
const chetana = [
  H1("Part 2 – Chetana: How the Platform Works + Live Demo"),
  slide(7, "Reasoning Engine – three layers", "70 s"),
  say("Thank you, Varshini. The intelligence of KAIROS is in three layers. **Detect:** a robust seasonal z-score compares each value with its normal level and its normal pattern for that hour of the day. We use the median instead of the mean, so the anomalies themselves don't distort the baseline. Anything beyond 3.5 standard deviations is flagged."),
  say("**Explain:** this is the core of our project. An algorithm called **DYNOTEARS** learns a causal graph of all the metrics – which metric affects which, and after how much delay. When something goes wrong, we walk backwards through this graph to the **origin** of the problem."),
  say("**Verify:** a language model writes the report in plain English, but before it is sent, our **LLM-Modulo checker** verifies every number and every metric name against the real data. If anything is wrong, the report is rejected and rewritten. A wrong report never reaches the manager."),
  slide(8, "Answering the Review", "10 s"),
  say("In our second review, the panel asked an important question: *how will data come from any source, and isn't FTP slow for large files?* This section is our answer."),
  slide(9, "Move the computation, not the data", "75 s"),
  say("Our key idea is simple: **KAIROS needs metrics, not raw data.** So instead of buying one connector per product, we built five lightweight protocol adapters that cover almost every system."),
  ...bullets([
    "**Big database table** – the summing query runs *inside* the company's own database. 100,000 order rows reached us as just **19.5 KB**.",
    "**Scheduled exports** – yes, we support **FTP / SFTP**, but we download **only new files**, never the same file twice.",
    "**Large raw files** – a small **edge agent** summarises them next to the data. **106 MB became 94 KB.**",
    "**When the raw file really must move** – our **Fast Transfer**.",
    "**SaaS tools** – REST APIs or push webhooks.",
  ]),
  say("Five adapters, any source, and **zero licence cost**."),
  slide(10, "Fast Transfer", "50 s"),
  say("This also answers the point about large-file transfer tools. Fast Transfer **splits** the file into chunks, **compresses** each one, and sends them over **8 parallel streams**. Every chunk carries a **SHA-256 checksum**."),
  say("If the connection drops at 48%, we do not restart – we send **only the 14 missing chunks**, and then verify the whole file. No restart, no duplicates, no corrupted file. Let me show you all of this live."),

  H2("Live Demo (≈ 3 minutes) – in the browser at http://127.0.0.1:8000"),
  note("Keep the browser open on the Data Sources page before you start. If anything fails, switch to the Live Demo slide – the screenshots are your backup."),
  ...[
    ["**Data Sources → click “Sync all”.**", "“Four completely different systems synced – a database, CSV exports, an FTP server and a REST API. Look at the Transferred column: the ERP database sent only 19.5 KB for 100,000 orders.”"],
    ["**Click “Sync all” again.**", "“Zero new rows – it is incremental. Nothing is downloaded twice.”"],
    ["**Run the prepared FTP command, then click Sync on logistics_ftp.**", "“The partner just dropped one new file on the FTP server. KAIROS downloaded only that one file and skipped the other 14.”"],
    ["**Fast Transfer page → drag in BIG_erp_orders_2M.csv (106 MB).**", "“Watch the chunks turn green – 8 streams in parallel.” Click **Pause** around half, then **Resume**: “It continues from the missing chunks only.” When done, click **Ingest**."],
    ["**Overview → click “Run pipeline now”.**", "“KAIROS ran all five agents. Anomalies are found automatically and colour-coded by severity.” Click one anomaly to show its chart."],
    ["**Causal Analysis page.**", "“Look at the stars – KAIROS found **ad spend** and **delivery delay** as the origins, and shows the full chain: delivery delay → support tickets → response time → NPS → churn.” Hover over a chain to highlight it."],
    ["**Reports & Alerts page.**", "“This report was written by the language model, and the **verified** badge means every number in it was checked against the data.”"],
  ].flatMap(([action, line], i) => [
    new D.Paragraph({ numbering: { reference: "demo", level: 0 }, spacing: { after: 20, line: 288 }, children: runs(action) }),
    say(line),
  ]),
  say("So in a few minutes, KAIROS went from raw data in four different systems to a verified business explanation. Now Nandini will present our results and the road ahead."),
];

// ── NANDINI ─────────────────────────────────────────────────────────────────
const nandini = [
  H1("Part 3 – Nandini: Results, Challenges, Future Scope, Conclusion"),
  slide(11, "Performance Benchmark", "45 s"),
  say("Thank you, Chetana. We measured everything properly. We took **2 million rows – a 106 MB file** – and limited every connection to 50 megabits per second, to behave like a real network."),
  ...bullets([
    "Plain **FTP** took **16.9 seconds**.",
    "Our **Fast Transfer** took **2.6 seconds** – that is **6.4 times faster**.",
    "After a dropped connection, finishing took only **1.7 seconds**, because only the missing half was re-sent.",
    "The **edge agent** finished in **1.3 seconds** and sent just **193 KB** instead of 106 MB.",
  ]),
  say("So for most large data, the best transfer is *not to transfer the raw data at all.*"),
  slide(12, "Causal Discovery Results", "45 s"),
  say("To measure accuracy, we built a test dataset where we *know* the true causes, and repeated the experiment ten times."),
  ...bullets([
    "DYNOTEARS scored an **F1 of 0.97**, compared with 0.90 for Granger, 0.87 for VARLiNGAM and only **0.50 for simple correlation**.",
    "It created **zero false causal links** in ten runs.",
    "It found the **true origin in 10 out of 10** incidents.",
  ]),
  say("That is exactly the difference between *“these numbers moved together”* and *“this is what caused it.”*"),
  slide(14, "Novelty, Challenges & Roadmap", "75 s"),
  say("Our project makes four contributions: a **proactive BI loop** that monitors without being asked; the **Causal Business Metric Graph** for business KPIs; **verified LLM reports**; and **low-cost ingestion** from any source."),
  say("We also faced real challenges along the way:"),
  ...bullets([
    "The existing DYNOTEARS library **would not install** on our Python version, so we **implemented the algorithm ourselves** in NumPy and SciPy.",
    "Our first report checker caught only **61%** of wrong numbers – we redesigned it to compare at the precision written, and it now catches **98.5%**.",
    "The review question on data ingestion made us **redesign the data layer** – that led to the edge agent and Fast Transfer.",
  ]),
  say("We are also honest about the limits: our evaluation used a synthetic dataset with known answers, and the network was emulated on one machine. So in **Capstone-II** we will test on **real company datasets**, add **nonlinear causal methods like PCMCI**, run **real long-distance transfer tests**, and do a **study with managers** to see how they use the alerts."),
  slide(15, "Conclusion", "25 s"),
  say("To conclude: KAIROS moves business intelligence **from dashboards you check, to an agent that checks for you.** It finds problems early, explains their real cause, and verifies every number before anyone reads it – all on free, open-source software."),
  say("Thank you. We are happy to take your questions."),
  note("Pause after the quote on slide 15 before saying thank you. All three members should stand ready for questions."),
];

// ── Q&A + checklist ─────────────────────────────────────────────────────────
const qa = [
  H1("Questions & Answers – Preparation"),
  p("Any member can answer; suggested owner in brackets."),
  table(["Likely question", "Short answer"], [
    ["Is this real company data? *(Nandini)*", "It is a synthetic benchmark with known true causes, so accuracy can be measured exactly. Real datasets are planned for Capstone-II."],
    ["Why not just use correlation? *(Chetana)*", "Correlation has no direction and no time lag. On our test it scored F1 0.50, against 0.97 for DYNOTEARS."],
    ["What if the LLM gives wrong information? *(Chetana)*", "The LLM-Modulo checker verifies every number and metric name; 98.5% of injected errors were caught. If a draft fails twice, a template report that is correct by construction is sent."],
    ["Can you use FTP? Isn't it slow? *(Chetana)*", "Yes – as SFTP, fetching only new, small, compressed files. For big data the edge agent sends only the KPIs, and Fast Transfer is 6.4× faster than FTP."],
    ["How is this different from Power BI? *(Varshini)*", "Power BI waits for a user and explains by correlation. KAIROS monitors on its own, finds the causal origin and sends a verified alert."],
    ["What does it cost? *(Varshini)*", "Zero licence cost – everything is open source. The LLM runs on Groq's free tier or locally with Ollama."],
    ["How does it handle a new company with different systems? *(Chetana)*", "Five protocol adapters cover almost any system, and our SLAC module reads a sample and proposes the column mapping automatically."],
    ["What are the main limitations? *(Nandini)*", "Synthetic evaluation, emulated network, linear causal model, and the checker verifies numbers but not wording. All are planned for Capstone-II."],
  ], [3300, 5726]),

  H1("Demo Checklist (Chetana – 30 minutes before)", DARK),
  p("Open three terminals in the **Kairos** folder and run:"),
  ...code([
    "backend\\venv\\Scripts\\python scripts\\generate_demo_sources.py",
    "backend\\venv\\Scripts\\python scripts\\demo_servers.py",
    "backend\\venv\\Scripts\\python -m uvicorn backend.main:app --port 8000",
  ]),
  p(" "),
  ...bullets([
    "Open **http://127.0.0.1:8000** – check all pages load and Data Sources shows four sources.",
    "Check that **data\\demo\\BIG_erp_orders_2M.csv** exists (the 106 MB file for Fast Transfer).",
    "Keep this command ready in a fourth terminal for the “new FTP file” step:",
  ]),
  ...code(["backend\\venv\\Scripts\\python -c \"import pandas as pd;pd.DataFrame({'ts':[pd.Timestamp.now(tz='UTC').floor('h').isoformat()],'kpi':['delivery_delay_hrs'],'value':[1.3]}).to_csv('data/demo/ftp/kpis/logistics_NEW_drop.csv.gz',index=False,compression='gzip')\""]),
  p(" "),
  ...bullets([
    "Laptop on charger, notifications off, browser zoom 110–125% so the panel can read it.",
    "Backup: if anything fails, go to the Live Demo slide and explain using the screenshots.",
    "Rehearse the full 15 minutes at least three times with a timer.",
  ]),
];

const doc = new D.Document({
  creator: "KAIROS team", title: "KAIROS Final Evaluation – Presentation Script",
  styles: { default: { document: { run: { font: FONT, size: 23 } } } },
  numbering: { config: [
    { reference: "b", levels: [{ level: 0, format: D.LevelFormat.BULLET, text: "•", alignment: D.AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 300 } } } }] },
    { reference: "demo", levels: [{ level: 0, format: D.LevelFormat.DECIMAL, text: "%1.", alignment: D.AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 360 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1247, right: 1247 } } },
    footers: { default: new D.Footer({ children: [new D.Paragraph({ alignment: D.AlignmentType.CENTER, children: [new D.TextRun({ text: "KAIROS · Final Evaluation Script · ", font: FONT, size: 18, color: "6B7280" }), new D.TextRun({ children: [D.PageNumber.CURRENT], font: FONT, size: 18, color: "6B7280" })] })] }) },
    children: [...cover, ...varshini, ...chetana, ...nandini, ...qa],
  }],
});
D.Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("wrote", OUT); });
