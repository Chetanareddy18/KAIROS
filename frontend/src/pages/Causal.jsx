import { useMemo, useState } from 'react'
import { api } from '../api'
import CausalGraph from '../components/CausalGraph'
import { useAction, useApi } from '../hooks'
import { Empty, ErrorBanner, PageHeader, Spinner } from '../components/ui'

function GroundTruth({ edges }) {
  const truth = useApi('/dev/ground-truth')
  if (!truth.data?.edges || !edges?.length) return null
  const T = new Set(truth.data.edges.map(e => `${e.from}→${e.to}`))
  const F = new Set(edges.map(e => `${e.from}→${e.to}`))
  if (![...F].some(k => T.has(k))) return null           // not the demo dataset
  const tp = [...F].filter(k => T.has(k)).length
  const precision = tp / F.size, recall = tp / T.size
  const f1 = precision + recall ? (2 * precision * recall) / (precision + recall) : 0
  const missed = [...T].filter(k => !F.has(k))
  return (
    <div className="card p-5 text-sm">
      <div className="font-semibold mb-2">Evaluation against the demo ground truth</div>
      <div className="flex flex-wrap gap-6">
        <div><div className="text-2xl font-bold text-teal">{(precision * 100).toFixed(0)}%</div><div className="text-xs text-gray-400">precision</div></div>
        <div><div className="text-2xl font-bold text-teal">{(recall * 100).toFixed(0)}%</div><div className="text-xs text-gray-400">recall</div></div>
        <div><div className="text-2xl font-bold text-teal">{f1.toFixed(2)}</div><div className="text-xs text-gray-400">F1</div></div>
        <div className="text-xs text-gray-500 max-w-md">
          {tp} of {T.size} true causal edges recovered, {F.size - tp} spurious.
          {missed.length > 0 && <> Missed: {missed.join(', ')}.</>}
        </div>
      </div>
    </div>
  )
}

export default function Causal() {
  const latest = useApi('/investigation/latest')
  const [hl, setHl] = useState([])
  const action = useAction()
  const inv = latest.data

  async function investigate() {
    const r = await action.run(async () => (await api.post('/investigate', null, { params: { hours: 24 } })).data)
    if (r) latest.setData(r)
  }

  const anomalousCount = useMemo(() => (inv?.cbmg?.nodes ?? []).filter(n => n.anomalous).length, [inv])

  return (
    <div className="space-y-6">
      <PageHeader title="Causal Analysis"
        subtitle="DYNOTEARS learns a directed, lagged causal graph of your metrics (the CBMG); KAIROS walks it backwards from each anomaly to its origin.">
        <button className="btn-primary" onClick={investigate} disabled={action.busy}>
          {action.busy ? <><Spinner /> Discovering causal structure…</> : 'Run causal investigation'}
        </button>
      </PageHeader>
      <ErrorBanner error={action.error || latest.error} />

      {latest.loading && !inv && <div className="card p-10 flex justify-center text-gray-400"><Spinner className="w-6 h-6" /></div>}

      {inv && (
        <>
          <div className="card p-5">
            <div className="flex flex-wrap gap-2 mb-3">
              <span className="chip bg-teal-light text-teal font-semibold">method: {inv.method}</span>
              {inv.stats?.variables && <span className="chip bg-gray-100 text-gray-600">{inv.stats.variables} metrics × {inv.stats.samples} time steps</span>}
              {inv.stats?.step_hours && <span className="chip bg-gray-100 text-gray-600">step {inv.stats.step_hours}h · lags {inv.stats.lags}</span>}
              <span className="chip bg-gray-100 text-gray-600">{inv.cbmg?.edges?.length ?? 0} causal edges</span>
              <span className="chip bg-red-50 text-red-700">{anomalousCount} anomalous metrics</span>
            </div>
            <p className="text-sm text-gray-700 leading-relaxed">{inv.summary}</p>
            {inv.origins?.length > 0 && (
              <p className="text-sm mt-2">Most likely origin: {inv.origins.map(o => <b key={o} className="text-teal-dark mr-2">★ {o}</b>)}</p>
            )}
          </div>

          <div className="card">
            <div className="card-h">
              <span className="font-semibold text-sm">Causal Business Metric Graph (CBMG)</span>
              <span className="text-[11px] text-gray-400 flex gap-3">
                <span><b className="text-teal">—</b> positive effect</span>
                <span><b className="text-red-600">—</b> negative effect</span>
                <span>thickness = strength · lag 1 step unless shown</span>
                <span>★ origin · filled = anomalous</span>
              </span>
            </div>
            <div className="p-4">
              {inv.cbmg?.nodes?.length
                ? <CausalGraph graph={inv.cbmg} highlight={hl} origins={inv.origins ?? []} />
                : <Empty>No graph — not enough overlapping history yet.</Empty>}
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="card-h">
              <span className="font-semibold text-sm">Root-cause chains</span>
              <span className="text-xs text-gray-400">hover a row to highlight it in the graph</span>
            </div>
            {(inv.root_causes ?? []).length === 0 ? <Empty>No upstream causes found — anomalies look independent.</Empty> : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50"><tr>
                    <th className="th">Causal chain</th><th className="th text-right">Strength</th><th className="th text-right">Confidence</th>
                    <th className="th text-right">Lag</th><th className="th text-center">Evidence</th><th className="th text-right">DoWhy effect</th></tr></thead>
                  <tbody>
                    {inv.root_causes.map((rc, i) => (
                      <tr key={i} className="border-t border-gray-50 hover:bg-teal-light/50" onMouseEnter={() => setHl(rc.path)} onMouseLeave={() => setHl([])}>
                        <td className="td">
                          <div className="flex flex-wrap items-center gap-1">
                            {rc.path.map((m, j) => (
                              <span key={j} className="flex items-center gap-1">
                                <span className={`chip ${j === 0 ? 'bg-teal text-white' : j === rc.path.length - 1 ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-700'}`}>{m}</span>
                                {j < rc.path.length - 1 && <span className="text-gray-400">→</span>}
                              </span>
                            ))}
                            {rc.is_origin && <span className="chip bg-teal-dark text-white text-[10px]">ORIGIN</span>}
                          </div>
                          <div className="text-[11px] text-gray-400 mt-1">{rc.explanation}</div>
                        </td>
                        <td className="td text-right tabular-nums">{rc.causal_strength.toFixed(2)}</td>
                        <td className="td text-right tabular-nums">{(rc.confidence * 100).toFixed(0)}%</td>
                        <td className="td text-right tabular-nums">{rc.lag_hours}h</td>
                        <td className="td text-center">{rc.cause_anomalous ? <span title="cause was anomalous just before the effect" className="text-teal font-bold">✓</span> : '—'}</td>
                        <td className="td text-right tabular-nums text-gray-500">{rc.effect_estimate != null ? rc.effect_estimate.toFixed(2) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <GroundTruth edges={inv.cbmg?.edges} />
        </>
      )}
    </div>
  )
}
