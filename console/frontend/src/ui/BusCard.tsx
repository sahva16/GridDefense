// Bus-level inspection: everything GridDefense computed for one bus in the shown snapshot.
import { useStore } from '../store'
import { busDef, branchName, neighbours } from '../grid'
import { CHECK_TEXT, pct, truthKnown } from '../text'

export default function BusCard({ onDetails }: { onDetails: () => void }) {
  const { shown: e, selectedBus: b, selectBus, status, showTruth } = useStore()
  if (!b || !e) return null
  const d = busDef(b)
  const info = e.result.buses[b - 1]
  const m = e.result.measurements
  const Z = status?.model.physics.Z ?? 3.5
  const flows = e.result.line_flow_mva
  const truth = e.truth.buses.includes(b)
  const known = truthKnown(e)
  const mt = e.result.measurement_table?.rows[b - 1]
  return (
    <aside className="bus-card" aria-label={`Bus ${b} inspection`}>
      <header>
        <div><b>Bus {b}</b><span>{d.name} · {d.kv} kV</span></div>
        <button className="btn xs" onClick={() => selectBus(null)} aria-label="Close">✕</button>
      </header>
      <div className={`bus-state ${info.named ? 'alarm' : ''}`}>
        {info.named ? 'Named by GridDefense as attacked' : 'Not named'}
        {showTruth && (known ? <span className={truth ? 'truth' : 'dim'}> · ground truth: {truth ? 'attacked' : 'clean'}</span>
          : <span className="dim"> · ground truth unknown</span>)}
      </div>
      {mt ? (
        <table className="tbl tight">
          <thead><tr><th>Reading</th><th className="r">Observed</th><th className="r">Normal</th><th className="r">σ</th></tr></thead>
          <tbody>
            {([['Vm', 'Vm (pu)', 4], ['Va', 'Va (°)', 3], ['Pd', 'P load (MW)', 2], ['Qd', 'Q load (MVAr)', 2]] as const).map(([k, l, d]) => {
              const c = mt[k]
              const sd = c.deviation_sd
              return <tr key={k} className={sd != null && Math.abs(sd) >= 3 ? 'hot' : ''}><td>{l}</td><td className="r mono">{c.observed.toFixed(d)}</td>
                <td className="r mono dim">{c.normal_mean.toFixed(d)}</td><td className="r mono">{sd == null ? '—' : sd.toFixed(1)}</td></tr>
            })}
          </tbody>
        </table>
      ) : m && (
        <dl className="meas mono">
          <div><dt>Vm</dt><dd>{m.Vm[b - 1].toFixed(4)} pu</dd></div>
          <div><dt>Va</dt><dd>{m.Va[b - 1].toFixed(3)}°</dd></div>
          <div><dt>P load</dt><dd>{m.Pd[b - 1].toFixed(2)} MW</dd></div>
          <div><dt>Q load</dt><dd>{m.Qd[b - 1].toFixed(2)} MVAr</dd></div>
        </dl>
      )}
      <table className="tbl tight">
        <thead><tr><th>Physics check</th><th className="r">z</th><th className="r">Vote</th></tr></thead>
        <tbody>
          {Object.entries(info.z).map(([k, z]) => (
            <tr key={k} className={z > Z ? 'hot' : ''} title={CHECK_TEXT[k]?.long}>
              <td>{CHECK_TEXT[k]?.short ?? k}</td>
              <td className="r mono">{z.toFixed(2)}</td>
              <td className="r">{z > Z ? <span className="flag on">YES</span> : <span className="flag">no</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="kv">
        <div><dt>Votes</dt><dd className="mono">{info.votes} / {status?.model.physics.votes ?? 2} needed</dd></div>
        <div><dt>Localiser</dt><dd className="mono">{pct(info.loc_probability)} <small className="dim">(names at ≥ {pct(status?.model.loc_threshold ?? 0.5)})</small></dd></div>
        <div><dt>AE error (this bus)</dt><dd className="mono">{info.ae_error.toFixed(4)}</dd></div>
      </dl>
      <button className="btn xs" onClick={onDetails}>All buses · measurements, physics map, verdict</button>
      {flows && (
        <p className="nb dim">Lines: {neighbours(b).map((n) => `${branchName(n.line)} ${flows[n.line].toFixed(1)} MVA`).join(' · ')}</p>
      )}
    </aside>
  )
}
