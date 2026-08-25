import { useEffect, useState } from 'react'
import axios from 'axios'

const BASE = '/api/v1'

export default function AlertFeed() {
  const [history, setHistory] = useState([])

  useEffect(() => {
    axios.get(`${BASE}/alerts/history`)
      .then(r => setHistory(r.data.history ?? []))
      .catch(() => {})
  }, [])

  if (history.length === 0) {
    return <p className="text-sm text-gray-400 py-4">No alerts sent yet.</p>
  }

  return (
    <div className="space-y-3">
      {[...history].reverse().map((h, i) => (
        <div key={i} className="bg-white rounded-xl p-4 shadow-sm border-l-4 border-[#1E7A78]">
          <div className="flex gap-3 text-xs text-gray-400 mb-1">
            {h.telegram && <span className="text-[#1E7A78] font-semibold">✓ Telegram</span>}
            {h.email    && <span className="text-[#1E7A78] font-semibold">✓ Email</span>}
          </div>
          <p className="text-sm text-gray-700 leading-relaxed">{h.report}…</p>
        </div>
      ))}
    </div>
  )
}
