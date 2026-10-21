import { useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import { getApiKey, setApiKey } from './api'
import { useApi } from './hooks'
import { Modal, timeAgo, until } from './components/ui'
import Home from './pages/Home'
import Causal from './pages/Causal'
import Reports from './pages/Reports'
import Sources from './pages/Sources'
import Transfer from './pages/Transfer'

const NAV = [
  { to: '/', label: 'Overview', icon: '◉', end: true },
  { to: '/causal', label: 'Causal Analysis', icon: '⇢' },
  { to: '/reports', label: 'Reports & Alerts', icon: '✉' },
  { to: '/sources', label: 'Data Sources', icon: '⛁' },
  { to: '/transfer', label: 'Fast Transfer', icon: '⇪' },
]

function StatusPill({ status, error }) {
  if (error) return <span className="chip bg-red-100 text-red-700">● API offline</span>
  if (!status) return <span className="chip bg-gray-100 text-gray-500">connecting…</span>
  if (status.pipeline_running) return <span className="chip bg-amber-100 text-amber-800"><span className="pulse-dot">●</span> pipeline running</span>
  return <span className="chip bg-emerald-100 text-emerald-700">● live</span>
}

function ApiKeyModal({ open, onClose }) {
  const [key, setKey] = useState(getApiKey())
  return (
    <Modal open={open} onClose={onClose} title="API key">
      <p className="text-sm text-gray-500 mb-3">Required only when the backend sets <code>KAIROS_API_KEY</code>. Stored in this browser.</p>
      <input className="input mb-4" value={key} onChange={e => setKey(e.target.value)} placeholder="X-API-Key" />
      <div className="flex justify-end gap-2">
        <button className="btn-ghost" onClick={() => { setApiKey(''); setKey(''); onClose(); location.reload() }}>Clear</button>
        <button className="btn-primary" onClick={() => { setApiKey(key.trim()); onClose(); location.reload() }}>Save</button>
      </div>
    </Modal>
  )
}

export default function App() {
  const { data: status, error } = useApi('/status', { interval: 10_000 })
  const [keyOpen, setKeyOpen] = useState(false)
  const needsKey = error && /401|API key/i.test(error)

  return (
    <BrowserRouter>
      <div className="min-h-screen flex">
        <aside className="hidden md:flex w-60 shrink-0 flex-col bg-teal-dark text-white">
          <div className="px-6 py-5 border-b border-white/10">
            <div className="text-2xl font-black tracking-[0.25em]">KAIROS</div>
            <div className="text-[11px] text-white/60 mt-1 leading-snug">Autonomous Causal<br />Business Intelligence</div>
          </div>
          <nav className="flex-1 px-3 py-4 space-y-1">
            {NAV.map(n => (
              <NavLink key={n.to} to={n.to} end={n.end}
                className={({ isActive }) => `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${isActive ? 'bg-white/15 font-semibold' : 'text-white/75 hover:bg-white/10'}`}>
                <span className="w-5 text-center opacity-80">{n.icon}</span>{n.label}
              </NavLink>
            ))}
          </nav>
          <div className="px-5 py-4 border-t border-white/10 text-[11px] text-white/60 space-y-1">
            <div>5 agents · LangGraph · DuckDB</div>
            {status?.scheduler?.enabled && <div>next run in {until(status.scheduler.next_run)}</div>}
            {status?.last_run && <div>last run {timeAgo(status.last_run.finished_at)}</div>}
            <button onClick={() => setKeyOpen(true)} className="underline hover:text-white">API key</button>
          </div>
        </aside>

        <div className="flex-1 min-w-0 flex flex-col">
          <header className="bg-white border-b border-gray-100 px-4 md:px-8 py-3 flex items-center justify-between gap-4">
            <div className="md:hidden font-black tracking-[0.2em] text-teal">KAIROS</div>
            <nav className="md:hidden flex gap-1 overflow-x-auto scroll-thin">
              {NAV.map(n => (
                <NavLink key={n.to} to={n.to} end={n.end}
                  className={({ isActive }) => `px-2 py-1 rounded text-xs whitespace-nowrap ${isActive ? 'bg-teal-light text-teal font-semibold' : 'text-gray-500'}`}>
                  {n.label}
                </NavLink>
              ))}
            </nav>
            <div className="hidden md:block text-sm text-gray-500">
              {status ? <>Monitoring <b className="text-gray-800">{status.data.series}</b> metrics from <b className="text-gray-800">{status.data.sources_registered}</b> sources · scheduler every {status.scheduler.interval_min} min</> : 'Proactive monitoring · causal root cause · verified reports'}
            </div>
            <div className="flex items-center gap-2">
              {status && !status.llm.groq && <span className="chip bg-gray-100 text-gray-500" title="Set GROQ_API_KEY or run Ollama for LLM reports">template reports</span>}
              <StatusPill status={status} error={error} />
            </div>
          </header>

          {needsKey && (
            <div className="bg-amber-50 border-b border-amber-200 px-8 py-2 text-sm text-amber-800">
              The API requires a key. <button className="underline font-semibold" onClick={() => setKeyOpen(true)}>Enter API key</button>
            </div>
          )}

          <main className="flex-1 px-4 md:px-8 py-6 max-w-[1400px] w-full mx-auto">
            <Routes>
              <Route path="/" element={<Home status={status} />} />
              <Route path="/causal" element={<Causal />} />
              <Route path="/reports" element={<Reports status={status} />} />
              <Route path="/sources" element={<Sources />} />
              <Route path="/transfer" element={<Transfer />} />
            </Routes>
          </main>
        </div>
      </div>
      <ApiKeyModal open={keyOpen} onClose={() => setKeyOpen(false)} />
    </BrowserRouter>
  )
}
