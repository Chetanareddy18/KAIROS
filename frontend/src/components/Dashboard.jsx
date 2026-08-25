import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'

const BASE = '/api/v1'

function StatCard({ label, value, sub, accent }) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border-l-4" style={{ borderColor: accent }}>
      <p className="text-xs uppercase tracking-widest text-gray-400">{label}</p>
      <p className="text-3xl font-bold mt-1" style={{ color: accent }}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
}

function SeverityBadge({ level }) {
  const colors = {
    critical: 'bg-red-100 text-red-700',
    high:     'bg-orange-100 text-orange-700',
    medium:   'bg-yellow-100 text-yellow-700',
    low:      'bg-green-100 text-green-700',
  }
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded-full uppercase ${colors[level] ?? 'bg-gray-100'}`}>
      {level}
    </span>
  )
}

export default function Dashboard() {
  const [anomalies, setAnomalies] = useState([])
  const [metrics,   setMetrics]   = useState([])
  const [series,    setSeries]    = useState([])
  const [selected,  setSelected]  = useState(null)
  const [running,   setRunning]   = useState(false)
  const [lastRun,   setLastRun]   = useState(null)

  useEffect(() => { load() }, [])

  async function load() {
    try {
      const [a, m] = await Promise.all([
        axios.get(`${BASE}/anomalies`),
        axios.get(`${BASE}/metrics`),
      ])
      setAnomalies(a.data.anomalies ?? [])
      setMetrics(m.data.metrics ?? [])
    } catch { /* API not running yet */ }
  }

  async function loadSeries(name) {
    setSelected(name)
    try {
      const { data } = await axios.get(`${BASE}/metrics/${encodeURIComponent(name)}/series`, { params: { hours: 72 } })
      setSeries(
        (data.points ?? []).map(p => ({
          time:  new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          value: p.value,
        }))
      )
    } catch { setSeries([]) }
  }

  async function runPipeline() {
    setRunning(true)
    try {
      await axios.post(`${BASE}/pipeline/run`)
      setLastRun(new Date().toLocaleTimeString())
      await load()
    } finally {
      setRunning(false)
    }
  }

  const critical = anomalies.filter(a => a.severity === 'critical').length
  const high     = anomalies.filter(a => a.severity === 'high').length

  return (
    <div className="space-y-6">
      {/* Stat row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Anomalies" value={anomalies.length} sub="this cycle"     accent="#1E7A78" />
        <StatCard label="Critical"        value={critical}          sub="need attention" accent="#C04040" />
        <StatCard label="High"            value={high}              sub="investigate"    accent="#D97706" />
        <StatCard label="Metrics Tracked" value={metrics.length}    sub="sources"        accent="#6B7280" />
      </div>

      {/* Run button */}
      <div className="flex items-center gap-4">
        <button
          onClick={runPipeline}
          disabled={running}
          className="bg-[#1E7A78] text-white px-5 py-2 rounded-lg font-semibold text-sm hover:bg-[#0D3D3C] disabled:opacity-50 transition-colors"
        >
          {running ? 'Running pipeline…' : 'Run Pipeline Now'}
        </button>
        {lastRun && <span className="text-xs text-gray-400">Last run: {lastRun}</span>}
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Anomaly table */}
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100 font-semibold text-sm">Live Anomalies</div>
          {anomalies.length === 0
            ? <p className="px-5 py-8 text-sm text-gray-400 text-center">No anomalies detected</p>
            : (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-xs text-gray-400 uppercase">
                  <tr>
                    <th className="px-4 py-2 text-left">Metric</th>
                    <th className="px-4 py-2 text-right">Observed</th>
                    <th className="px-4 py-2 text-right">Expected</th>
                    <th className="px-4 py-2 text-center">Severity</th>
                  </tr>
                </thead>
                <tbody>
                  {anomalies.slice(0, 8).map((a, i) => (
                    <tr key={i} className="border-t border-gray-50 hover:bg-gray-50 cursor-pointer"
                        onClick={() => loadSeries(a.metric_name)}>
                      <td className="px-4 py-2 font-medium">{a.metric_name}</td>
                      <td className="px-4 py-2 text-right">{a.observed_value?.toFixed(2)}</td>
                      <td className="px-4 py-2 text-right text-gray-400">{a.expected_value?.toFixed(2)}</td>
                      <td className="px-4 py-2 text-center"><SeverityBadge level={a.severity} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>

        {/* Series chart */}
        <div className="bg-white rounded-xl shadow-sm p-5">
          <div className="font-semibold text-sm mb-4">
            {selected ? `Metric: ${selected}` : 'Click a metric to see its time series'}
          </div>
          {series.length > 0
            ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={series}>
                  <CartesianGrid stroke="#f0f0f0" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="value" stroke="#1E7A78" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            )
            : (
              <div className="h-56 flex items-center justify-center text-sm text-gray-300">
                No data
              </div>
            )}
        </div>
      </div>

      {/* Metrics list */}
      <div className="bg-white rounded-xl shadow-sm p-5">
        <div className="font-semibold text-sm mb-3">All Tracked Metrics</div>
        <div className="flex flex-wrap gap-2">
          {metrics.map((m, i) => (
            <button key={i}
              onClick={() => loadSeries(m.metric_name)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors
                ${selected === m.metric_name
                  ? 'bg-[#1E7A78] text-white border-[#1E7A78]'
                  : 'border-gray-200 hover:border-[#1E7A78] hover:text-[#1E7A78]'}`}
            >
              {m.metric_name}
              <span className="ml-1 text-gray-400">{m.source}</span>
            </button>
          ))}
          {metrics.length === 0 && <p className="text-sm text-gray-400">No metrics yet — run the pipeline or register connectors</p>}
        </div>
      </div>
    </div>
  )
}
