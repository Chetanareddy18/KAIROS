import { useState } from 'react'
import { Empty, fmtTime } from './ui'

function AlertItem({ h }) {
  const [open, setOpen] = useState(false)
  const long = (h.report ?? '').length > 280
  return (
    <div className="rounded-lg p-4 border border-gray-100 border-l-4 border-l-teal bg-white">
      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400 mb-2">
        <span>{fmtTime(h.sent_at)}</span>
        {h.anomaly_count > 0 && <span>· {h.anomaly_count} anomalies</span>}
        {h.telegram && <span className="chip bg-sky-50 text-sky-700">✓ Telegram</span>}
        {h.email && <span className="chip bg-indigo-50 text-indigo-700">✓ Email</span>}
        {!h.telegram && !h.email && <span className="chip bg-gray-100 text-gray-500">stored only</span>}
        {h.verified && <span className="chip bg-emerald-50 text-emerald-700">✓ verified</span>}
        {h.model && <span className="chip bg-gray-50 text-gray-500">{h.model}</span>}
      </div>
      <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">
        {open || !long ? h.report : h.report.slice(0, 280) + '…'}
      </p>
      {long && <button onClick={() => setOpen(o => !o)} className="text-xs text-teal mt-1">{open ? 'less' : 'more'}</button>}
    </div>
  )
}

export default function AlertFeed({ history }) {
  if (!history?.length) return <Empty>No alerts yet — KAIROS sends one when new alert-worthy anomalies appear.</Empty>
  return <div className="space-y-3">{history.map(h => <AlertItem key={h.id} h={h} />)}</div>
}
