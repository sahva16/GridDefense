// Measurements of the shown snapshot: voltage profile, line flows, detector history.
import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useStore } from '../store'
import { branchName } from '../grid'
import Panel from './Panel'

const TABS = ['Voltage', 'Line flows', 'Detectors'] as const
const axis = { fill: '#6f8794', fontSize: 11 }
const tip = { background: '#0b141b', border: '1px solid #22323e', fontSize: 12 }

export default function Charts() {
  const { shown: e, events, selectBus, selectedBus } = useStore()
  const [tab, setTab] = useState<typeof TABS[number]>('Voltage')
  const named = new Set(e?.result.alarm ? e.result.named_buses : [])
  const vm = useMemo(() => (e?.result.measurements?.Vm ?? []).map((v, i) => ({ bus: `B${i + 1}`, n: i + 1, v })), [e])
  const lf = useMemo(() => (e?.result.line_flow_mva ?? []).map((v, i) => ({ line: branchName(i), v })), [e])
  const hist = useMemo(() => events.slice(0, 60).slice().reverse().map((x) => ({
    id: x.id, AE: +x.result.detectors.ae.score.toFixed(3), RF: +x.result.detectors.rf.score.toFixed(3), Physics: +x.result.detectors.physics.score.toFixed(3),
  })), [events])
  return (
    <Panel title="Measurements" className="charts"
      actions={<div className="tabs" role="tablist">{TABS.map((t) => (
        <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>{t}</button>
      ))}</div>}>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          {tab === 'Voltage' ? (
            <BarChart data={vm} margin={{ top: 8, right: 8, bottom: 0, left: -10 }} onClick={(s) => { const p = s?.activePayload?.[0]?.payload; if (p) selectBus(p.n) }}>
              <CartesianGrid stroke="#16242e" vertical={false} />
              <ReferenceArea y1={0.95} y2={1.05} fill="#3ddc84" fillOpacity={0.05} />
              <XAxis dataKey="bus" tick={axis} tickLine={false} axisLine={{ stroke: '#1d2e3a' }} interval={0} />
              <YAxis domain={[0.98, 1.1]} tick={axis} tickLine={false} axisLine={false} tickFormatter={(v) => v.toFixed(2)} />
              <Tooltip cursor={{ fill: '#ffffff08' }} contentStyle={tip} formatter={(v) => [`${Number(v).toFixed(4)} pu`, 'Vm (measured)']} />
              <Bar dataKey="v" isAnimationActive={false} radius={[2, 2, 0, 0]}>
                {vm.map((d) => <Cell key={d.n} fill={named.has(d.n) ? '#ff3b3b' : d.n === selectedBus ? '#e8f1f5' : '#2aa9bd'} />)}
              </Bar>
            </BarChart>
          ) : tab === 'Line flows' ? (
            <BarChart data={lf} margin={{ top: 8, right: 8, bottom: 0, left: -10 }}>
              <CartesianGrid stroke="#16242e" vertical={false} />
              <XAxis dataKey="line" tick={{ ...axis, fontSize: 10 }} tickLine={false} axisLine={{ stroke: '#1d2e3a' }} interval={0} angle={-45} textAnchor="end" height={36} />
              <YAxis tick={axis} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: '#ffffff08' }} contentStyle={tip} formatter={(v) => [`${Number(v).toFixed(1)} MVA`, '|S| from measurements']} />
              <Bar dataKey="v" fill="#2aa9bd" isAnimationActive={false} radius={[2, 2, 0, 0]} />
            </BarChart>
          ) : (
            <LineChart data={hist} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
              <CartesianGrid stroke="#16242e" vertical={false} />
              <XAxis dataKey="id" tick={axis} tickLine={false} axisLine={{ stroke: '#1d2e3a' }} minTickGap={24} />
              <YAxis domain={[0, 1]} tick={axis} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={tip} />
              <Legend wrapperStyle={{ fontSize: 11 }} iconSize={10} />
              <Line dataKey="AE" stroke="#5ab8ff" dot={false} strokeWidth={1.4} isAnimationActive={false} />
              <Line dataKey="RF" stroke="#b38cff" dot={false} strokeWidth={1.4} isAnimationActive={false} />
              <Line dataKey="Physics" stroke="#ffb020" dot={false} strokeWidth={1.4} isAnimationActive={false} />
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
      {tab === 'Voltage' && <p className="legend-line">Measured voltage magnitude per bus (per unit). Shaded: 0.95–1.05 pu. Red: bus named by GridDefense.</p>}
      {tab === 'Line flows' && <p className="legend-line">Apparent power per line computed from the measured voltages (the LineFlow features).</p>}
      {tab === 'Detectors' && <p className="legend-line">Each layer's score over the last 60 snapshots.</p>}
    </Panel>
  )
}
