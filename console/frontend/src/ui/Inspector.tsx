// Snapshot inspector: everything behind one decision, in five tabs.
//   Why          — rule-based explanation built from this snapshot's numbers (backend app/explain.py)
//   Measurements — observed Vm, Va, Pd, Qd vs the normal reference (development normals)
//   Physics map  — 14 buses × 4 checks, coloured by z-score against the limit
//   Localisation — actual vs predicted buses (only when the ground truth is known)
//   Compare      — this snapshot side by side with another one
import { useMemo, useState } from 'react'
import type { GridEvent, MeasCell, Verdict } from '../api'
import { api } from '../api'
import { useStore } from '../store'
import { CHECK_TEXT, fmtTime, list, sourceLabel, truthKnown } from '../text'

type Tab = 'why' | 'meas' | 'heat' | 'loc' | 'cmp'
const CHECKS = ['P_res', 'Q_res', 'Va_neighbor', 'Vm_neighbor'] as const
const QTY = [
  { k: 'Vm', label: 'Voltage magnitude', unit: 'p.u.', d: 4 },
  { k: 'Va', label: 'Voltage angle', unit: '°', d: 3 },
  { k: 'Pd', label: 'Active load', unit: 'MW', d: 2 },
  { k: 'Qd', label: 'Reactive load', unit: 'MVAr', d: 2 },
] as const

export function zColor(z: number, limit: number) {
  // below 0 → neutral; 0…limit → cyan→amber; above limit → red, darker as z grows
  if (z <= 0) return 'var(--hm-0)'
  if (z <= limit) return `color-mix(in oklab, var(--hm-low) ${100 - (z / limit) * 100}%, var(--hm-mid))`
  const t = Math.min(1, (z - limit) / (3 * limit))
  return `color-mix(in oklab, var(--hm-hot) ${100 - t * 55}%, var(--hm-max))`
}

function Why({ e }: { e: GridEvent }) {
  const x = e.result.explanation
  if (!x) return <p className="dim">This event was logged before explanations were added.</p>
  return (
    <div className="why">
      <p className={`why-head ${e.result.alarm ? 'alarm' : 'ok'}`}>{x.summary}</p>
      {x.borderline && <p className="note warn">Borderline: a small change in the readings could flip this decision.</p>}
      <ol>{x.lines.slice(1, -1).map((l, i) => <li key={i}>{l}</li>)}</ol>
      <p className="note">{x.lines[x.lines.length - 1]}</p>
      <p className="dim small">These sentences are filled in by fixed rules from the numbers above; no language model writes them.</p>
    </div>
  )
}

function devClass(c: MeasCell) {
  const z = c.deviation_sd == null ? 0 : Math.abs(c.deviation_sd)
  return z >= 3 ? 'dev3' : z >= 2 ? 'dev2' : ''
}

function Measurements({ e, sel, onSel }: { e: GridEvent; sel: number | null; onSel: (b: number) => void }) {
  const t = e.result.measurement_table
  const [q, setQ] = useState<'Vm' | 'Va' | 'Pd' | 'Qd'>('Vm')
  if (!t) return <p className="dim">No normal reference in this model bundle (re-export with the current export cell).</p>
  const meta = QTY.find((x) => x.k === q)!
  return (
    <div>
      <div className="seg" role="tablist" aria-label="Quantity">
        {QTY.map((x) => <button key={x.k} role="tab" aria-selected={q === x.k} className={q === x.k ? 'on' : ''} onClick={() => setQ(x.k)}>{x.label}</button>)}
      </div>
      <div className="tbl-wrap">
        <table className="tbl meas-tbl">
          <thead><tr><th>Bus</th><th className="r">Observed</th><th className="r">Normal mean</th><th className="r">Normal 1–99 %</th><th className="r">Deviation</th><th className="r">in σ</th></tr></thead>
          <tbody>
            {t.rows.map((r) => {
              const c = r[q]
              return (
                <tr key={r.bus} className={`${devClass(c)} ${sel === r.bus ? 'sel' : ''} ${e.result.named_buses.includes(r.bus) ? 'named' : ''}`} onClick={() => onSel(r.bus)}>
                  <td>B{r.bus}{e.result.named_buses.includes(r.bus) && <span className="tag-n" title="Named by GridDefense">N</span>}</td>
                  <td className="r mono">{c.observed.toFixed(meta.d)}</td>
                  <td className="r mono dim">{c.normal_mean.toFixed(meta.d)}</td>
                  <td className="r mono dim">{c.normal_p1.toFixed(meta.d)} – {c.normal_p99.toFixed(meta.d)}</td>
                  <td className="r mono">{c.deviation >= 0 ? '+' : ''}{c.deviation.toFixed(meta.d)}</td>
                  <td className="r mono">{c.deviation_sd == null ? '—' : `${c.deviation_sd >= 0 ? '+' : ''}${c.deviation_sd.toFixed(1)}`}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="dim small">Unit: {meta.unit}. Normal reference: {t.source}. Rows shaded when the reading is more than 2σ / 3σ from the normal mean.
        Loads vary by ±20 % in normal operation, so a large deviation alone is <b>not</b> evidence of an attack; this table is for reading the numbers, and no detector uses it.</p>
    </div>
  )
}

function Heatmap({ e, limit, votes2, sel, onSel }: { e: GridEvent; limit: number; votes2: number; sel: number | null; onSel: (b: number) => void }) {
  const votes = useMemo(() => e.result.buses.map((b) => b.votes), [e])
  return (
    <div>
      <div className="tbl-wrap">
        <table className="heat" aria-label="Physics evidence heatmap">
          <thead><tr><th>Bus</th>{CHECKS.map((c) => <th key={c} title={CHECK_TEXT[c].long}>{CHECK_TEXT[c].short}</th>)}<th>Votes</th></tr></thead>
          <tbody>
            {e.result.buses.map((b, i) => (
              <tr key={b.bus} className={sel === b.bus ? 'sel' : ''} onClick={() => onSel(b.bus)}>
                <th scope="row">B{b.bus}{b.named && <span className="tag-n" title="Named by GridDefense">N</span>}</th>
                {CHECKS.map((c) => {
                  const z = b.z[c] ?? 0
                  return <td key={c} style={{ background: zColor(z, limit) }} className={z > limit ? 'over' : ''}
                    title={`Bus ${b.bus} · ${CHECK_TEXT[c].long} · z = ${z.toFixed(2)}${z > limit ? ' (above limit)' : ''}`}>{z.toFixed(1)}</td>
                })}
                <td className={`mono votes ${b.physics_alarm ? 'hot' : ''}`}>{votes[i]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="heat-legend" aria-hidden>
        <span>z ≤ 0</span><i style={{ background: zColor(0, limit) }} /><i style={{ background: zColor(limit / 2, limit) }} /><i style={{ background: zColor(limit, limit) }} />
        <span>limit {limit}</span><i style={{ background: zColor(limit * 1.5, limit) }} /><i style={{ background: zColor(limit * 4, limit) }} /><span>far above</span>
      </div>
      <p className="dim small">Each cell is a z-score: how many standard deviations this check is from its value in normal training data. A cell above {limit} is one vote;
        a bus needs {votes2} votes to be flagged by the physics layer. Outlined cells are above the limit.</p>
    </div>
  )
}

export function VerdictView({ v }: { v: Verdict }) {
  const all = Array.from(new Set([...v.actual, ...v.predicted])).sort((a, b) => a - b)
  return (
    <div className="verdict">
      <div className={`verdict-head ${v.exact ? 'ok' : 'bad'}`}>
        <b>{v.exact ? 'Exact match' : 'Not an exact match'}</b>
        <span>{v.actual.length ? `attacked: ${list(v.actual)}` : 'no bus was attacked'} · named: {list(v.predicted)}</span>
      </div>
      {all.length > 0 && (
        <ul className="verdict-list">
          {all.map((b) => {
            const k = v.correct.includes(b) ? 'correct' : v.missed.includes(b) ? 'missed' : 'extra'
            return <li key={b} className={k}><b>B{b}</b><span>{k === 'correct' ? 'attacked and named — correct' : k === 'missed' ? 'attacked but NOT named — missed' : 'named but NOT attacked — extra'}</span></li>
          })}
        </ul>
      )}
      <dl className="kv3"><div><dt>Correct</dt><dd>{v.correct.length}</dd></div><div><dt>Missed</dt><dd>{v.missed.length}</dd></div><div><dt>Extra</dt><dd>{v.extra.length}</dd></div></dl>
      <p className="dim small">“Named” means the localiser named the bus <i>and</i> an alarm was raised. Exact match = the named set equals the attacked set — the same rule the notebook uses for its exact-localisation figure.</p>
    </div>
  )
}

function Compare({ e }: { e: GridEvent }) {
  const { events, pushEvent, status } = useStore()
  const [otherId, setOtherId] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const other = events.find((x) => x.id === otherId)
  const canTwin = (e.source === 'simulator' || e.source === 'scenario') && e.simulation && e.simulation.attack !== 'Normal'
  const limit = status?.model.physics.Z ?? 3.5
  const twin = async () => {
    if (!e.simulation) return
    setBusy(true); setErr('')
    try {
      const out = await api.simulate({ attack: 'Normal', buses: [], size_pct: 1, direction: 1, seed: e.simulation.seed })
      pushEvent(out.event, out.alarm); setOtherId(out.event.id)
    } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  const sameOp = other && other.simulation && e.simulation && other.simulation.seed === e.simulation.seed
  return (
    <div className="cmp">
      <div className="cmp-pick">
        <label>Compare with
          <select value={otherId ?? ''} onChange={(x) => setOtherId(x.target.value ? +x.target.value : null)}>
            <option value="">choose an event…</option>
            {events.filter((x) => x.id !== e.id).slice(0, 120).map((x) => (
              <option key={x.id} value={x.id}>#{x.id} · {fmtTime(x.time)} · {sourceLabel(x)} · {x.result.alarm ? 'ALARM' : 'normal'}</option>
            ))}
          </select>
        </label>
        {canTwin && <button className="btn sm" disabled={busy} onClick={twin}>{busy ? 'Scoring…' : 'Same snapshot without the attack'}</button>}
      </div>
      {canTwin && <p className="dim small">“Same snapshot without the attack” re-runs the simulator with the same seed, so the loads and meter noise are identical and only the injected attack differs.</p>}
      {err && <p className="err">{err}</p>}
      {other ? <CompareTable a={e} b={other} limit={limit} sameOp={!!sameOp} /> : <p className="dim">Pick a second event to see both side by side.</p>}
    </div>
  )
}

function CompareTable({ a, b, limit, sameOp }: { a: GridEvent; b: GridEvent; limit: number; sameOp: boolean }) {
  const rows = a.result.buses.map((x, i) => {
    const y = b.result.buses[i]
    const za = Math.max(...Object.values(x.z)), zb = Math.max(...Object.values(y.z))
    const ma = a.result.measurements, mb = b.result.measurements
    const dVm = ma && mb ? ma.Vm[i] - mb.Vm[i] : null
    const dVa = ma && mb ? ma.Va[i] - mb.Va[i] : null
    const changed = x.named !== y.named || x.physics_alarm !== y.physics_alarm
    return { bus: x.bus, x, y, za, zb, dVm, dVa, changed }
  })
  const head = (e: GridEvent) => (
    <div className={`cmp-card ${e.result.alarm ? 'alarm' : 'ok'}`}>
      <b>#{e.id} · {sourceLabel(e)}</b>
      <span>{e.result.alarm ? `ALARM · ${e.result.attack_type ?? 'type unclassified'}` : 'No alarm'} · fusion {e.result.fusion.score.toFixed(3)}</span>
      <span>named {list(e.result.named_buses)}{truthKnown(e) ? ` · truth: ${e.truth.type === 'Normal' ? 'no attack' : `${e.truth.type} on ${list(e.truth.buses)}`}` : ''}</span>
    </div>
  )
  return (
    <>
      <div className="cmp-cards">{head(a)}{head(b)}</div>
      <div className="tbl-wrap">
        <table className="tbl cmp-tbl">
          <thead>
            <tr><th rowSpan={2}>Bus</th><th colSpan={3} className="c">#{a.id}</th><th colSpan={3} className="c">#{b.id}</th><th colSpan={2} className="c">Difference A − B</th></tr>
            <tr><th>Named</th><th className="r">Votes</th><th className="r">max z</th><th>Named</th><th className="r">Votes</th><th className="r">max z</th><th className="r">Vm (p.u.)</th><th className="r">Va (°)</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.bus} className={r.changed ? 'changed' : ''}>
                <td>B{r.bus}{r.changed && <span className="tag-c" title="GridDefense's verdict for this bus differs">≠</span>}</td>
                <td>{r.x.named ? 'yes' : '—'}</td><td className="r mono">{r.x.votes}</td><td className={`r mono ${r.za > limit ? 'hot' : ''}`}>{r.za.toFixed(1)}</td>
                <td>{r.y.named ? 'yes' : '—'}</td><td className="r mono">{r.y.votes}</td><td className={`r mono ${r.zb > limit ? 'hot' : ''}`}>{r.zb.toFixed(1)}</td>
                <td className="r mono">{r.dVm == null ? '—' : r.dVm.toFixed(4)}</td><td className="r mono">{r.dVa == null ? '—' : r.dVa.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="dim small">Highlighted (≠) buses: GridDefense's verdict changed between the two snapshots, i.e. the bus is named in one and not the other,
        or its physics flag (≥ 2 votes) differs. {sameOp ? 'Both snapshots come from the same seed, so the Vm/Va differences are exactly the injected attack plus nothing else.'
          : 'The two snapshots have different loads and noise, so Vm/Va differences include normal variation, not only the attack.'}</p>
    </>
  )
}

export default function Inspector({ onClose }: { onClose: () => void }) {
  const { shown: e, status, selectedBus, selectBus } = useStore()
  const [tab, setTab] = useState<Tab>('why')
  if (!e) return null
  const limit = status?.model.physics.Z ?? 3.5
  const tabs: [Tab, string][] = [['why', 'Why'], ['meas', 'Measurements'], ['heat', 'Physics map'], ['loc', 'Localisation'], ['cmp', 'Compare']]
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal inspector" role="dialog" aria-label="Snapshot details" onClick={(x) => x.stopPropagation()}>
        <header>
          <div><b>Snapshot #{e.id}</b><span>{fmtTime(e.time)} · {sourceLabel(e)} · model bundle {e.bundle_id ?? 'not recorded'}</span></div>
          <button className="btn xs" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <nav className="tabs" role="tablist">
          {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}
        </nav>
        <div className="modal-body">
          {tab === 'why' && <Why e={e} />}
          {tab === 'meas' && <Measurements e={e} sel={selectedBus} onSel={selectBus} />}
          {tab === 'heat' && <Heatmap e={e} limit={limit} votes2={status?.model.physics.votes ?? 2} sel={selectedBus} onSel={selectBus} />}
          {tab === 'loc' && (e.verdict ? <VerdictView v={e.verdict} />
            : <p className="dim">The true attacked buses are not known for this snapshot ({sourceLabel(e).toLowerCase()}), so no verdict can be given. Verdicts are shown for the simulator, the scenarios and test-set replay.</p>)}
          {tab === 'cmp' && <Compare e={e} />}
        </div>
      </div>
    </div>
  )
}
