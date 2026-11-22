// Model & data provenance: which models are loaded, where they came from, and the proof that
// the app reproduces the notebook. "Verified" appears only when every comparison passed.
import type { Status } from '../api'

const CHECK_LABEL: Record<string, string> = {
  alarm: 'Alarm decision (yes/no)', named_buses: 'Named buses (all 14)', attack_type: 'Predicted attack type',
  fusion_score: 'Fusion score', ae_score: 'Autoencoder score', rf_score: 'Random Forest score', physics_score: 'Physics score',
}

export function ProvenanceBadge({ status, onClick }: { status: Status; onClick: () => void }) {
  const p = status.provenance
  const cls = p.status === 'verified' ? 'ok' : p.status === 'development' ? 'warn' : 'bad'
  return <button className={`badge ${cls} as-btn`} onClick={onClick} title="Model and data provenance">{p.label} · {p.bundle_id}</button>
}

export function ProvenanceBanner({ status, onClick }: { status: Status; onClick: () => void }) {
  const p = status.provenance
  if (p.status === 'verified') return null
  return (
    <div className={`prov-banner ${p.status}`} role="alert">
      <span>{p.status === 'development'
        ? <><b>DEVELOPMENT MODELS.</b> These were trained by the repo package for testing the dashboard. They are not the notebook's models, and nothing shown here is a notebook result.</>
        : <><b>MODELS NOT VERIFIED.</b> {p.reasons[0]}{p.reasons.length > 1 ? ` (+${p.reasons.length - 1} more)` : ''}. Do not present these results as the notebook's.</>}</span>
      <button className="btn xs" onClick={onClick}>Details</button>
    </div>
  )
}

const short = (h?: string | null) => (h ? `${h.slice(0, 12)}…` : '—')

export default function Verification({ status, onClose }: { status: Status; onClose: () => void }) {
  const c = status.self_check, p = status.provenance, m = status.model
  const vers: [string, string | null | undefined, string | null | undefined][] = [
    ['scikit-learn', m.sklearn_bundle, m.sklearn_app], ['numpy', m.numpy_bundle, m.numpy_app],
    ['pandas', m.manifest_versions?.pandas, null], ['tensorflow (export only)', m.manifest_versions?.tensorflow, null],
  ]
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="modal verif" role="dialog" aria-label="Model and data provenance" onClick={(e) => e.stopPropagation()}>
        <header>
          <div><b>Model &amp; data provenance</b><span>bundle {p.bundle_id} · exported {m.exported_at ?? 'unknown'}</span></div>
          <button className="btn xs" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="modal-body">
          <div className={`prov-state ${p.status}`}><b>{p.label}</b>
            <span>{p.status === 'verified' ? 'Exported from the notebook, unchanged since export, and every check below passed.'
              : p.status === 'development' ? 'Every check passed, but against a reference made by the repo package — not the notebook.'
                : 'At least one condition for “verified” failed:'}</span>
            {p.reasons.length > 0 && <ul>{p.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
          </div>

          <h3>Reproduction of the notebook (Section 10, all test snapshots)</h3>
          <table className="tbl">
            <thead><tr><th>Compared</th><th className="r">Identical</th><th className="r">Result</th></tr></thead>
            <tbody>{Object.entries(c.checks).map(([k, r]) => (
              <tr key={k}><td>{CHECK_LABEL[k] ?? k}</td><td className="r mono">{r.match.toLocaleString()} / {r.total.toLocaleString()}</td>
                <td className="r"><span className={`flag ${r.match === r.total ? 'pass' : 'on'}`}>{r.match === r.total ? 'PASS' : 'FAIL'}</span></td></tr>))}
            </tbody>
          </table>
          <p className="dim small">Reference: the notebook's own <span className="mono">results/alarm_log.csv</span>, attached to every test snapshot by the export cell.
            Rule: {c.tolerance}. Largest fusion difference {c.fusion_max_abs_diff.toExponential(2)}. Alarms: app {c.app_alarms.toLocaleString()}, notebook {c.notebook_alarms.toLocaleString()}.
            Checked at start-up {c.checked_at} ({c.seconds} s).</p>
          {Object.keys(c.mismatches).length > 0 && <p className="err">First mismatching snapshots: {Object.entries(c.mismatches).map(([k, v]) => `${k}: ${v.join(', ')}`).join(' · ')}</p>}

          <h3>Integrity</h3>
          <dl className="kv2">
            <div><dt>Manifest</dt><dd>{m.integrity.manifest_present ? 'present' : 'missing'}</dd></div>
            <div><dt>Model file SHA-256</dt><dd className="mono">{short(m.model_sha256)} {m.integrity.model_sha256_ok === undefined ? '' : m.integrity.model_sha256_ok ? '✓ matches' : '✗ changed'}</dd></div>
            <div><dt>Test-set file</dt><dd>{m.integrity.test_sha256_ok === undefined ? '—' : m.integrity.test_sha256_ok ? '✓ matches manifest' : '✗ changed'}</dd></div>
            {m.colab_checks && <div><dt>Checks run in Colab</dt><dd className="mono small">AE numpy vs Keras {Number(m.colab_checks.ae_numpy_vs_keras_max_diff).toExponential(1)} · AE rows off {m.colab_checks.ae_score_rows_off} · RF rows off {m.colab_checks.rf_score_rows_off}</dd></div>}
          </dl>

          <h3>Versions</h3>
          <table className="tbl"><thead><tr><th>Library</th><th>Export (Colab)</th><th>This app</th></tr></thead>
            <tbody>{vers.map(([n, a, b]) => <tr key={n} className={a && b && a !== b ? 'hot' : ''}><td>{n}</td><td className="mono">{a ?? '—'}</td><td className="mono">{b ?? '—'}</td></tr>)}</tbody>
          </table>

          <h3>Configuration</h3>
          <dl className="kv2">
            <div><dt>Features</dt><dd>AE {m.features.ae} · RF {m.features.rf} · localiser {m.features.localiser}</dd></div>
            <div><dt>Fusion</dt><dd className="mono">{m.fusion.w_ae.toFixed(2)}·AE + {m.fusion.w_rf.toFixed(2)}·RF + {m.fusion.w_phys.toFixed(2)}·Phys ≥ {m.fusion.threshold.toFixed(2)}</dd></div>
            <div><dt>AE score bounds</dt><dd className="mono">{m.fusion_bounds.ae_lo.toFixed(6)} … {m.fusion_bounds.ae_hi.toFixed(6)}</dd></div>
            <div><dt>AE threshold</dt><dd className="mono">{m.ae_threshold.toFixed(6)}</dd></div>
            <div><dt>Physics</dt><dd className="mono">z &gt; {m.physics.Z}, ≥ {m.physics.votes} of {m.physics.checks.length} checks</dd></div>
            <div><dt>Localiser threshold</dt><dd className="mono">{m.loc_threshold.toFixed(2)}</dd></div>
          </dl>
          <details><summary>Feature lists ({m.features.rf} RF features; AE uses the first {m.features.ae})</summary><p className="mono small wrap">{m.features.rf_cols.join(', ')}</p></details>
          {m.source_md5 && <details><summary>MD5 of the notebook files used for export</summary>
            <table className="tbl"><tbody>{Object.entries(m.source_md5).map(([f, h]) => <tr key={f}><td className="mono small">{f}</td><td className="mono small">{h}</td></tr>)}</tbody></table></details>}
          <p className="dim small">Every logged event stores this bundle ID, so the event log and CSV export always show which models made each decision.</p>
        </div>
      </div>
    </div>
  )
}
