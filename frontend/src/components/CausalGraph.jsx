import { useMemo, useState } from 'react'
import { SEV_STYLE } from './ui'

const NODE_W = 168, NODE_H = 34, COL_W = 230, ROW_H = 58, PAD = 24

/** Layered left→right layout: a node's column is the longest causal path that reaches it. */
function layout(nodes, edges) {
  const ids = nodes.map(n => n.id)
  const connected = new Set(edges.flatMap(e => [e.from, e.to]))
  const level = Object.fromEntries(ids.map(id => [id, 0]))
  for (let iter = 0; iter < ids.length; iter++) {          // bounded relaxation (summary graph may have lag cycles)
    let changed = false
    for (const e of edges) {
      if (level[e.to] < level[e.from] + 1 && level[e.from] + 1 < ids.length) { level[e.to] = level[e.from] + 1; changed = true }
    }
    if (!changed) break
  }
  const cols = {}
  for (const id of ids.filter(i => connected.has(i))) (cols[level[id]] ??= []).push(id)
  // order each column by the mean row of its parents to reduce crossings
  const row = {}
  Object.keys(cols).map(Number).sort((a, b) => a - b).forEach(c => {
    const parentsRow = id => {
      const ps = edges.filter(e => e.to === id && row[e.from] !== undefined).map(e => row[e.from])
      return ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : 0
    }
    cols[c].sort((a, b) => parentsRow(a) - parentsRow(b))
    cols[c].forEach((id, i) => { row[id] = i })
  })
  const pos = {}
  let maxRow = 0, maxCol = 0
  for (const [c, list] of Object.entries(cols)) {
    list.forEach((id, i) => { pos[id] = { x: PAD + Number(c) * COL_W, y: PAD + i * ROW_H }; maxRow = Math.max(maxRow, i); maxCol = Math.max(maxCol, Number(c)) })
  }
  const isolated = ids.filter(i => !connected.has(i))
  const isoTop = PAD + (maxRow + 1) * ROW_H + 30
  const perRow = Math.max(1, maxCol + 1)
  isolated.forEach((id, i) => { pos[id] = { x: PAD + (i % perRow) * COL_W, y: isoTop + Math.floor(i / perRow) * ROW_H } })
  const height = (isolated.length ? isoTop + Math.ceil(isolated.length / perRow) * ROW_H : PAD + (maxRow + 1) * ROW_H) + PAD
  const width = PAD * 2 + (maxCol + 1) * COL_W - (COL_W - NODE_W)
  return { pos, width: Math.max(width, 400), height, isoTop: isolated.length ? isoTop : null }
}

export default function CausalGraph({ graph, highlight = [], origins = [] }) {
  const [hover, setHover] = useState(null)
  const nodes = graph?.nodes ?? []
  const edges = graph?.edges ?? []
  const { pos, width, height, isoTop } = useMemo(() => layout(nodes, edges), [nodes, edges])
  const hl = new Set(highlight.slice(0, -1).map((n, i) => `${n}→${highlight[i + 1]}`))
  const hlNodes = new Set(highlight)

  if (!nodes.length) return null

  return (
    <div className="overflow-auto scroll-thin">
      {/* scales down to fit the card; wide graphs stay readable thanks to the min width + horizontal scroll */}
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" style={{ minWidth: Math.min(width, 860) }}>
        <defs>
          {['pos', 'neg', 'hl'].map(k => (
            <marker key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill={k === 'pos' ? '#1E7A78' : k === 'neg' ? '#C04040' : '#0D3D3C'} />
            </marker>
          ))}
        </defs>
        {isoTop && <text x={PAD} y={isoTop - 12} className="fill-gray-400" fontSize="11">no causal links found</text>}

        {edges.map(e => {
          const a = pos[e.from], b = pos[e.to]
          if (!a || !b) return null
          const key = `${e.from}→${e.to}`
          const on = hl.has(key)
          const dim = (highlight.length && !on) || (hover && hover !== e.from && hover !== e.to)
          const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x - 2, y2 = b.y + NODE_H / 2
          const back = x2 <= x1
          const dx = Math.max(40, Math.abs(x2 - x1) / 2)
          const d = back
            ? `M${a.x + NODE_W / 2},${a.y + NODE_H} C${a.x + NODE_W / 2},${a.y + NODE_H + 40} ${b.x + NODE_W / 2},${b.y + NODE_H + 40} ${b.x + NODE_W / 2},${b.y + NODE_H + 2}`
            : `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`
          const color = on ? '#0D3D3C' : e.sign < 0 ? '#C04040' : '#1E7A78'
          return (
            <g key={key} opacity={dim ? 0.15 : 1}>
              <path d={d} fill="none" stroke={color} strokeWidth={on ? 3.5 : 1 + 3 * Math.min(e.weight, 1)}
                markerEnd={`url(#arrow-${on ? 'hl' : e.sign < 0 ? 'neg' : 'pos'})`} opacity={0.85} />
              {!back && (
                <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 5} textAnchor="middle" fontSize="10" className="fill-gray-500">
                  {e.sign < 0 ? '−' : '+'}{e.weight.toFixed(2)}{e.lag === 0 ? ' · same step' : e.lag > 1 ? ` · lag ${e.lag}` : ''}
                </text>
              )}
              <title>{`${e.from} → ${e.to}\nweight ${e.weight} (${e.sign < 0 ? 'negative' : 'positive'})\nlag ${e.lag} step(s)\nbootstrap confidence ${(e.confidence * 100).toFixed(0)}%`}</title>
            </g>
          )
        })}

        {nodes.map(n => {
          const p = pos[n.id]
          if (!p) return null
          const sev = n.anomalous ? SEV_STYLE[n.severity]?.dot ?? '#C04040' : null
          const isOrigin = origins.includes(n.id)
          const dim = highlight.length && !hlNodes.has(n.id)
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} opacity={dim ? 0.3 : 1}
              onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)} className="cursor-default">
              <rect width={NODE_W} height={NODE_H} rx="8" fill={sev ? sev : 'white'} fillOpacity={sev ? 0.14 : 1}
                stroke={isOrigin ? '#0D3D3C' : sev || '#1E7A78'} strokeWidth={isOrigin ? 2.5 : 1.3} />
              {sev && <circle cx="12" cy={NODE_H / 2} r="4" fill={sev} />}
              <text x={sev ? 22 : 10} y={NODE_H / 2 + 4} fontSize="11.5" fontWeight={isOrigin ? 700 : 500} className="fill-gray-800">
                {isOrigin ? '★ ' : ''}{n.id.length > 22 ? n.id.slice(0, 21) + '…' : n.id}
              </text>
              <title>{`${n.id}${n.source ? `\nsource: ${n.source}` : ''}${n.anomalous ? `\nanomalous (${n.severity})` : ''}${isOrigin ? '\nmost likely origin' : ''}`}</title>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
