# KAIROS — Gap Analysis

*Capstone Project-I, Woxsen University — Palla Chetana Reddy, Varshini Yadav Nasaram, Obulagari Nandini*

This document maps five gaps in current BI practice and research to what KAIROS actually implements,
and points to the code for each. Citations refer to `research/literature_review.md`.

The project claims three research contributions:

- **ProBI (Proactive Business Intelligence):** metrics are monitored, explained and alerted on with no human initiation.
- **CBMG (Causal Business Metric Graph):** DYNOTEARS temporal causal discovery is applied to business-KPI root-cause analysis.
- **SLAC (Semantic Layer Auto-Construction):** the ingestion mapping and business meaning of raw, heterogeneous schemas are inferred automatically.

These are supported by an engineering contribution, a **low-cost ingestion layer**: protocol-level
connectors, SFTP/FTP with new-file tracking, aggregation push-down, an edge agent and Fast Transfer.

---

## 1. Gap table

| Gap | Existing approaches | Limitation | KAIROS contribution | Where in the code |
|---|---|---|---|---|
| **G1. Reactive BI: a human must ask** | Dashboards and NL query in Power BI, Tableau, Looker, ThoughtSpot; per-visual anomaly markers (Ren et al., 2019); ReAct-style LLM analysts (Yao et al., 2023) | Nothing happens unless someone looks or asks. LLM agents choose their own actions, which is variable and costly for continuous monitoring | **ProBI**: a scheduled, fixed 5-node LangGraph loop (collect → detect → investigate → report → alert). It investigates only when new anomalies warranting an alert exist. Alert gating: first-seen only, within a 24 h look-back, at or above a minimum severity, per-metric cooldown | `backend/pipeline.py` (graph, `_alertable`), `backend/agents/anomaly_watchman.py` (persisted, de-duplicated anomalies), `backend/models/anomaly.py` (robust-z + Prophet ensemble, shared severity scale), `backend/agents/messenger.py` (Telegram / Gmail), `backend/config.py` (`pipeline_interval_min`, `alert_min_severity`, `alert_cooldown_min`) |
| **G2. "Root cause" in BI tools is correlation / decomposition** | Key-driver and decomposition visuals; Granger tests (Granger, 1969); AIOps RCA on infrastructure telemetry (CloudRanger, MicroCause, RCD) | Correlation has no direction or lag. Decomposition explains *where*, not *why*. AIOps RCA targets high-frequency system metrics, not cross-system business KPIs | **CBMG**: DYNOTEARS structural VAR (contemporaneous W + lagged A) on winsorised, standardised KPIs; bootstrap edge confidence; backward strongest-path walk; temporal-evidence scoring and origin detection; DoWhy effect estimates for direct edges; fallback chain DYNOTEARS → VARLiNGAM → Granger | `backend/models/dynotears.py`, `backend/models/cbmg.py`, `backend/agents/causal_investigator.py` (`_prepare`, `_discover`, `_stability`, `_rank`, `_dowhy_refine`) |
| **G3. Semantic layers are modelled by hand** | dbt Semantic Layer / MetricFlow, LookML; schema matching (Rahm & Bernstein, 2001); LLM data wrangling (Narayan et al., 2022) | Every source needs an engineer, and LLM output is unvalidated | **SLAC**: infers the timestamp column, long vs. wide format, metric columns and whether to aggregate raw records. Infers unit, category, KPI flag and `higher_is_better`. Heuristic first; the LLM (Groq → Ollama) is used only for semantics, and its JSON is accepted only if it validates against the real columns | `backend/models/slac.py` (`suggest_mapping`, `build`, `_heuristic`, `_parse`), `backend/services/ingest.py` (SLAC-inferred mapping on upload), `backend/agents/nl_reporter.py` (uses `higher_is_better` to phrase moves) |
| **G4. LLM narratives are unverified** | LLM summaries in BI copilots; data-to-text generation (Wiseman et al., 2017); faithfulness metrics (Dhingra et al., 2019) | Fluent but possibly fabricated numbers or metric names (Ji et al., 2023), and self-critique is unreliable (Kambhampati et al., 2024) | **LLM-Modulo reporter**: the LLM writes from computed FACTS. An external critic checks every number (with tolerance) and every snake_case metric name. One critique-and-retry round, then a deterministic template that is correct by construction. `verified`, `engine` and `attempts` are stored with each alert | `backend/agents/nl_reporter.py` (`verify`, `_allowed_numbers`, `_template`), `backend/pipeline.py` (`_report`, `_alert` persist the metadata) |
| **G5. Expensive per-product connectors and slow bulk file transfer** | Managed ELT (Fivetran, Airbyte) with per-product connectors; CDC (Debezium); plain FTP exports; parallel striped transfer (GridFTP) | Full-table replication to compute a few KPIs; connector catalogues are costly to maintain; CDC needs privileged DB access; single-stream FTP is slow and not resumable | **Protocol-level ingestion**: one contract `fetch(state) → (df, state, stats)` with persisted incremental state; SQL / file / SFTP / FTPS / FTP / REST / Sheets / push connectors; **aggregation push-down** into the source query or DuckDB; **SFTP new-file tracking** (name + size + mtime, skipping in-progress files); **edge agent** that aggregates locally and pushes KPIs; **Fast Transfer** with chunked, parallel, gzip/zstd, resumable, SHA-256-verified uploads | `backend/connectors/base.py`, `backend/connectors/registry.py`, `backend/connectors/sql_connector.py`, `backend/connectors/file_connector.py`, `backend/connectors/sftp_connector.py`, `backend/connectors/rest_connector.py`, `backend/connectors/sheets_connector.py`, `backend/agents/data_collector.py`, `backend/api/ingest.py`, `backend/services/transfer.py`, `backend/services/ingest.py`, `edge_agent/kairos_edge.py` |

---

## 2. Narrative

### G1: From reactive to proactive (ProBI)

The defining property of today's BI is that it is **pull-based**. Value appears only when a person
opens a dashboard and asks the right question. LLM agents such as ReAct lower the cost of asking, but
they do not remove the need to ask. KAIROS treats monitoring as a *workflow* rather than a
*conversation*. `KAIROSPipeline` compiles a LangGraph `StateGraph` with a conditional edge after
detection, so the expensive steps (causal discovery, LLM calls, delivery) run only when there is
something new to say. Anomalies are persisted with a primary key, so the same historical spike never
triggers twice. A severity floor and a per-metric cooldown keep alert volume low. The LLM never decides
what the agent does, which makes each cycle reproducible and inexpensive.

### G2: From correlation to directed, lagged mechanisms (CBMG)

A drop in revenue is correlated with many things at once. What an operator needs is the **upstream
origin** and the **path** by which it spread. KAIROS learns a structural VAR with DYNOTEARS.
Contemporaneous edges are kept acyclic by the NOTEARS constraint, and lagged edges give direction in
time. Before learning, the anomalies themselves are winsorised away so the graph reflects normal
behaviour, and the data is standardised, which addresses the scale sensitivity raised by Reisach et
al. (2021). Edges at |w| ≥ 0.15 form the CBMG. Ranking combines path strength, bootstrap stability and
the temporal order of the anomalies themselves. A cause that was anomalous *before* the effect, and has
no anomalous ancestor of its own, is reported as an **origin**. On the bundled synthetic data, where the
ground truth is known (`backend/demo/synthetic.py`, `TRUE_EDGES`), notebook
`notebooks/03_causal_analysis.ipynb` measures how much of the true graph is recovered.

### G3: Semantic layer without an analytics engineer (SLAC)

KAIROS has to understand a new source without anyone writing YAML. SLAC does just enough semantic
modelling for monitoring. It finds the time axis. It tells long format (metric name + value) from wide
format (one column per metric). It detects raw transactional data (irregular or duplicate timestamps)
and proposes hourly aggregation with a record count. It also labels each metric's direction of
goodness, so that a rise in `delivery_delay_hrs` is described as unfavourable. The deterministic
heuristic means SLAC works offline. The LLM path adds richer semantics, but only after validation.

### G4: Trustworthy narratives (LLM-Modulo)

The reporter is designed so that **no unverified number reaches an executive**. The verifier is
deterministic and sound for what it checks: numeric tokens and metric identifiers. Small integers
(≤ 12) are exempt, so list numbering and counts of actions do not cause false rejections. When the LLM
cannot produce a passing draft, the system degrades to a template rather than to silence.

### G5: Cheap, fast ingestion

Monitoring needs **KPIs, not tables**. KAIROS integrates through protocols that almost every system
already speaks: SQL, files and object storage, (S)FTP, HTTP/JSON, Sheets and webhooks. It does not
build a connector per SaaS product. Computation moves to the data. SQL connectors aggregate inside
the source database with a `:since` watermark. The file connector lets DuckDB run the GROUP BY
out-of-core. The edge agent does the same inside the customer's network and sends only KPI rows.
When a raw file must be moved, Fast Transfer splits it into chunks (8 MB by default), compresses each
chunk, uploads chunks in parallel, resumes only the missing ones, and verifies each chunk and the
reassembled file by SHA-256.

---

## 3. Limitations and future work

We state these honestly so that the claims above are read in the right scope.

1. **Anomaly Transformer is not implemented.** The README lists it, but the running detector is a
   seasonal robust z-score + Prophet ensemble (`backend/models/anomaly.py`). A head-to-head comparison
   with the Anomaly Transformer (and other deep detectors) on labelled benchmarks is future work.
2. **Evaluation uses synthetic data.** The quantitative evaluation (notebooks 01–03) uses
   `backend/demo/synthetic.py`. This is a linear, Gaussian-noise structural VAR with hourly sampling,
   lag-1 edges and injected incidents, so it matches DYNOTEARS' assumptions by design. Results on it are
   an upper bound and a sanity check, not evidence of real-world accuracy. The README lists Olist,
   Superstore and Northwind as evaluation datasets, but they do not come with ground-truth causal
   graphs. Evaluating there will need expert-annotated incidents or semi-synthetic interventions.
3. **Causal sufficiency.** DYNOTEARS (and VARLiNGAM) assume that no unobserved common cause drives
   two monitored metrics. In business data this is often violated (promotions, holidays, outages,
   macro factors). Edges may then reflect confounding. Methods that tolerate latent confounders
   (e.g. FCI-style or LPCMCI-style approaches) are future work.
4. **Linear SVAR assumption.** The model is linear with additive noise. Saturation, thresholds and
   multiplicative effects (revenue = orders × AOV) are only approximated. Nonlinear extensions
   (e.g. PCMCI with nonlinear CI tests, or neural DYNOTEARS variants) could be explored.
5. **Stationarity and sampling rate.** The graph is learned on a recent window, up to 1,500 points
   per metric and at most `causal_max_vars` = 20 variables, which assumes stable structure inside
   that window. Mechanisms faster than the sampling interval appear as contemporaneous edges, whose
   direction is harder to identify.
6. **Thresholds are hand-set.** The edge threshold (0.15), L1 penalties (0.05), z-threshold (3.5) and
   severity cut-offs were chosen by inspection, not tuned with cross-validation.
7. **Bootstrap confidence is coarse.** By default only 2 block-bootstrap refits plus the full fit are
   used, so confidence takes few distinct values. More refits would cost more runtime.
8. **The verifier is narrow.** The LLM-Modulo critic checks numbers and metric names, not whether a
   causal sentence matches the CBMG, nor recommendations or tone. Extending it to check causal claims
   is future work.
9. **SLAC is heuristic-first and limited in scope.** It does not model joins, filters or composite
   metric definitions, and its keyword heuristics are English-centric.
10. **Ingestion benchmark is localhost-based.** `benchmark/benchmark_ingestion.py` measures single-stream
    FTP, Fast Transfer and edge aggregation on a 2M-row (≈106 MB) export (results in
    `benchmark/results/results.md`), but the WAN is *emulated* by a per-connection throughput cap on
    localhost. Measurements over a real wide-area link, and against full-table ELT tools, remain future work.
11. **No user study.** The usefulness of alerts to business users, and their false-alarm tolerance,
    has not been evaluated.
