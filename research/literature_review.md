# KAIROS — Literature Review

*Capstone Project-I, Woxsen University — Palla Chetana Reddy, Varshini Yadav Nasaram, Obulagari Nandini*

KAIROS is a five-agent pipeline (collect → detect → investigate → report → alert) that monitors business
metrics without being asked, explains anomalies with a learned temporal causal graph, and delivers
verified natural-language alerts. This review covers the seven research areas the system draws on.
For each one it summarises what prior work does, where it falls short for proactive business
intelligence (BI), and how KAIROS relates to it. We describe KAIROS only as it is implemented in
`backend/`. Where the README names a technique the code does not use (for example the Anomaly
Transformer), we say so.

---

## 1. Proactive / autonomous BI and agentic data analysis

**Prior work.** Commercial BI platforms (Power BI, Tableau, Looker, ThoughtSpot) are built around a
human who opens a dashboard or types a question. Their "augmented analytics" features, such as
anomaly markers on a line chart, "explain this data point", or key-driver visuals, run when a user
looks at a particular visual. Microsoft has published the anomaly detection service that sits behind
some of these features (Ren et al., 2019). It is a strong per-series detector, but it is offered as a
service that someone must call or configure. It does not monitor many sources on its own.

Large language models (LLMs) have made *agentic* analysis feasible. ReAct (Yao et al., 2023) interleaves
reasoning traces with tool calls ("thought → action → observation"), which allows an LLM to query data,
inspect results and decide its next step. Related work on tool use (Schick et al., 2023) and surveys of
LLM-based autonomous agents (Wang et al., 2024) describe a fast-growing design space of agents that
plan, call tools and keep memory. AIDA (arXiv 2605.07202) is cited in the project README as recent work
on AI-driven data analysis. We have not reproduced its results, so we only note that it is related work.

**Limitations.** Agentic analysts in the ReAct style still *answer* questions. A human sets the goal,
and the LLM chooses what to do next. That is the wrong reliability profile for monitoring, where the
same steps must run every cycle and where an LLM's free choice of actions is a source of variance and
cost. Built-in BI anomaly features detect, but they do not explain across sources, and they need a
human to be looking.

**KAIROS.** KAIROS reverses the initiative. A scheduler triggers a **fixed** LangGraph state machine
(`backend/pipeline.py`) every cycle, with no human prompt. The graph routes conditionally: it
investigates only when new anomalies that warrant an alert exist (new, recent, at or above a minimum
severity, and outside a cooldown window). The LLM appears in two bounded roles only, semantic
annotation (SLAC) and report writing. In neither role does it choose actions. We call this setting
**ProBI (Proactive BI)**. KAIROS borrows the "agent" decomposition from the agentic literature but
replaces open-ended tool selection with a deterministic workflow.

---

## 2. Time-series anomaly detection

**Prior work.** Classical detection rests on statistics. Chandola et al. (2009) survey the field. For
contaminated data, robust estimators of scale such as the median absolute deviation (MAD) are preferred
over the standard deviation, because the outliers being sought inflate the standard deviation and
hide themselves (Rousseeuw & Croux, 1993; Leys et al., 2013). Seasonal decomposition combined with
robust statistics underlies production detectors such as Twitter's Seasonal Hybrid ESD (Hochenbaum
et al., 2017). **Prophet** (Taylor & Letham, 2018) fits a decomposable additive model (trend + seasonality
+ holidays) and returns forecast intervals, so points outside the interval are natural anomaly
candidates. Deep models learn normal behaviour from data. The **Anomaly Transformer** (Xu et al., 2022)
introduced "association discrepancy" between a learned prior association and the series' self-attention
associations, and reported strong results on multivariate benchmarks.

**Limitations.** Deep detectors need sizeable training data per deployment, GPU-friendly
infrastructure and careful threshold calibration, and their scores are hard to explain to business
users. Prophet is interpretable but slower and can be thrown off by the very outliers it is meant to
find. Plain z-scores are not robust. Most detectors also report a score on a scale specific to that
detector, so "severity" means different things depending on which model fired.

**KAIROS.** The implemented detector (`backend/models/anomaly.py`) is an **ensemble of a seasonal robust
z-score and Prophet**. The robust z-score uses a rolling median, plus an hour-of-day seasonal profile
when that profile actually reduces residual spread, with scale σ = 1.4826 × MAD. For Prophet, σ is
derived from the 99 % prediction interval. Both detectors score in robust sigmas, so one severity
scale (low / medium / high / critical at 3.5 / 4.5 / 6 / 9σ) holds whichever detector fires. Agreement
of both detectors is reported as higher confidence (`prophet+robust_z`). **The Anomaly Transformer
named in the README is not implemented.** We chose the robust + Prophet ensemble because it needs no
training, is fast enough to run every 15 minutes on many series, and its output can be explained. It
remains a candidate for future comparison.

---

## 3. Causal discovery for time series

**Prior work.** **Granger causality** (Granger, 1969) tests whether the past of X improves prediction of
Y. It is cheap and widely used, but it captures predictive precedence, not intervention-level causation,
and it is confounded by unobserved common drivers. Constraint-based methods (PC/FCI; Spirtes et al., 2000)
were extended to time series by **PCMCI** (Runge et al., 2019), which uses conditional-independence
tests with momentary conditioning to keep false positives under control in high-dimensional,
autocorrelated data. Functional-model approaches exploit non-Gaussianity. LiNGAM (Shimizu et al., 2006)
and its time-series extension **VARLiNGAM** (Hyvärinen et al., 2010) identify a structural VAR with
contemporaneous and lagged effects.

**NOTEARS** (Zheng et al., 2018) recast DAG learning as continuous optimisation. Acyclicity is encoded
by the smooth constraint h(W) = tr(e^{W∘W}) − d = 0 and solved with an augmented Lagrangian. **DYNOTEARS**
(Pamfil et al., 2020) extends this to time series. It jointly learns contemporaneous weights W (which
must be acyclic) and lagged weights A₁…A_p of a structural VAR, with L1 sparsity. Assaad et al. (2022)
survey and benchmark these families. For estimating effects once a graph is known, **DoWhy** (Sharma &
Kiciman, 2020) implements Pearl's (2009) identify → estimate → refute workflow.

**Limitations.** All these methods rest on strong assumptions: causal sufficiency (no hidden
confounders) for DYNOTEARS, PCMCI and VARLiNGAM; linearity for DYNOTEARS and VARLiNGAM; stationarity;
and sampling at the timescale of the causal mechanism. Continuous-optimisation methods are also
sensitive to the scale of the variables. Reisach et al. (2021) show that NOTEARS-style benchmarks can
be "gamed" by variance ordering (varsortability), so standardisation matters. Finally, the causal
discovery literature is mostly evaluated on benchmarks. It is rarely connected to an operational loop
that must explain a specific anomaly in business terms.

**KAIROS.** `backend/models/dynotears.py` is a self-contained numpy/scipy implementation of DYNOTEARS.
It solves for the positive and negative parts of the weights with L-BFGS-B under an augmented
Lagrangian, forbids contemporaneous self-loops and allows lagged autoregression. The Causal
Investigator (`backend/agents/causal_investigator.py`) first **winsorises** the anomalies themselves
(clipping at median ± 3.5·MAD), so the learned structure reflects normal behaviour. It then
**standardises** the data, which follows the varsortability concern above, and runs DYNOTEARS. If that
fails, it falls back to VARLiNGAM (causal-learn) and then to a lagged-regression Granger matrix. Edge
confidence comes from block-bootstrap refits, and DoWhy backdoor linear regression estimates
standardised effects for direct edges. The resulting graph is the **CBMG** (Causal Business Metric
Graph, `backend/models/cbmg.py`). The novelty claimed is the *application* of DYNOTEARS-style temporal
discovery to business-KPI root-cause analysis inside an autonomous loop, not a new discovery algorithm.

---

## 4. Root cause analysis (RCA) in AIOps and business metrics

**Prior work.** The AIOps community has studied RCA for microservices and cloud systems extensively.
CloudRanger (Wang et al., 2018) builds an impact graph among services with a PC-style algorithm and
ranks candidates with a random walk. MicroCause (Meng et al., 2020) adds temporal causal discovery and
an attention-based walk. RCD (Ikram et al., 2022) localises root causes by targeted causal discovery,
treating the failure as an intervention. Soldani and Brogi (2022) survey anomaly detection and RCA
for service-based applications.

**Limitations.** These systems target infrastructure telemetry such as latency, CPU and error rates,
collected at high frequency from one observability stack. Business KPIs differ. They arrive from
heterogeneous systems (ERP, marketing tools, spreadsheets) at coarse, irregular granularity, with
strong seasonality and long causal delays (hours or days). They also have to be explained to
non-engineers. In commercial BI, "root cause" features generally decompose a metric by dimensions or
rank correlated drivers. They do not report a directed, time-lagged mechanism.

**KAIROS.** KAIROS carries the AIOps idea of "graph + walk" over to business metrics. The investigator
walks the CBMG backwards from each anomalous metric. For every ancestor it computes the strongest path,
defined as the maximum product of |weights|. Each candidate is scored by per-hop strength × bootstrap
confidence × **temporal evidence** (did the cause itself become anomalous shortly before the
effect?). Candidates that are anomalous and have no anomalous upstream ancestor are flagged as
**origins**. The output is a chain with direction, sign and lag (e.g. ad_spend_usd → click_through_rate
→ conversion_rate → order_count). Like the AIOps work, it inherits the assumptions of its discovery
method.

---

## 5. LLMs for data-to-text reporting and verification

**Prior work.** Neural data-to-text generation has long been known to produce fluent but unsupported
statements (Wiseman et al., 2017). Faithfulness and hallucination are now central topics in NLG (Maynez
et al., 2020; Ji et al., 2023), and metrics such as PARENT check generated text against the source table
(Dhingra et al., 2019). In their ICML 2024 position paper, Kambhampati et al. argue that LLMs cannot
reliably plan or verify their own output, and that they should be wrapped in an **LLM-Modulo**
framework: the LLM generates candidates, and sound external critics accept or reject them.

**Limitations.** Asking the LLM to "be accurate" is not a guarantee. Self-critique by the same model
shares its blind spots. An executive alert that quotes a wrong revenue figure is worse than no alert.

**KAIROS.** The NL Reporter (`backend/agents/nl_reporter.py`) puts LLM-Modulo into practice. The LLM
(Groq, then local Ollama) receives a list of computed FACTS. A deterministic critic then extracts every
number and every snake_case metric identifier from the draft and checks each one against the allowed
numbers (within a tolerance) and the known metric names. A failing draft is returned once with the
critique. If it fails again, or no LLM is available, a template report that is correct by construction
is sent. Every report records `verified`, `engine` and `attempts`. The critic is narrow: it checks
numbers and names, not the logic of causal claims. We discuss this in the gap analysis.

---

## 6. Semantic layers and schema understanding

**Prior work.** Industry semantic layers such as the dbt Semantic Layer (MetricFlow) and Looker's LookML
let analytics engineers declare metrics, dimensions and joins once, so every tool computes "revenue" the
same way. Automatic schema matching has a long research history (Rahm & Bernstein, 2001). More recently,
foundation models have been shown to perform entity matching, schema matching and data-cleaning tasks
with few or no examples (Narayan et al., 2022). LLMs are also widely used for text-to-SQL (Yu et al., 2018
introduced the Spider benchmark; Rajkumar et al., 2022 evaluated LLMs on it).

**Limitations.** Declarative semantic layers are written by hand. Every new source needs an engineer to
model it, which is exactly the cost that keeps small organisations from monitoring their data. LLM-based
matching is promising, but its outputs are probabilistic and need validation before they can drive
automated decisions.

**KAIROS.** SLAC (`backend/models/slac.py`) infers two things. First, the **ingestion mapping**: the
timestamp column, long vs. wide format, the metric columns, and whether irregular raw records should be
aggregated to hourly KPIs. Second, the **business semantics** of each metric: unit, category, whether it
is a KPI, and whether higher is better. A deterministic heuristic is always computed first. An LLM is
consulted for semantics only, and its JSON is accepted only if it parses and references real columns.
The reporter uses `higher_is_better` to say whether a move is unfavourable. SLAC does not try to model
joins or complex metric definitions the way LookML does. It covers the minimal semantic layer that
monitoring needs.

---

## 7. Data integration and ingestion cost

**Prior work.** Managed ELT services (Fivetran, Airbyte) maintain catalogues of per-product connectors
that replicate source tables into a warehouse. Change data capture (CDC) tools such as Debezium stream
row-level changes from database logs (Kleppmann, 2017, discusses CDC and log-based integration). The
database literature has long pushed computation towards the data: query push-down, and in-network
aggregation as in TAG for sensor networks (Madden et al., 2002). Edge computing generalises the idea of
processing near the source (Shi et al., 2016). Embedded analytical engines such as DuckDB (Raasveldt &
Mühleisen, 2019) make out-of-core aggregation available in-process. For bulk movement of large files,
parallel striped transfer (GridFTP; Allcock et al., 2005) addresses the limits of a single TCP stream.

**Limitations.** Replicating whole tables to compute a handful of hourly KPIs moves orders of magnitude
more data than monitoring needs. Per-product connector catalogues are costly to build and maintain.
CDC requires database-level access that many small businesses cannot grant. Plain FTP exports are
universal, but each file is a single uncompressed stream, and a dropped connection means starting over.

**KAIROS.** The ingestion layer (`backend/connectors/`) is built on **protocols rather than products**:
SQL via SQLAlchemy, files via DuckDB (local, S3/GCS/HTTP), SFTP/FTPS/FTP, generic REST with
pagination and `since` parameters, Google Sheets, and push/webhook. All of them share one contract,
`fetch(state) → (df, state, stats)`, with persisted incremental state. Aggregation is **pushed down** to
the source query (SQL) or to DuckDB (files), so only KPI rows travel. The SFTP connector downloads only
files it has not seen (name + size + mtime) and skips files that are still being written. The **edge
agent** (`edge_agent/kairos_edge.py`) aggregates large files locally and pushes only KPIs. **Fast
Transfer** (`backend/services/transfer.py`) provides chunked, parallel, compressed (gzip/zstd),
resumable, SHA-256-verified uploads for the cases where the raw file itself is needed. We make no
quantitative throughput claims, because no benchmark has been run yet.

---

## Summary

| Area | Representative prior work | What KAIROS takes | What KAIROS adds |
|---|---|---|---|
| Agentic BI | ReAct, LLM agents | agent decomposition | fixed, unprompted LangGraph loop (ProBI) |
| Anomaly detection | MAD, Prophet, Anomaly Transformer | robust stats + Prophet | shared robust-sigma severity scale |
| Causal discovery | NOTEARS, DYNOTEARS, VARLiNGAM, PCMCI, DoWhy | DYNOTEARS + DoWhy | applied to business KPIs, bootstrap confidence (CBMG) |
| RCA | CloudRanger, MicroCause, RCD | graph walk | temporal-evidence origin detection on KPIs |
| LLM reporting | LLM-Modulo, data-to-text faithfulness | generate-then-verify | numeric/metric critic with verified template fallback |
| Semantic layer | dbt SL, LookML, LLM schema matching | — | automatic mapping + semantics (SLAC) |
| Ingestion | Fivetran/Airbyte, Debezium, TAG, GridFTP | push-down, chunked parallel transfer | protocol connectors, edge agent, Fast Transfer |

---

## References

- Allcock, W., Bresnahan, J., Kettimuthu, R., Link, M., Dumitrescu, C., Raicu, I., & Foster, I. (2005). The Globus striped GridFTP framework and server. *Proc. ACM/IEEE Supercomputing (SC'05)*.
- Assaad, C. K., Devijver, E., & Gaussier, E. (2022). Survey and evaluation of causal discovery methods for time series. *Journal of Artificial Intelligence Research*, 73, 767–819.
- Chandola, V., Banerjee, A., & Kumar, V. (2009). Anomaly detection: A survey. *ACM Computing Surveys*, 41(3).
- Dhingra, B., Faruqui, M., Parikh, A., Chang, M.-W., Das, D., & Cohen, W. (2019). Handling divergent reference texts when evaluating table-to-text generation. *ACL 2019*.
- Granger, C. W. J. (1969). Investigating causal relations by econometric models and cross-spectral methods. *Econometrica*, 37(3), 424–438.
- Hochenbaum, J., Vallis, O. S., & Kejariwal, A. (2017). Automatic anomaly detection in the cloud via statistical learning. arXiv:1704.07706.
- Hyvärinen, A., Zhang, K., Shimizu, S., & Hoyer, P. O. (2010). Estimation of a structural vector autoregression model using non-Gaussianity. *Journal of Machine Learning Research*, 11, 1709–1731.
- Ikram, A., Chakraborty, S., Mitra, S., Saini, S., Bagchi, S., & Kocaoglu, M. (2022). Root cause analysis of failures in microservices through causal discovery. *NeurIPS 2022*.
- Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., et al. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys*, 55(12).
- Kambhampati, S., Valmeekam, K., Guan, L., Verma, M., Stechly, K., Bhambri, S., Saldyt, L., & Murthy, A. (2024). Position: LLMs can't plan, but can help planning in LLM-Modulo frameworks. *ICML 2024*.
- Kleppmann, M. (2017). *Designing Data-Intensive Applications*. O'Reilly Media.
- Leys, C., Ley, C., Klein, O., Bernard, P., & Licata, L. (2013). Detecting outliers: Do not use standard deviation around the mean, use absolute deviation around the median. *Journal of Experimental Social Psychology*, 49(4), 764–766.
- Madden, S., Franklin, M. J., Hellerstein, J. M., & Hong, W. (2002). TAG: A Tiny AGgregation service for ad-hoc sensor networks. *OSDI 2002*.
- Maynez, J., Narayan, S., Bohnet, B., & McDonald, R. (2020). On faithfulness and factuality in abstractive summarization. *ACL 2020*.
- Meng, Y., Zhang, S., Sun, Y., et al. (2020). Localizing failure root causes in a microservice through causality inference. *IEEE/ACM IWQoS 2020*.
- Narayan, A., Chami, I., Orr, L., & Ré, C. (2022). Can foundation models wrangle your data? *Proc. VLDB Endowment*, 16(4).
- Pamfil, R., Sriwattanaworachai, N., Desai, S., Pilgerstorfer, P., Beaumont, P., Georgatzis, K., & Aragam, B. (2020). DYNOTEARS: Structure learning from time-series data. *AISTATS 2020*. arXiv:2002.00498.
- Pearl, J. (2009). *Causality: Models, Reasoning, and Inference* (2nd ed.). Cambridge University Press.
- Raasveldt, M., & Mühleisen, H. (2019). DuckDB: An embeddable analytical database. *SIGMOD 2019 (demo)*.
- Rahm, E., & Bernstein, P. A. (2001). A survey of approaches to automatic schema matching. *The VLDB Journal*, 10(4), 334–350.
- Rajkumar, N., Li, R., & Bahdanau, D. (2022). Evaluating the text-to-SQL capabilities of large language models. arXiv:2204.00498.
- Reisach, A. G., Seiler, C., & Weichwald, S. (2021). Beware of the simulated DAG! Causal discovery benchmarks may be easy to game. *NeurIPS 2021*.
- Ren, H., Xu, B., Wang, Y., Yi, C., Huang, C., Kou, X., Xing, T., Yang, M., Tong, J., & Zhang, Q. (2019). Time-series anomaly detection service at Microsoft. *KDD 2019*.
- Rousseeuw, P. J., & Croux, C. (1993). Alternatives to the median absolute deviation. *Journal of the American Statistical Association*, 88(424), 1273–1283.
- Runge, J., Nowack, P., Kretschmer, M., Flaxman, S., & Sejdinovic, D. (2019). Detecting and quantifying causal associations in large nonlinear time series datasets. *Science Advances*, 5(11).
- Schick, T., Dwivedi-Yu, J., Dessì, R., Raileanu, R., Lomeli, M., Zettlemoyer, L., Cancedda, N., & Scialom, T. (2023). Toolformer: Language models can teach themselves to use tools. *NeurIPS 2023*.
- Sharma, A., & Kiciman, E. (2020). DoWhy: An end-to-end library for causal inference. arXiv:2011.04216.
- Shi, W., Cao, J., Zhang, Q., Li, Y., & Xu, L. (2016). Edge computing: Vision and challenges. *IEEE Internet of Things Journal*, 3(5), 637–646.
- Shimizu, S., Hoyer, P. O., Hyvärinen, A., & Kerminen, A. (2006). A linear non-Gaussian acyclic model for causal discovery. *Journal of Machine Learning Research*, 7, 2003–2030.
- Soldani, J., & Brogi, A. (2022). Anomaly detection and failure root cause analysis in (micro)service-based cloud applications: A survey. *ACM Computing Surveys*, 55(3).
- Spirtes, P., Glymour, C., & Scheines, R. (2000). *Causation, Prediction, and Search* (2nd ed.). MIT Press.
- Taylor, S. J., & Letham, B. (2018). Forecasting at scale. *The American Statistician*, 72(1), 37–45.
- Wang, L., Ma, C., Feng, X., et al. (2024). A survey on large language model based autonomous agents. *Frontiers of Computer Science*, 18(6).
- Wang, P., Xu, J., Ma, M., Lin, W., Pan, D., Wang, Y., & Chen, P. (2018). CloudRanger: Root cause identification for cloud native systems. *IEEE/ACM CCGrid 2018*.
- Wiseman, S., Shieber, S. M., & Rush, A. M. (2017). Challenges in data-to-document generation. *EMNLP 2017*.
- Xu, J., Wu, H., Wang, J., & Long, M. (2022). Anomaly Transformer: Time series anomaly detection with association discrepancy. *ICLR 2022*. arXiv:2110.02642.
- Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing reasoning and acting in language models. *ICLR 2023*. arXiv:2210.03629.
- Yu, T., Zhang, R., Yang, K., et al. (2018). Spider: A large-scale human-labeled dataset for complex and cross-domain semantic parsing and text-to-SQL task. *EMNLP 2018*.
- Zheng, X., Aragam, B., Ravikumar, P., & Xing, E. P. (2018). DAGs with NO TEARS: Continuous optimization for structure learning. *NeurIPS 2018*.

Product documentation referenced (not peer-reviewed): dbt Semantic Layer / MetricFlow, Looker LookML,
Fivetran, Airbyte, Debezium, LangGraph. AIDA (arXiv 2605.07202) is cited in the project README; we have
not independently verified it.
