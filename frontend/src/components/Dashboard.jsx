import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid, ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from '../api'
import { useAction, useApi } from '../hooks'
import {
  Empty, ErrorBanner, SEV_STYLE, SeverityBadge, Spinner, StatCard, fmtNum, fmtTime, timeAgo,
} from './ui'

const SEVERITIES = ['all', 'critical', 'high', 'medium', 'low']

function SeriesChart({ metric, source }) {
  const { data, loading } = useApi(metric ? `/metrics/${encodeURIComponent(metric)}/series` : null,
    { params: { hours: 168, source }, enabled: !!metric })
  const points = useMemo(() => (data?.points ?? []).map(p => ({
    t: new Date(p.timestamp).getTime(), value: p.value,
    anomaly: p.anomaly ? p.value : null, severity: p.anomaly, expected: p.expected,
  })), [data])

  if (!metric) return <Empty className="h-64 flex items-center justify-center">Click an anomaly or a metric to see its time series</Empty>
  if (loading) return <div className="h-64 flex items-center justify-center text-gray-400"><Spinner /></div>
  if (!points.length) return <Empty className="h-64">No data</Empty>

  const Dot = ({ cx, cy, payload }) => payload.severity
    ? <circle cx={cx} cy={cy} r={5} fill={SEV_STYLE[payload.severity]?.dot} stroke="white" strokeWidth={1.5} />
    : null

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="#f2f2f2" />
        <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tick={{ fontSize: 10 }}
          tickFormatter={t => new Date(t).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit' })} minTickGap={40} />
        <YAxis tick={{ fontSize: 10 }} width={56} tickFormatter={v => fmtNum(v, 1)} domain={['auto', 'auto']} />
        <Tooltip labelFormatter={t => new Date(t).toLocaleString()}
          formatter={(v, name, item) => name === 'anomaly'
            ? [`${fmtNum(v)} (${item.payload.severity}, expected ${fmtNum(item.payload.expected)})`, 'anomaly']
            : [fmtNum(v), name]} />
        <Line type="monotone" dataKey="value" stroke="#1E7A78" dot={false} strokeWidth={1.8} isAnimationActive={false} />
        <Scatter dataKey="anomaly" shape={<Dot />} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export default function Dashboard({ status }) {
  const [severity, setSeverity] = useState('all')
  const [source, setSource] = useState('')
  const [limit, setLimit] = useState(25)
  const [selected, setSelected] = useState(null)
  const [lastRun, setLastRun] = useState(null)
  const anomalies = useApi('/anomalies', { params: { severity, source: source || undefined, limit: 1000 }, interval: 30_000 })
  const metrics = useApi('/metrics', { interval: 30_000 })
  const runs = useApi('/pipeline/runs', { params: { limit: 8 }, interval: 30_000 })
  const action = useAction()

  const list = anomalies.data?.anomalies ?? []
  const counts = anomalies.data?.counts ?? {}
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const bySource = useMemo(() => {
    const g = {}
    for (const m of metrics.data?.metrics ?? []) (g[m.source] ??= []).push(m)
    return g
  }, [metrics.data])

  useEffect(() => {
    if (!selected && list.length) setSelected({ metric: list[0].metric_name, source: list[0].source })
  }, [list, selected])

  const refresh = () => { anomalies.reload(); metrics.reload(); runs.reload() }

  async function runPipeline() {
    const r = await action.run(async () => (await api.post('/pipeline/run')).data)
    if (r) { setLastRun(r); refresh() }
  }
  async function seed() {
    const r = await action.run(async () => (await api.post('/dev/seed')).data)
    if (r) {
      const p = await action.run(async () => (await api.post('/pipeline/run')).data)
      if (p) setLastRun(p)
      setSelected(null); refresh()
    }
  }

  const empty = status && status.data.points === 0

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={runPipeline} disabled={action.busy} className="btn-primary">
          {action.busy ? <><Spinner /> Running agents…</> : '▶ Run pipeline now'}
        </button>
        {status && status.env !== 'production' && (
          <button onClick={seed} disabled={action.busy} className="btn-ghost" title="Load 2 weeks of synthetic data from 4 sources with known causal structure">
            Load demo data
          </button>
        )}
        <span className="text-xs text-gray-400">
          Collect → Detect → Investigate → Report → Alert{status?.last_run ? ` · last run ${timeAgo(status.last_run.finished_at)}` : ''}
        </span>
      </div>

      <ErrorBanner error={action.error || anomalies.error} onClose={() => action.setError('')} />

      {lastRun && lastRun.status !== 'skipped' && (
        <div className="card px-5 py-3 text-sm flex flex-wrap gap-x-6 gap-y-1 items-center border-l-4 border-l-teal">
          <b className="text-teal">Pipeline finished</b>
          <span>{fmtNum(lastRun.metrics_collected, 0)} rows collected</span>
          <span>{lastRun.anomalies_found} anomalies scanned · <b>{lastRun.new_anomalies} new</b></span>
          <span>{lastRun.alertable} alert-worthy</span>
          <span>{lastRun.alert_sent ? '✓ alert delivered' : lastRun.alertable ? 'alert stored (no channel configured)' : 'no alert needed'}</span>
          {lastRun.origins?.length > 0 && <span>origin: <b>{lastRun.origins.join(', ')}</b></span>}
          {lastRun.errors?.length > 0 && <span className="text-red-600">{lastRun.errors.length} source error(s)</span>}
        </div>
      )}

      {empty && (
        <div className="card p-6 text-sm text-gray-600">
          <b>No data yet.</b> Connect a source on <Link className="text-teal underline" to="/sources">Data Sources</Link>, upload a file
          on <Link className="text-teal underline" to="/transfer">Fast Transfer</Link>, push from the edge agent — or click <b>Load demo data</b>.
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard label="Metrics monitored" value={status?.data.series ?? '—'} sub={`${fmtNum(status?.data.points ?? 0, 0)} data points`} accent="#1E7A78" />
        <StatCard label="Critical" value={counts.critical ?? 0} sub="act now" accent="#C04040" />
        <StatCard label="High" value={counts.high ?? 0} sub="investigate today" accent="#D97706" />
        <StatCard label="Medium / Low" value={`${counts.medium ?? 0} / ${counts.low ?? 0}`} sub="watch" accent="#CA8A04" />
        <StatCard label="Sources" value={status?.data.sources_registered ?? '—'} sub={status?.data.last_ingest ? `last ingest ${timeAgo(status.data.last_ingest)}` : 'no ingest yet'} accent="#6B7280" />
      </div>

      <div className="grid xl:grid-cols-5 gap-6">
        <div className="card xl:col-span-3 overflow-hidden">
          <div className="card-h flex-wrap">
            <span className="font-semibold text-sm">Detected anomalies <span className="text-gray-400 font-normal">({total})</span></span>
            <div className="flex flex-wrap gap-1 items-center">
              {SEVERITIES.map(s => (
                <button key={s} onClick={() => { setSeverity(s); setLimit(25) }}
                  className={`px-2.5 py-1 rounded-full text-xs font-semibold capitalize transition-colors ${severity === s
                    ? (s === 'all' ? 'bg-teal text-white' : SEV_STYLE[s].chip) : 'bg-gray-100 text-gray-500 hover:bg-gray-200'}`}>
                  {s === 'all' ? `All` : `${s} ${counts[s] ?? 0}`}
                </button>
              ))}
              <select value={source} onChange={e => setSource(e.target.value)} className="ml-1 text-xs border border-gray-200 rounded-md px-2 py-1 bg-white">
                <option value="">all sources</option>
                {Object.keys(bySource).map(s => <option key={s}>{s}</option>)}
              </select>
            </div>
          </div>
          {list.length === 0
            ? <Empty>{anomalies.loading ? 'Loading…' : 'No anomalies detected'}</Empty>
            : (
              <div className="max-h-[420px] overflow-auto scroll-thin">
                <table className="w-full">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr><th className="th">When</th><th className="th">Metric</th><th className="th">Source</th>
                      <th className="th text-right">Observed</th><th className="th text-right">Expected</th>
                      <th className="th text-right">σ</th><th className="th text-center">Severity</th></tr>
                  </thead>
                  <tbody>
                    {list.slice(0, limit).map(a => (
                      <tr key={a.id} onClick={() => setSelected({ metric: a.metric_name, source: a.source })}
                        className={`border-t border-gray-50 cursor-pointer hover:bg-teal-light/50 ${selected?.metric === a.metric_name && selected?.source === a.source ? 'bg-teal-light/60' : ''}`}>
                        <td className="td text-xs text-gray-500 whitespace-nowrap">{fmtTime(a.timestamp)}</td>
                        <td className="td font-medium">{a.metric_name}</td>
                        <td className="td text-xs text-gray-400">{a.source}</td>
                        <td className="td text-right tabular-nums">{fmtNum(a.observed_value)}</td>
                        <td className="td text-right tabular-nums text-gray-400">{fmtNum(a.expected_value)}</td>
                        <td className="td text-right tabular-nums text-gray-500">{a.deviation_score > 0 ? '+' : ''}{a.deviation_score?.toFixed(1)}</td>
                        <td className="td text-center"><SeverityBadge level={a.severity} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {list.length > limit && (
                  <button onClick={() => setLimit(l => l + 50)} className="w-full py-2 text-xs text-teal hover:bg-gray-50">Show more ({list.length - limit})</button>
                )}
              </div>
            )}
        </div>

        <div className="card xl:col-span-2">
          <div className="card-h">
            <span className="font-semibold text-sm truncate">{selected ? selected.metric : 'Time series'}</span>
            {selected && <span className="text-xs text-gray-400">{selected.source} · last 7 days</span>}
          </div>
          <div className="p-4"><SeriesChart metric={selected?.metric} source={selected?.source} /></div>
          <div className="px-5 pb-4 flex flex-wrap gap-3 text-[11px] text-gray-500">
            {['critical', 'high', 'medium', 'low'].map(s => (
              <span key={s} className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: SEV_STYLE[s].dot }} />{s}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="card">
          <div className="card-h"><span className="font-semibold text-sm">Metrics by source</span></div>
          <div className="p-5 space-y-4 max-h-96 overflow-auto scroll-thin">
            {Object.keys(bySource).length === 0 && <Empty>No metrics yet</Empty>}
            {Object.entries(bySource).map(([src, ms]) => (
              <div key={src}>
                <div className="text-xs font-semibold text-gray-500 mb-2">{src} <span className="font-normal text-gray-400">· {ms.length} metrics</span></div>
                <div className="flex flex-wrap gap-2">
                  {ms.map(m => (
                    <button key={m.metric_name} onClick={() => setSelected({ metric: m.metric_name, source: m.source })}
                      className={`px-3 py-1 rounded-full text-xs border transition-colors ${selected?.metric === m.metric_name && selected?.source === src
                        ? 'bg-teal text-white border-teal' : 'border-gray-200 hover:border-teal hover:text-teal'}`}>
                      {m.metric_name} <span className="opacity-60 tabular-nums">{fmtNum(m.latest_value)}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card overflow-hidden">
          <div className="card-h"><span className="font-semibold text-sm">Recent pipeline runs</span></div>
          {(runs.data?.runs ?? []).length === 0 ? <Empty>No runs yet</Empty> : (
            <table className="w-full">
              <thead className="bg-gray-50"><tr><th className="th">Started</th><th className="th">Trigger</th><th className="th text-right">Rows</th>
                <th className="th text-right">New anomalies</th><th className="th text-center">Alert</th><th className="th text-right">Duration</th></tr></thead>
              <tbody>
                {runs.data.runs.map(r => (
                  <tr key={r.id} className="border-t border-gray-50">
                    <td className="td text-xs text-gray-500">{fmtTime(r.started_at)}</td>
                    <td className="td text-xs">{r.trigger}</td>
                    <td className="td text-right tabular-nums">{fmtNum(r.metrics_collected, 0)}</td>
                    <td className="td text-right tabular-nums">{r.new_anomalies}</td>
                    <td className="td text-center">{r.alert_sent ? '✓' : '—'}</td>
                    <td className="td text-right text-xs text-gray-500">{r.duration_s != null ? `${r.duration_s}s` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}
