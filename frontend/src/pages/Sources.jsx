import { useMemo, useState } from 'react'
import { API_BASE, api } from '../api'
import { useAction, useApi } from '../hooks'
import {
  DataTable, Empty, ErrorBanner, Modal, PageHeader, Spinner, fmtBytes, fmtNum, timeAgo,
} from '../components/ui'

const TYPE_STYLE = {
  sql: 'bg-indigo-50 text-indigo-700', file: 'bg-amber-50 text-amber-800', csv: 'bg-amber-50 text-amber-800',
  sftp: 'bg-sky-50 text-sky-700', rest: 'bg-violet-50 text-violet-700', sheets: 'bg-green-50 text-green-700',
  push: 'bg-gray-100 text-gray-700',
}

const STRATEGY = [
  { t: 'SQL push-down', d: 'The aggregation query runs inside the source DB — a 50 GB table sends a few KB of KPIs.' },
  { t: 'SFTP / FTP', d: 'Universal zero-cost batch route. Only new files are fetched; .gz/.zst/Parquet read directly.' },
  { t: 'Files & cloud', d: 'CSV/Excel/Parquet on disk, S3 or HTTPS. DuckDB streams and aggregates out-of-core.' },
  { t: 'REST APIs', d: 'One config-driven adapter for any JSON API — auth headers, paging, incremental since.' },
  { t: 'Push / edge', d: 'Webhooks and the edge agent POST to /ingest — no connector on our side at all.' },
]

const toForm = cfg => Object.fromEntries(Object.entries(cfg || {}).map(([k, v]) => [k, typeof v === 'object' ? JSON.stringify(v) : String(v)]))

function buildConfig(form, fields) {
  const spec = Object.fromEntries(fields.map(f => [f.name, f]))
  const out = {}
  for (const [k, raw] of Object.entries(form)) {
    if (raw === '' || raw === undefined || raw === null) continue
    const f = spec[k]
    if (f?.type === 'number') out[k] = Number(raw)
    else if (f?.type === 'json' || (typeof raw === 'string' && /^[[{]/.test(raw.trim()))) {
      try { out[k] = JSON.parse(raw) } catch { throw new Error(`"${f?.label ?? k}" is not valid JSON`) }
    } else out[k] = raw
  }
  return out
}

function Field({ f, value, onChange }) {
  const common = { className: 'input', value: value ?? '', onChange: e => onChange(e.target.value), placeholder: f.default ?? '' }
  return (
    <div className={f.type === 'textarea' || f.type === 'json' ? 'sm:col-span-2' : ''}>
      <label className="label">{f.label}{f.required && <span className="text-red-500"> *</span>}</label>
      {f.type === 'select'
        ? <select {...common}>{(f.options ?? []).map(o => <option key={o} value={o}>{o || '(auto)'}</option>)}</select>
        : f.type === 'textarea' || f.type === 'json'
          ? <textarea {...common} rows={f.type === 'json' ? 2 : 4} className="input font-mono text-xs" />
          : <input {...common} type={f.type === 'password' ? 'password' : f.type === 'number' ? 'number' : 'text'} />}
      {f.help && <p className="text-[11px] text-gray-400 mt-1">{f.help}</p>}
    </div>
  )
}

function TestResult({ result, onApply }) {
  if (!result) return null
  return (
    <div className="space-y-3">
      <div className={`rounded-lg px-4 py-2.5 text-sm ${result.ok ? (result.mapping_ok === false ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-800') : 'bg-red-50 text-red-700'}`}>
        {result.ok ? '✓ ' : '✕ '}{result.message}
        {result.metrics?.length > 0 && <div className="text-xs mt-1">Metrics found: {result.metrics.slice(0, 12).join(', ')}{result.metrics.length > 12 ? '…' : ''}</div>}
      </div>
      {result.sample?.length > 0 && <DataTable rows={result.sample} />}
      {result.slac?.mapping && Object.keys(result.slac.mapping).length > 0 && (
        <div className="rounded-lg border border-teal/30 bg-teal-light/50 p-3 text-sm">
          <div className="flex items-center justify-between gap-3">
            <div><b className="text-teal-dark">SLAC suggested mapping</b> <span className="text-xs text-gray-500">(Semantic Layer Auto-Construction)</span></div>
            {onApply && <button className="btn-primary btn-sm" onClick={() => onApply(result.slac.mapping)}>Apply</button>}
          </div>
          <pre className="text-xs mt-2 whitespace-pre-wrap text-gray-700">{JSON.stringify(result.slac.mapping, null, 1)}</pre>
          {result.slac.notes?.map((n, i) => <div key={i} className="text-xs text-gray-500">• {n}</div>)}
        </div>
      )}
    </div>
  )
}

function SourceForm({ types, initial, onClose, onSaved }) {
  const editing = !!initial
  const [name, setName] = useState(initial?.name ?? '')
  const [type, setType] = useState(initial?.type ?? 'file')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [enabled, setEnabled] = useState(initial?.enabled ?? true)
  const [form, setForm] = useState(toForm(initial?.config))
  const [showMap, setShowMap] = useState(editing)
  const [result, setResult] = useState(null)
  const test = useAction()
  const save = useAction()
  const spec = types.find(t => t.type === type) ?? types[0]
  const allFields = useMemo(() => [...(spec?.fields ?? []), ...(spec?.mapping_fields ?? [])], [spec])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function runTest() {
    setResult(null)
    const r = await test.run(async () => (await api.post('/sources/test', { type, config: buildConfig(form, allFields) })).data)
    if (r) setResult(r)
  }
  async function submit() {
    const ok = await save.run(async () => {
      const body = { name, type, description, enabled, config: buildConfig(form, allFields) }
      return editing ? (await api.put(`/sources/${name}`, body)).data : (await api.post('/sources', body)).data
    })
    if (ok) onSaved()
  }
  function applyMapping(m) {
    setShowMap(true)
    setForm(f => ({ ...f, ...toForm(m) }))
  }

  return (
    <div className="space-y-5">
      <div className="grid sm:grid-cols-2 gap-4">
        <div>
          <label className="label">Name *</label>
          <input className="input" value={name} disabled={editing} onChange={e => setName(e.target.value.replace(/[^A-Za-z0-9_.-]/g, '_'))} placeholder="erp_orders" />
        </div>
        <div>
          <label className="label">Connector type *</label>
          <select className="input" value={type} disabled={editing} onChange={e => { setType(e.target.value); setResult(null) }}>
            {types.map(t => <option key={t.type} value={t.type}>{t.label}</option>)}
          </select>
        </div>
        <div className="sm:col-span-2 text-xs text-gray-500 -mt-2">{spec?.description}</div>
        {(spec?.fields ?? []).map(f => <Field key={f.name} f={f} value={form[f.name]} onChange={v => set(f.name, v)} />)}
        <div className="sm:col-span-2">
          <label className="label">Description</label>
          <input className="input" value={description} onChange={e => setDescription(e.target.value)} placeholder="what this source is" />
        </div>
      </div>

      {spec?.mapping_fields?.length > 0 && (
        <div className="border border-gray-100 rounded-lg">
          <button className="w-full px-4 py-2.5 text-left text-sm font-semibold flex justify-between" onClick={() => setShowMap(s => !s)}>
            <span>Mapping <span className="font-normal text-gray-400">— leave blank and use “Test” to let SLAC infer it</span></span>
            <span>{showMap ? '−' : '+'}</span>
          </button>
          {showMap && (
            <div className="grid sm:grid-cols-2 gap-4 p-4 pt-0">
              {spec.mapping_fields.map(f => <Field key={f.name} f={f} value={form[f.name]} onChange={v => set(f.name, v)} />)}
            </div>
          )}
        </div>
      )}

      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> Enabled (polled every pipeline run)</label>

      <ErrorBanner error={test.error || save.error} />
      <TestResult result={result} onApply={applyMapping} />

      <div className="flex justify-end gap-2 pt-2 border-t border-gray-100">
        <button className="btn-ghost" onClick={onClose}>Cancel</button>
        {type !== 'push' && <button className="btn-ghost" onClick={runTest} disabled={test.busy}>{test.busy ? <Spinner /> : 'Test & preview'}</button>}
        <button className="btn-primary" onClick={submit} disabled={save.busy || !name}>{save.busy ? <Spinner /> : editing ? 'Save changes' : 'Add source'}</button>
      </div>
    </div>
  )
}

export default function Sources() {
  const sources = useApi('/sources', { interval: 15_000 })
  const types = useApi('/connectors')
  const [modal, setModal] = useState(null)       // null | {mode:'new'} | {mode:'edit', src} | {mode:'test', name, result}
  const [busy, setBusy] = useState({})
  const action = useAction()
  const list = sources.data?.sources ?? []

  async function act(name, kind) {
    setBusy(b => ({ ...b, [name]: kind }))
    const r = await action.run(async () => {
      if (kind === 'sync') return (await api.post(`/sources/${name}/sync`)).data
      if (kind === 'test') return (await api.post(`/sources/${name}/test`)).data
      if (kind === 'delete') return (await api.delete(`/sources/${name}`, { params: { purge: true } })).data
      return null
    })
    setBusy(b => ({ ...b, [name]: null }))
    if (kind === 'test' && r) setModal({ mode: 'test', name, result: r })
    sources.reload()
  }
  async function editSource(name) {
    const src = await action.run(async () => (await api.get(`/sources/${name}`)).data)
    if (src) setModal({ mode: 'edit', src })
  }
  async function syncAll() {
    await action.run(async () => (await api.post('/sources/sync-all')).data)
    sources.reload()
  }

  const ingestUrl = `${API_BASE.startsWith('http') ? API_BASE : location.origin + API_BASE}/ingest`

  return (
    <div className="space-y-6">
      <PageHeader title="Data Sources" subtitle="Five lightweight protocol adapters cover almost every company system — no per-product connectors, no paid ELT platform.">
        <button className="btn-ghost" onClick={syncAll} disabled={action.busy}>Sync all</button>
        <button className="btn-primary" onClick={() => setModal({ mode: 'new' })}>+ Add source</button>
      </PageHeader>

      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {STRATEGY.map(s => (
          <div key={s.t} className="card p-4">
            <div className="font-semibold text-sm text-teal-dark">{s.t}</div>
            <div className="text-xs text-gray-500 mt-1 leading-relaxed">{s.d}</div>
          </div>
        ))}
      </div>

      <ErrorBanner error={action.error || sources.error} onClose={() => action.setError('')} />

      <div className="card overflow-hidden">
        <div className="card-h"><span className="font-semibold text-sm">Registered sources ({list.length})</span>
          <span className="text-xs text-gray-400">incremental: each sync moves only data newer than the stored watermark</span></div>
        {list.length === 0 ? <Empty>{sources.loading ? 'Loading…' : 'No sources yet — add one, upload a file, or push data to /ingest.'}</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50"><tr>
                <th className="th">Source</th><th className="th">Type</th><th className="th">Status</th><th className="th">Last sync</th>
                <th className="th text-right">Rows (last)</th><th className="th text-right">Transferred</th><th className="th text-right">Time</th>
                <th className="th text-right">Total rows</th><th className="th text-right">Actions</th></tr></thead>
              <tbody>
                {list.map(s => (
                  <tr key={s.name} className="border-t border-gray-50 align-top">
                    <td className="td">
                      <div className="font-medium">{s.name}</div>
                      <div className="text-[11px] text-gray-400">{s.description || s.managed_by}{!s.enabled && ' · disabled'}</div>
                    </td>
                    <td className="td"><span className={`chip ${TYPE_STYLE[s.type] ?? 'bg-gray-100'}`}>{s.type}{s.config?.protocol ? ` · ${s.config.protocol}` : ''}</span></td>
                    <td className="td">
                      {s.last_status === 'ok' && <span className="chip bg-emerald-50 text-emerald-700">● ok</span>}
                      {s.last_status === 'error' && <span className="chip bg-red-50 text-red-700 cursor-help" title={s.last_error}>● error</span>}
                      {s.last_status === 'never' && <span className="chip bg-gray-100 text-gray-500">never synced</span>}
                      {s.last_status === 'error' && <div className="text-[11px] text-red-500 mt-1 max-w-[220px] truncate" title={s.last_error}>{s.last_error}</div>}
                    </td>
                    <td className="td text-xs text-gray-500">{timeAgo(s.last_sync)}</td>
                    <td className="td text-right tabular-nums">{fmtNum(s.last_rows, 0)}</td>
                    <td className="td text-right tabular-nums text-gray-500">{s.last_bytes ? fmtBytes(s.last_bytes) : '—'}</td>
                    <td className="td text-right tabular-nums text-gray-500">{s.last_duration_ms ? `${(s.last_duration_ms / 1000).toFixed(2)}s` : '—'}</td>
                    <td className="td text-right tabular-nums">{fmtNum(s.total_rows, 0)}</td>
                    <td className="td text-right whitespace-nowrap">
                      {s.type !== 'push' && <>
                        <button className="btn-ghost btn-sm mr-1" onClick={() => act(s.name, 'test')} disabled={!!busy[s.name]}>{busy[s.name] === 'test' ? <Spinner className="w-3 h-3" /> : 'Test'}</button>
                        <button className="btn-ghost btn-sm mr-1" onClick={() => act(s.name, 'sync')} disabled={!!busy[s.name]}>{busy[s.name] === 'sync' ? <Spinner className="w-3 h-3" /> : 'Sync'}</button>
                      </>}
                      <button className="btn-ghost btn-sm mr-1" onClick={() => editSource(s.name)}>Edit</button>
                      <button className="btn-danger btn-sm" onClick={() => confirm(`Delete source "${s.name}" and its data?`) && act(s.name, 'delete')}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-5">
          <div className="font-semibold text-sm mb-2">Push data (webhooks, in-house apps)</div>
          <p className="text-xs text-gray-500 mb-3">Any system that can send an HTTP POST can feed KAIROS directly — the source is created on first push.</p>
          <pre className="text-[11px] bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto">{`curl -X POST ${ingestUrl} \\
  -H "Content-Type: application/json" -H "X-API-Key: $KAIROS_API_KEY" \\
  -d '{"source":"pos_store_7","records":[
        {"metric_name":"sales","value":1840.5,"timestamp":"2026-10-06T10:00:00Z"}]}'`}</pre>
        </div>
        <div className="card p-5">
          <div className="font-semibold text-sm mb-2">Large raw data? Run the edge agent next to it</div>
          <p className="text-xs text-gray-500 mb-3">“Move the computation, not the data”: the agent aggregates a multi-GB export locally and sends only KPIs.</p>
          <pre className="text-[11px] bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto">{`python edge_agent/kairos_edge.py aggregate \\
  --input orders_2026.csv.gz --ts-col created_at \\
  --metric amount:revenue:sum --count-metric orders \\
  --freq 1h --source store_42 --server ${location.origin.replace(':5173', ':8000')}`}</pre>
        </div>
      </div>

      <Modal open={modal?.mode === 'new' || modal?.mode === 'edit'} onClose={() => setModal(null)} wide
        title={modal?.mode === 'edit' ? `Edit source · ${modal.src.name}` : 'Add a data source'}>
        {types.data && <SourceForm types={types.data.types} initial={modal?.src} onClose={() => setModal(null)} onSaved={() => { setModal(null); sources.reload() }} />}
      </Modal>
      <Modal open={modal?.mode === 'test'} onClose={() => setModal(null)} wide title={`Connection test · ${modal?.name}`}>
        <TestResult result={modal?.result} />
      </Modal>
    </div>
  )
}
