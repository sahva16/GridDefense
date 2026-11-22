// Attack simulator: prepared, reproducible scenarios (fixed seeds) plus a custom attack.
import { useState } from 'react'
import { EXPORT_URL } from '../api'
import { useStore } from '../store'
import { DEMO } from '../demo'
import { list } from '../text'
import Panel from './Panel'

export default function Scenarios() {
  const { scenarios, runScenario, runCustom, reset, busy, error, events, pinnedId, scoreSnapshot } = useStore()
  const [mode, setMode] = useState<'scen' | 'custom' | 'upload'>('scen')
  const custom = mode === 'custom'
  const [type, setType] = useState('Additive')
  const [buses, setBuses] = useState<number[]>([4])
  const [size, setSize] = useState(2)
  const [dir, setDir] = useState(1)
  const shown = pinnedId != null ? events.find((e) => e.id === pinnedId) : undefined
  const toggle = (b: number) => setBuses((s) => (s.includes(b) ? s.filter((x) => x !== b) : s.length >= 3 ? [...s.slice(1), b] : [...s, b].sort((x, y) => x - y)))
  return (
    <Panel title="Attack simulator"
      actions={<>
        <div className="seg sm" role="tablist" aria-label="Simulator mode">
          <button className={mode === 'scen' ? 'on' : ''} onClick={() => setMode('scen')}>Scenarios</button>
          <button className={mode === 'custom' ? 'on' : ''} onClick={() => setMode('custom')}>Custom</button>
          {!DEMO && <button className={mode === 'upload' ? 'on' : ''} onClick={() => setMode('upload')}>Upload</button>}
        </div>
        <button className="btn sm warn" onClick={() => void reset()} disabled={busy}>Reset</button>
      </>}>
      {mode === 'upload' ? <Upload onScore={scoreSnapshot} busy={busy} /> : !custom ? (
        <ul className="scenarios scroll">
          {scenarios.map((s) => (
            <li key={s.id} className={shown?.scenario?.id === s.id ? 'last' : ''}>
              <span className="sid mono">{s.id}</span>
              <div>
                <b>{s.title}</b>
                <small>{s.attack === 'Normal' ? 'No attack' : `${s.attack} · ${s.direction > 0 ? '+' : '−'}${s.size_pct}% · ${list(s.buses)}`} · seed {s.seed}</small>
              </div>
              <button className="btn sm run" disabled={busy} onClick={() => void runScenario(s)}>Run</button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="custom">
          {DEMO && <p className="dim small">Preview: replays recorded runs for one bus at a time.</p>}
          <label>Type
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option>Additive</option><option>Scaling</option><option>Coordinated</option>
            </select>
          </label>
          <div className="bus-pick" role="group" aria-label="Target buses">
            {Array.from({ length: 13 }, (_, i) => i + 2).map((b) => (
              <button key={b} className={buses.includes(b) ? 'on' : ''} onClick={() => (DEMO ? setBuses([b]) : toggle(b))}>{b}</button>
            ))}
          </div>
          <label>Size <span className="mono">{size.toFixed(2)}%</span>
            <input type="range" min={0.25} max={3} step={0.25} value={size} onChange={(e) => setSize(+e.target.value)} />
          </label>
          <div className="seg">
            <button className={dir > 0 ? 'on' : ''} onClick={() => setDir(1)}>+ bias</button>
            <button className={dir < 0 ? 'on' : ''} onClick={() => setDir(-1)}>− bias</button>
          </div>
          <button className="btn run wide" disabled={busy || !buses.length} onClick={() => void runCustom({ attack: type, buses, size_pct: size, direction: dir })}>
            Inject and score
          </button>
        </div>
      )}
      <footer className="sim-foot">
        {error && mode !== 'upload' ? <span className="red">{error}</span> : <span className="dim">Same scenario + seed → same result.</span>}
        {!DEMO && <a className="link" href={EXPORT_URL} download>Export event log (CSV)</a>}
      </footer>
    </Panel>
  )
}

/** Parse one CSV row (header + first data line). No quoting needed: the snapshot is numbers only. */
function parseCsv(text: string): Record<string, string> {
  const lines = text.split(/\r?\n/).filter((l) => l.trim())
  if (lines.length < 2) throw new Error('The CSV needs a header line and at least one data line.')
  const head = lines[0].split(',').map((h) => h.trim())
  const vals = lines[1].split(',').map((v) => v.trim())
  if (vals.length !== head.length) throw new Error(`Header has ${head.length} columns but the first row has ${vals.length}.`)
  return Object.fromEntries(head.map((h, i) => [h, vals[i]]))
}

function Upload({ onScore, busy }: { onScore: (s: Record<string, unknown>) => Promise<void>; busy: boolean }) {
  const [msg, setMsg] = useState('')
  const [ok, setOk] = useState(false)
  const pick = async (f: File | undefined) => {
    if (!f) return
    setMsg(''); setOk(false)
    try {
      const row = parseCsv(await f.text())
      await onScore(row)            // values are sent as text; the backend checks every one is a finite number
      setOk(true); setMsg(`Scored the first row of ${f.name}.`)
    } catch (e) { setMsg((e as Error).message) }
  }
  return (
    <div className="custom upload">
      <p className="small">Score your own snapshot: a CSV with a header row and one data row containing the 84 measurement columns
        <span className="mono"> Vm_1…14, Va_1…14, Pd_1…14, Qd_1…14, Pg_ref_1…14, Qg_ref_1…14</span>. Column order does not matter; other columns are ignored.</p>
      <label className="btn run wide file">{busy ? 'Scoring…' : 'Choose CSV file'}
        <input type="file" accept=".csv,text/csv" disabled={busy} onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = '' }} />
      </label>
      <p className="dim small">Every value is checked first (present, a number, finite, inside wide sanity limits). An invalid file is rejected with the reason and nothing is scored.
        Ground truth is unknown for an upload, so no localisation verdict is shown. <a className="link" href="/api/sample.csv">Sample file</a> (one test-set row).</p>
      {msg && <p className={ok ? 'ok-line' : 'err'}>{msg}</p>}
    </div>
  )
}
