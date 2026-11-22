// Live detection centre: the decision on the shown snapshot and every piece of evidence.
import { useStore } from '../store'
import { CHECK_TEXT, decisionText, fmtTime, list, pct, sourceLabel, truthKnown } from '../text'
import Panel from './Panel'

export default function Detection() {
  const { shown: e, status, showTruth, selectBus, selectedBus } = useStore()
  if (!e) return <Panel title="Detection centre"><p className="dim">Waiting for the first snapshot…</p></Panel>
  const r = e.result
  const f = r.fusion
  const w = f.weights
  const det = [
    { k: 'Autoencoder', sub: 'pattern anomaly', score: r.detectors.ae.score, part: f.parts.ae, wt: w.ae, flag: r.detectors.ae.flag, cls: 'ae' },
    { k: 'Random Forest', sub: 'attack classifier', score: r.detectors.rf.score, part: f.parts.rf, wt: w.rf, flag: r.detectors.rf.flag, cls: 'rf' },
    { k: 'Physics checks', sub: 'power-flow laws', score: r.detectors.physics.score, part: f.parts.physics, wt: w.physics, flag: r.detectors.physics.flag, cls: 'ph' },
  ]
  const evidence = r.buses.filter((b) => b.votes > 0).sort((a, b) => b.votes - a.votes || a.bus - b.bus)
  const suspects = r.buses.filter((b) => b.loc_probability >= 0.05).sort((a, b) => b.loc_probability - a.loc_probability).slice(0, 6)
  const votesNeeded = status?.model.physics.votes ?? 2
  return (
    <Panel title="Detection centre" meta={`#${e.id} · ${fmtTime(e.time)} · ${sourceLabel(e)}`}>
      <div className={`state-block ${r.alarm ? 'alarm' : 'ok'}`}>
        <span className="lamp" />
        <div>
          <b>{r.alarm ? 'ALARM' : 'NORMAL'}</b>
          <span>{decisionText(r)}{r.alarm && r.named_buses.length ? ` · ${list(r.named_buses)}` : ''}</span>
        </div>
      </div>

      {r.explanation && <p className={`why-mini ${r.explanation.borderline ? 'warn' : ''}`}>{r.explanation.summary}</p>}
      {e.verdict && r.alarm && (
        <p className={`verdict-mini ${e.verdict.exact ? 'ok' : 'bad'}`}>
          Localisation vs ground truth: <b>{e.verdict.exact ? 'exact match' : 'not exact'}</b>
          {e.verdict.missed.length ? ` · missed ${list(e.verdict.missed)}` : ''}{e.verdict.extra.length ? ` · extra ${list(e.verdict.extra)}` : ''}
        </p>
      )}

      <section className="sub">
        <h3>Fusion score</h3>
        <div className="fusion">
          <span className={`big mono ${r.alarm ? 'red' : ''}`}>{f.score.toFixed(3)}</span>
          <span className="dim mono">threshold {f.threshold.toFixed(2)}</span>
        </div>
        <div className="stack" role="img" aria-label={`Fusion ${f.score.toFixed(2)}, threshold ${f.threshold.toFixed(2)}`}>
          <i className="ae" style={{ width: pct(f.parts.ae, 2) }} />
          <i className="rf" style={{ width: pct(f.parts.rf, 2) }} />
          <i className="ph" style={{ width: pct(f.parts.physics, 2) }} />
          <em style={{ left: pct(f.threshold, 2) }} />
        </div>
        <p className="formula mono">{w.ae.toFixed(2)}·AE + {w.rf.toFixed(2)}·RF + {w.physics.toFixed(2)}·Phys</p>
      </section>

      <section className="sub">
        <h3>Detectors</h3>
        <table className="tbl">
          <thead><tr><th>Layer</th><th className="r">Score</th><th className="r">Weighted</th><th className="r">Flag</th></tr></thead>
          <tbody>
            {det.map((d) => (
              <tr key={d.k}>
                <td><i className={`sw ${d.cls}`} />{d.k}<small>{d.sub}</small></td>
                <td className="r mono">{d.score.toFixed(3)}</td>
                <td className="r mono">{d.part.toFixed(3)}</td>
                <td className="r"><span className={`flag ${d.flag ? 'on' : ''}`}>{d.flag ? 'YES' : 'no'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="sub">
        <h3>Predicted attack type</h3>
        <div className="probs">
          {Object.entries(r.type_probabilities).map(([k, v]) => (
            <div key={k} className={k === (r.attack_type ?? 'Normal') && r.alarm ? 'top' : ''}>
              <span>{k}</span><i style={{ width: pct(v) }} /><b className="mono">{pct(v)}</b>
            </div>
          ))}
        </div>
      </section>

      <section className="sub">
        <h3>Suspected buses <small className="dim">localiser probability</small></h3>
        {suspects.length ? (
          <div className="chips">
            {suspects.map((b) => (
              <button key={b.bus} className={`chip ${b.named ? 'named' : ''} ${selectedBus === b.bus ? 'sel' : ''}`} onClick={() => selectBus(b.bus)}>
                B{b.bus} <span className="mono">{pct(b.loc_probability)}</span>
              </button>
            ))}
          </div>
        ) : <p className="dim">None above 5%.</p>}
      </section>

      <section className="sub">
        <h3>Physics evidence <small className="dim">vote when z &gt; {status?.model.physics.Z ?? 3.5}; alarm needs {votesNeeded}</small></h3>
        {evidence.length ? (
          <ul className="evidence">
            {evidence.slice(0, 7).map((b) => (
              <li key={b.bus} className={b.physics_alarm ? 'hot' : ''}>
                <button className="link" onClick={() => selectBus(b.bus)}><b>B{b.bus}</b></button>
                <span className="votes mono">{b.votes} vote{b.votes > 1 ? 's' : ''}</span>
                <span className="checks">{b.checks_failed.map((c) => <em key={c} title={CHECK_TEXT[c]?.long}>{CHECK_TEXT[c]?.short ?? c}</em>)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="dim">No physics check exceeded its limit.</p>}
      </section>

      {showTruth && !truthKnown(e) && <p className="truth-line"><span>Ground truth</span> unknown for an uploaded snapshot.</p>}
      {showTruth && truthKnown(e) && (
        <p className="truth-line">
          <span>Ground truth</span> (stored separately, never given to the models):{' '}
          {e.truth.type === 'Normal' ? 'no attack' : `${e.truth.type} on ${list(e.truth.buses)}`}
          {e.simulation && e.truth.type !== 'Normal' ? `, ${e.simulation.size_pct}%` : ''}
        </p>
      )}
    </Panel>
  )
}
