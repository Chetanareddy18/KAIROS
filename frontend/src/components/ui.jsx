export const SEV_STYLE = {
  critical: { chip: 'bg-red-100 text-red-700', dot: '#C04040' },
  high:     { chip: 'bg-orange-100 text-orange-700', dot: '#D97706' },
  medium:   { chip: 'bg-yellow-100 text-yellow-800', dot: '#CA8A04' },
  low:      { chip: 'bg-green-100 text-green-700', dot: '#16A34A' },
}

export function SeverityBadge({ level }) {
  if (!level) return null
  return (
    <span className={`chip uppercase font-bold tracking-wide text-[10px] ${SEV_STYLE[level]?.chip ?? 'bg-gray-100 text-gray-600'}`}>
      {level}
    </span>
  )
}

export function StatCard({ label, value, sub, accent = '#1E7A78', icon }) {
  return (
    <div className="card p-5 border-l-4" style={{ borderLeftColor: accent }}>
      <div className="flex items-start justify-between">
        <p className="text-[11px] uppercase tracking-widest text-gray-400 font-semibold">{label}</p>
        {icon && <span className="text-lg opacity-60">{icon}</span>}
      </div>
      <p className="text-3xl font-bold mt-1 tabular-nums" style={{ color: accent }}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
}

export function Spinner({ className = 'w-4 h-4' }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity=".25" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

export function ErrorBanner({ error, onClose }) {
  if (!error) return null
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700 flex items-start justify-between gap-3">
      <span>{error}</span>
      {onClose && <button onClick={onClose} className="text-red-400 hover:text-red-700">✕</button>}
    </div>
  )
}

export function Empty({ children, className = '' }) {
  return <div className={`py-10 text-center text-sm text-gray-400 ${className}`}>{children}</div>
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
        {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  )
}

export function Modal({ open, onClose, title, children, wide }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 overflow-y-auto" onMouseDown={onClose}>
      <div className={`card w-full ${wide ? 'max-w-4xl' : 'max-w-lg'} mt-10 mb-10`} onMouseDown={e => e.stopPropagation()}>
        <div className="card-h">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-lg leading-none">✕</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export function DataTable({ rows, max = 8 }) {
  if (!rows?.length) return <Empty>No rows</Empty>
  const cols = Object.keys(rows[0])
  return (
    <div className="overflow-auto scroll-thin border border-gray-100 rounded-lg max-h-72">
      <table className="w-full text-xs">
        <thead className="bg-gray-50 sticky top-0">
          <tr>{cols.map(c => <th key={c} className="px-3 py-1.5 text-left font-semibold text-gray-500 whitespace-nowrap">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, max).map((r, i) => (
            <tr key={i} className="border-t border-gray-50">
              {cols.map(c => <td key={c} className="px-3 py-1 whitespace-nowrap text-gray-700">{r[c] === null ? '—' : String(r[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── formatting ──────────────────────────────────────────────────────────────

export function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (a >= 1e4) return (v / 1e3).toFixed(1) + 'K'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits })
}

export function fmtBytes(n) {
  if (n === null || n === undefined) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = n
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${u[i]}`
}

export function fmtTime(iso, withDate = true) {
  if (!iso) return '—'
  const d = new Date(iso)
  return withDate
    ? d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function timeAgo(iso) {
  if (!iso) return 'never'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 5) return 'just now'
  if (s < 60) return `${Math.round(s)}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

export function until(iso) {
  if (!iso) return '—'
  const s = (new Date(iso).getTime() - Date.now()) / 1000
  if (s <= 0) return 'now'
  if (s < 60) return `${Math.round(s)}s`
  return `${Math.round(s / 60)} min`
}
