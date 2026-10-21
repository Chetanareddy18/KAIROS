import { useEffect, useRef, useState } from 'react'
import { api, errMsg } from '../api'
import { useAction, useApi } from '../hooks'
import { DataTable, Empty, ErrorBanner, PageHeader, Spinner, fmtBytes, fmtTime } from '../components/ui'

const HAS_GZIP = typeof CompressionStream !== 'undefined'
const HAS_SHA = typeof crypto !== 'undefined' && !!crypto.subtle

async function sha256Hex(buf) {
  if (!HAS_SHA) return null
  const d = await crypto.subtle.digest('SHA-256', buf)
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('')
}

async function gzip(buf) {
  const stream = new Blob([buf]).stream().pipeThrough(new CompressionStream('gzip'))
  return new Uint8Array(await new Response(stream).arrayBuffer())
}

const resumeKey = f => `kairos_tx_${f.name}_${f.size}_${f.lastModified}`

function ChunkGrid({ states }) {
  if (!states.length) return null
  const cells = states.length > 600 ? 600 : states.length
  const per = states.length / cells
  const color = s => ({ done: '#1E7A78', sending: '#D4B896', error: '#C04040' }[s] ?? '#E5E7EB')
  return (
    <div className="flex flex-wrap gap-[3px]">
      {Array.from({ length: cells }, (_, i) => {
        const slice = states.slice(Math.floor(i * per), Math.floor((i + 1) * per) || Math.floor(i * per) + 1)
        const s = slice.includes('error') ? 'error' : slice.every(x => x === 'done') ? 'done' : slice.includes('sending') ? 'sending' : 'todo'
        return <span key={i} className="w-2.5 h-2.5 rounded-sm" style={{ background: color(s) }} />
      })}
    </div>
  )
}

function Benchmark() {
  const { data } = useApi('/benchmark')
  if (!data?.results?.length) return null
  const m = data.meta
  const max = Math.max(...data.results.map(r => r.seconds))
  return (
    <div className="card">
      <div className="card-h">
        <span className="font-semibold text-sm">Measured: {Number(m.rows).toLocaleString()} raw rows · {fmtBytes(m.raw_bytes)}</span>
        <span className="text-xs text-gray-400">{m.stream_mbps_cap ? `${m.stream_mbps_cap} Mbit/s per connection (emulated WAN)` : 'localhost'} · benchmark/benchmark_ingestion.py</span>
      </div>
      <div className="p-5 space-y-3">
        {data.results.map(r => (
          <div key={r.method}>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-medium text-gray-700">{r.method}</span>
              <span className="tabular-nums text-gray-500">{r.seconds.toFixed(1)}s · {fmtBytes(r.bytes_on_wire)} on wire · <b className="text-teal">{r.speedup_vs_ftp}×</b></span>
            </div>
            <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${(r.seconds / max) * 100}%`, background: r.method.startsWith('1') || r.method.startsWith('2') ? '#9CA3AF' : '#1E7A78' }} />
            </div>
            {r.note && <div className="text-[11px] text-gray-400 mt-0.5">{r.note}</div>}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Transfer() {
  const [file, setFile] = useState(null)
  const [streams, setStreams] = useState(8)
  const [chunkMb, setChunkMb] = useState(4)
  const [compress, setCompress] = useState(HAS_GZIP ? 'gzip' : 'none')
  const [phase, setPhase] = useState('idle')        // idle | uploading | paused | done
  const [states, setStates] = useState([])
  const [stats, setStats] = useState({ raw: 0, wire: 0, started: 0, elapsed: 0 })
  const [result, setResult] = useState(null)
  const [suggest, setSuggest] = useState(null)
  const [source, setSource] = useState('')
  const [mapping, setMapping] = useState('')
  const [error, setError] = useState('')
  const [drag, setDrag] = useState(false)
  const pauseRef = useRef(false)
  const history = useApi('/transfers', { interval: phase === 'uploading' ? 0 : 20_000 })
  const ingest = useAction()

  useEffect(() => {
    if (phase !== 'uploading') return
    const id = setInterval(() => setStats(s => ({ ...s, elapsed: (performance.now() - s.started) / 1000 })), 250)
    return () => clearInterval(id)
  }, [phase])

  function pick(f) {
    if (!f) return
    setFile(f); setPhase('idle'); setStates([]); setResult(null); setSuggest(null); setError('')
    setSource(f.name.replace(/\.[^.]+(\.gz|\.zst)?$/, '').replace(/[^A-Za-z0-9_.-]/g, '_'))
  }

  async function start() {
    setError(''); setResult(null); setSuggest(null)
    pauseRef.current = false
    const chunk = chunkMb * 1024 * 1024
    try {
      let st
      const saved = localStorage.getItem(resumeKey(file))
      if (saved) {
        try { st = (await api.get(`/transfer/${saved}`)).data } catch { st = null }
        if (st && (st.status === 'completed' || st.status === 'failed' || st.chunk_size !== chunk)) st = null
      }
      if (!st) {
        st = (await api.post('/transfer/start', { filename: file.name, size_bytes: file.size, chunk_size: chunk, compression: compress })).data
        localStorage.setItem(resumeKey(file), st.id)
      }
      const total = st.total_chunks
      const missing = new Set(st.missing)
      const local = Array.from({ length: total }, (_, i) => (missing.has(i) ? 'todo' : 'done'))
      setStates([...local])
      setPhase('uploading')
      setStats({ raw: (total - missing.size) * chunk, wire: 0, started: performance.now(), elapsed: 0 })

      const queue = [...missing].sort((a, b) => a - b)
      const sendOne = async i => {
        const raw = new Uint8Array(await file.slice(i * chunk, Math.min(file.size, (i + 1) * chunk)).arrayBuffer())
        const hash = await sha256Hex(raw)
        const body = compress === 'gzip' ? await gzip(raw) : raw
        for (let attempt = 0; attempt < 5; attempt++) {
          try {
            await api.put(`/transfer/${st.id}/chunk/${i}`, body, {
              headers: { 'Content-Type': 'application/octet-stream', ...(hash ? { 'X-Chunk-SHA256': hash } : {}) },
              transformRequest: [d => d],
            })
            setStats(s => ({ ...s, raw: s.raw + raw.byteLength, wire: s.wire + body.byteLength }))
            return
          } catch (e) {
            if (attempt === 4) throw e
            await new Promise(r => setTimeout(r, 400 * 2 ** attempt))
          }
        }
      }
      const worker = async () => {
        while (queue.length && !pauseRef.current) {
          const i = queue.shift()
          local[i] = 'sending'; setStates([...local])
          try { await sendOne(i); local[i] = 'done' } catch (e) { local[i] = 'error'; setStates([...local]); throw e }
          setStates([...local])
        }
      }
      await Promise.all(Array.from({ length: Math.min(streams, Math.max(1, queue.length)) }, worker))
      if (pauseRef.current) { setPhase('paused'); return }

      const done = (await api.post(`/transfer/${st.id}/complete`, { ingest: false })).data
      localStorage.removeItem(resumeKey(file))
      setResult(done); setPhase('done'); history.reload()
      try {
        const s = (await api.get(`/files/${encodeURIComponent(done.file_id)}/suggest`)).data
        setSuggest(s); setMapping(JSON.stringify(s.mapping ?? {}, null, 1))
      } catch { /* not a tabular file — fine */ }
    } catch (e) {
      setError(errMsg(e) + ' — click Resume to continue from the missing chunks.'); setPhase('paused')
    }
  }

  async function doIngest() {
    let m
    try { m = mapping.trim() ? JSON.parse(mapping) : null } catch { ingest.setError('Mapping is not valid JSON'); return }
    const r = await ingest.run(async () => (await api.post(`/files/${encodeURIComponent(result.file_id)}/ingest`, { source, mapping: m })).data)
    if (r) setResult(res => ({ ...res, ingest: r }))
  }

  const doneCount = states.filter(s => s === 'done').length
  const pct = states.length ? (doneCount / states.length) * 100 : 0
  const rate = stats.elapsed > 0 ? stats.wire / stats.elapsed : 0

  return (
    <div className="space-y-6">
      <PageHeader title="Fast Transfer"
        subtitle="Large files without the FTP wait: chunked, compressed, parallel, SHA-256 verified and resumable — then ingested with a SLAC-inferred mapping." />

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="card lg:col-span-2 p-5 space-y-5">
          <label onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]) }}
            className={`block border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${drag ? 'border-teal bg-teal-light' : 'border-gray-200 hover:border-teal'}`}>
            <input type="file" className="hidden" onChange={e => pick(e.target.files[0])} />
            {file
              ? <div><div className="font-semibold">{file.name}</div><div className="text-sm text-gray-500">{fmtBytes(file.size)} · {Math.ceil(file.size / (chunkMb * 1048576))} chunks</div></div>
              : <div className="text-gray-500"><div className="text-3xl mb-1">⇪</div>Drop a file here or click to choose<div className="text-xs mt-1">CSV · Excel · Parquet · JSON · .gz — any size up to the server limit</div></div>}
          </label>

          <div className="grid sm:grid-cols-3 gap-4">
            <div>
              <label className="label">Parallel streams: {streams}</label>
              <input type="range" min="1" max="16" value={streams} onChange={e => setStreams(+e.target.value)} className="w-full accent-teal" disabled={phase === 'uploading'} />
              <div className="text-[11px] text-gray-400">FTP = 1 stream</div>
            </div>
            <div>
              <label className="label">Chunk size</label>
              <select className="input" value={chunkMb} onChange={e => setChunkMb(+e.target.value)} disabled={phase === 'uploading'}>
                {[1, 2, 4, 8, 16, 32].map(n => <option key={n} value={n}>{n} MB</option>)}
              </select>
            </div>
            <div>
              <label className="label">Compression</label>
              <select className="input" value={compress} onChange={e => setCompress(e.target.value)} disabled={phase === 'uploading'}>
                {HAS_GZIP && <option value="gzip">gzip (per chunk)</option>}
                <option value="none">none</option>
              </select>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 items-center">
            {phase !== 'uploading'
              ? <button className="btn-primary" disabled={!file} onClick={start}>{phase === 'paused' ? '↻ Resume' : '⇪ Start transfer'}</button>
              : <button className="btn-ghost" onClick={() => { pauseRef.current = true }}>❚❚ Pause</button>}
            {!HAS_SHA && <span className="text-xs text-amber-700">Per-chunk SHA-256 needs HTTPS or localhost</span>}
          </div>
          <ErrorBanner error={error} onClose={() => setError('')} />

          {states.length > 0 && (
            <div className="space-y-3">
              <div className="flex justify-between text-sm">
                <span><b>{pct.toFixed(0)}%</b> · {doneCount}/{states.length} chunks</span>
                <span className="text-gray-500 tabular-nums">
                  {fmtBytes(stats.wire)} on wire{stats.raw ? ` (${(stats.raw / Math.max(stats.wire, 1)).toFixed(1)}× smaller)` : ''} · {fmtBytes(rate)}/s · {stats.elapsed.toFixed(1)}s
                </span>
              </div>
              <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden"><div className="h-full bg-teal transition-all" style={{ width: `${pct}%` }} /></div>
              <ChunkGrid states={states} />
              <div className="flex gap-4 text-[11px] text-gray-400">
                <span><span className="inline-block w-2 h-2 rounded-sm bg-teal mr-1" />verified</span>
                <span><span className="inline-block w-2 h-2 rounded-sm bg-sand mr-1" />in flight</span>
                <span><span className="inline-block w-2 h-2 rounded-sm bg-gray-200 mr-1" />pending</span>
              </div>
            </div>
          )}

          {result && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm space-y-1">
              <div className="font-semibold text-emerald-800">✓ Transfer complete and verified</div>
              <div className="text-emerald-900 text-xs">SHA-256 {result.sha256?.slice(0, 24)}… · stored as <code>{result.file_id}</code> · {fmtBytes(result.size_bytes)} file, {fmtBytes(result.bytes_on_wire)} on wire</div>
            </div>
          )}

          {result && suggest && (
            <div className="space-y-3 border-t border-gray-100 pt-4">
              <div className="font-semibold text-sm">Ingest into KAIROS</div>
              {suggest.sample?.length > 0 && <DataTable rows={suggest.sample} max={5} />}
              {suggest.notes?.map((n, i) => <div key={i} className="text-xs text-gray-500">• SLAC: {n}</div>)}
              <div className="grid sm:grid-cols-3 gap-3">
                <div><label className="label">Source name</label><input className="input" value={source} onChange={e => setSource(e.target.value)} /></div>
                <div className="sm:col-span-2"><label className="label">Mapping (SLAC suggestion — edit if needed)</label>
                  <textarea className="input font-mono text-xs" rows={4} value={mapping} onChange={e => setMapping(e.target.value)} /></div>
              </div>
              <ErrorBanner error={ingest.error} />
              <button className="btn-primary" onClick={doIngest} disabled={ingest.busy || !source}>{ingest.busy ? <><Spinner /> Ingesting…</> : 'Ingest file'}</button>
              {result.ingest && (
                <div className="text-sm text-gray-700">
                  ✓ {result.ingest.rows.toLocaleString()} KPI rows stored in <b>{result.ingest.source}</b>
                  {result.ingest.aggregated_at_source && ' (raw records aggregated by DuckDB)'} · metrics: {result.ingest.metrics.slice(0, 8).join(', ')} · {result.ingest.seconds}s.
                  {' '}Run the pipeline on the Overview page to analyse them.
                </div>
              )}
            </div>
          )}
        </div>

        <div className="space-y-6">
          <div className="card p-5 text-sm text-gray-600 leading-relaxed space-y-2">
            <div className="font-semibold text-gray-800">Why this is faster than FTP</div>
            <p><b>Parallel streams.</b> One TCP connection is capped by window size and latency; N streams use the whole link.</p>
            <p><b>Compression.</b> CSV exports shrink 4–10× on the wire.</p>
            <p><b>Resume.</b> A dropped connection re-sends only the missing chunks, never the whole file.</p>
            <p><b>Integrity.</b> Every chunk carries a SHA-256; the server re-hashes the whole file.</p>
            <p className="text-xs text-gray-400">And often no transfer is needed at all: the edge agent aggregates at the source and sends only KPIs.</p>
          </div>
          <div className="card overflow-hidden">
            <div className="card-h"><span className="font-semibold text-sm">Recent transfers</span></div>
            {(history.data?.transfers ?? []).length === 0 ? <Empty>None yet</Empty> : (
              <div className="divide-y divide-gray-50">
                {history.data.transfers.slice(0, 8).map(t => (
                  <div key={t.id} className="px-5 py-2.5 text-xs flex justify-between gap-3">
                    <div className="min-w-0"><div className="font-medium text-gray-800 truncate">{t.filename}</div>
                      <div className="text-gray-400">{fmtTime(t.created_at)} · {fmtBytes(t.size_bytes)} → {fmtBytes(t.bytes_on_wire)}</div></div>
                    <span className={`chip h-fit ${t.status === 'completed' ? 'bg-emerald-50 text-emerald-700' : t.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>
                      {t.status === 'completed' ? 'done' : t.status === 'failed' ? 'failed' : `${Math.round(t.progress * 100)}%`}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <Benchmark />
    </div>
  )
}
