import { useEffect, useState } from 'react'
import axios from 'axios'
import AlertFeed from '../components/AlertFeed'

const BASE = '/api/v1'

export default function Reports() {
  const [report,    setReport]    = useState('')
  const [loading,   setLoading]   = useState(false)
  const [causal,    setCausal]    = useState(null)

  async function fetchReport() {
    setLoading(true)
    try {
      const [r, inv] = await Promise.all([
        axios.post(`${BASE}/report`),
        axios.post(`${BASE}/investigate`),
      ])
      setReport(r.data.report ?? '')
      setCausal(inv.data)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Reports & Causal Analysis</h1>
          <p className="text-sm text-gray-400 mt-1">NL report generation + CBMG root cause</p>
        </div>
        <button
          onClick={fetchReport}
          disabled={loading}
          className="bg-[#1E7A78] text-white px-5 py-2 rounded-lg font-semibold text-sm hover:bg-[#0D3D3C] disabled:opacity-50"
        >
          {loading ? 'Generating…' : 'Generate Report'}
        </button>
      </div>

      {report && (
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="text-xs uppercase tracking-widest text-gray-400 mb-3">NL Executive Report</div>
          <p className="text-sm leading-relaxed whitespace-pre-line text-gray-800">{report}</p>
        </div>
      )}

      {causal && (
        <div className="bg-white rounded-xl shadow-sm p-6">
          <div className="text-xs uppercase tracking-widest text-gray-400 mb-3">Causal Root Causes (CBMG)</div>
          <p className="text-sm text-gray-600 mb-4">{causal.summary}</p>
          {causal.root_causes?.length > 0 ? (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-400 uppercase">
                <tr>
                  <th className="px-4 py-2 text-left">Cause</th>
                  <th className="px-4 py-2 text-left">Effect</th>
                  <th className="px-4 py-2 text-right">Strength</th>
                  <th className="px-4 py-2 text-right">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {causal.root_causes.map((rc, i) => (
                  <tr key={i} className="border-t border-gray-50">
                    <td className="px-4 py-2 font-medium text-[#1E7A78]">{rc.cause}</td>
                    <td className="px-4 py-2">{rc.effect}</td>
                    <td className="px-4 py-2 text-right">{(rc.strength * 100).toFixed(1)}%</td>
                    <td className="px-4 py-2 text-right">{(rc.confidence * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-gray-400">No causal relationships found in current data.</p>
          )}
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm p-6">
        <div className="text-xs uppercase tracking-widest text-gray-400 mb-3">Alert Delivery History</div>
        <AlertFeed />
      </div>
    </div>
  )
}
