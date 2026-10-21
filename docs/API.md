# KAIROS API reference

Base URL: `/api/v1`. Interactive OpenAPI docs are at `/docs`.

When `KAIROS_API_KEY` is set, every `/api/v1` call needs the header `X-API-Key: <key>`.
`/health` is always open.

## Status & pipeline
| Method | Path | Description |
|---|---|---|
| GET | `/status` | Scheduler (next run), last run, data overview, severity counts, LLM/channel/capability flags |
| POST | `/pipeline/run` | Run collect → detect → investigate → report → alert now. Returns a run summary, root causes and the report |
| GET | `/pipeline/runs?limit=20` | Run history |

## Metrics & anomalies
| Method | Path | Description |
|---|---|---|
| GET | `/metrics` | Every series: source, points, first/last timestamp, latest value |
| GET | `/metrics/{metric}/series?hours=168&source=` | Points (measured back from the series' newest point), with anomaly flags |
| GET | `/anomalies?severity=&source=&metric=&limit=` | Stored anomalies plus severity counts |
| POST | `/anomalies/detect` | Run detection only. Returns `{found, new}` |

## Causal analysis, reports, alerts
| Method | Path | Description |
|---|---|---|
| POST | `/investigate?hours=24` | DYNOTEARS on recent anomalies → `{summary, method, origins, root_causes[], cbmg{nodes, edges}}` |
| GET | `/investigation/latest` | Last investigation (runs one if none) |
| POST | `/report?hours=24` | NL report → `{report, verified, engine, attempts, issues[]}` |
| GET | `/report/latest` | Last report |
| GET | `/semantics?use_llm=false` | SLAC business semantics for every metric |
| GET | `/alerts/history` | Delivered/stored alerts plus configured channels |
| POST | `/alerts/test` | Send a test alert |

## Sources
| Method | Path | Description |
|---|---|---|
| GET | `/connectors` | Connector types with form-field specs |
| GET / POST | `/sources` | List / create `{name, type, config, enabled, description}` |
| POST | `/sources/test` | Test an unsaved config. Returns sample rows plus SLAC mapping suggestion |
| GET / PUT / DELETE | `/sources/{name}` | Read (secrets masked) / update / delete (`?purge=true` also removes data) |
| POST | `/sources/{name}/test` | Test a saved source |
| POST | `/sources/{name}/sync?full_refresh=false` | Incremental sync now |
| POST | `/sources/sync-all` | Sync every enabled pull source in parallel |

## Ingest
| Method | Path | Description |
|---|---|---|
| POST | `/ingest` | Push `{source, records: [{metric_name, value, timestamp}], mapping?}`. The source is auto-created |
| POST | `/files` | Multipart upload (streamed to disk). Returns `{file_id, suggestion}` |
| GET | `/files/{file_id}/suggest` | SLAC mapping for a stored file |
| POST | `/files/{file_id}/ingest` | `{source, mapping?}`. Reads, aggregates if needed, and stores |

## Fast Transfer
| Method | Path | Description |
|---|---|---|
| POST | `/transfer/start` | `{filename, size_bytes, chunk_size, sha256?, compression: none, gzip or zstd}` → transfer with `missing[]`. The same file plus hash resumes the existing transfer |
| PUT | `/transfer/{id}/chunk/{n}` | Raw (optionally compressed) chunk body, header `X-Chunk-SHA256` of the uncompressed chunk |
| GET | `/transfer/{id}` | Progress and the list of missing chunks (for resume) |
| POST | `/transfer/{id}/complete` | `{ingest, source?, mapping?}`. Verifies the whole-file SHA-256, then optionally ingests |
| GET | `/transfers` | Recent transfers |
| DELETE | `/transfer/{id}` | Abort |

## Development only (disabled when `KAIROS_ENV=production`)
`POST /dev/seed`, `POST /dev/reset`, `GET /dev/ground-truth`
