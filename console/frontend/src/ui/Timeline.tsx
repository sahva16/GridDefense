// Event history and replay: fusion score of the recent snapshots against the threshold.
// Click a point (or use the transport buttons) to put any past event back on the grid.
import { useEffect, useMemo, useState } from 'react'
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts'
import { useStore } from '../store'
import { fmtTime, sourceLabel } from '../text'
import Panel from './Panel'

const N = 90

export default function Timeline() {
  const { events, pinnedId, pin } = useStore()
  const [playing, setPlaying] = useState(false)
  const hist = useMemo(() => events.slice(0, N).slice().reverse(), [events])
  const data = useMemo(() => hist.map((e) => ({
    id: e.id, score: +e.result.fusion.score.toFixed(3), alarm: e.result.alarm ? +e.result.fusion.score.toFixed(3) : null,
    sim: e.source !== 'live' ? +e.result.fusion.score.toFixed(3) : null, time: fmtTime(e.time), src: sourceLabel(e),
  })), [hist])
  const thr = events[0]?.result.fusion.threshold ?? 0.45
  const idx = pinnedId != null ? hist.findIndex((e) => e.id === pinnedId) : hist.length - 1
  const step = (d: number) => {
    const i = Math.min(hist.length - 1, Math.max(0, (idx < 0 ? hist.length - 1 : idx) + d))
    if (hist[i]) pin(i === hist.length - 1 && d > 0 ? null : hist[i].id)
  }
  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => {
      if (idx >= hist.length - 1 || pinnedId == null) { setPlaying(false); pin(null); return }
      pin(hist[idx + 1].id)
    }, 900)
    return () => clearInterval(t)
  }, [playing, idx, hist, pinnedId, pin])

  const shown = pinnedId != null ? hist.find((e) => e.id === pinnedId) : undefined
  return (
    <Panel title="Event history & replay" className="timeline"
      meta={pinnedId == null ? <span className="live-tag">● LIVE</span> : <span className="replay-tag">REPLAY · #{pinnedId}{shown ? ` · ${fmtTime(shown.time)}` : ''}</span>}
      actions={
        <div className="transport" role="group" aria-label="Replay controls">
          <button className="btn xs" onClick={() => hist[0] && pin(hist[0].id)} aria-label="Oldest">⏮</button>
          <button className="btn xs" onClick={() => step(-1)} aria-label="Previous event">◀</button>
          <button className="btn xs" onClick={() => { if (pinnedId == null && hist.length) pin(hist[0].id); setPlaying((p) => !p) }} aria-label={playing ? 'Pause' : 'Play replay'}>{playing ? '❚❚' : '▶'}</button>
          <button className="btn xs" onClick={() => step(1)} aria-label="Next event">▶❘</button>
          <button className={`btn xs ${pinnedId == null ? 'on' : ''}`} onClick={() => { setPlaying(false); pin(null) }}>LIVE</button>
        </div>
      }>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 10, bottom: 0, left: -18 }}
            onClick={(s) => { const p = s?.activePayload?.[0]?.payload; if (p) { setPlaying(false); pin(p.id) } }}>
            <CartesianGrid stroke="#16242e" vertical={false} />
            <XAxis dataKey="id" tick={{ fill: '#6f8794', fontSize: 11 }} tickLine={false} axisLine={{ stroke: '#1d2e3a' }} minTickGap={24} />
            <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tick={{ fill: '#6f8794', fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip cursor={{ stroke: '#2b4553' }} contentStyle={{ background: '#0b141b', border: '1px solid #22323e', fontSize: 12 }}
              labelFormatter={(id, p) => `#${id} · ${p?.[0]?.payload?.time ?? ''} · ${p?.[0]?.payload?.src ?? ''}`}
              formatter={(v, n) => [Number(v).toFixed(3), n === 'score' ? 'fusion score' : n === 'alarm' ? 'alarm' : 'simulated']} />
            <ReferenceLine y={thr} stroke="#ffb020" strokeDasharray="5 4" label={{ value: `threshold ${thr.toFixed(2)}`, fill: '#ffb020', fontSize: 11, position: 'insideTopLeft' }} />
            {pinnedId != null && <ReferenceLine x={pinnedId} stroke="#e8f1f5" strokeWidth={1.5} />}
            <Line type="linear" dataKey="score" stroke="#35c6da" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <Scatter dataKey="sim" fill="none" stroke="#e8f1f5" shape="diamond" isAnimationActive={false} />
            <Scatter dataKey="alarm" fill="#ff3b3b" isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="legend-line"><i className="lg-line" />fusion score <i className="lg-alarm" />alarm <i className="lg-sim" />scenario / custom attack <i className="lg-thr" />threshold</p>
    </Panel>
  )
}
