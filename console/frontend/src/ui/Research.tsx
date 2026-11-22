// Research results — ONLY the notebook's saved result files, copied unchanged into the bundle.
// Nothing here is computed by the console, and it is kept apart from the live console on purpose.
import { useEffect, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Status } from '../api'
import { api } from '../api'

type FileEntry = {
  file: string; md5: string; source_md5: string | null; kind: 'csv' | 'json'
  rows_total?: number; columns?: string[]; rows?: Record<string, unknown>[] | null; data?: unknown
}
type Perf = { provenance: Status['provenance']; bundle_id: string; exported_at: string | null; files: Record<string, FileEntry> }

// Curated sections: the stem of the saved file, a heading, and one line saying what it is.
// Wording describes the file only; every number on the page comes from the file itself.
const SECTIONS: { id: string; title: string; files: string[]; about: string }[] = [
  { id: 'det', title: 'Detectors and fusion', files: ['final_summary_seed20261014'],
    about: 'Independent test set (seed 20261014): each detector alone, 2-of-3 voting and the weighted fusion. From final_summary_seed20261014.json.' },
  { id: 'cmp', title: 'Model comparison', files: ['model_comparison', 'model_comparison_vs_rf', 'small_attacks_model_comparison', 'small_attacks_vs_rf'],
    about: 'Other learning models compared with the Random Forest, as saved by the notebook.' },
  { id: 'loc', title: 'Localisation per bus', files: ['localisation_per_bus', 'localisation_bus_difficulty', 'localisation_by_number_of_buses'],
    about: 'How well each bus is named on the independent test set.' },
  { id: 'size', title: 'Attack size', files: ['attack_size_sensitivity'],
    about: 'Detection as the attack gets smaller or larger — the trained system on new data, nothing retrained.' },
  { id: 'stealth', title: 'Stealth', files: ['stealthy_attack_stress_test'],
    about: 'Attacks built to look more and more consistent with the physics.' },
  { id: 'gps', title: 'GPS spoofing', files: ['gps_spoofing_default', 'gps_spoofing_budget', 'gps_spoofing_localisation'],
    about: 'Angle-only attacks that imitate GPS time spoofing of PMUs.' },
]
// Result files the CURRENT notebook writes (checked against the notebook source, 8 Nov 2026).
// Anything else found in the results folder is an older file left on Drive by an earlier run.
const CURRENT = new Set(['alarm_log', 'attack_size_sensitivity', 'classical_bad_data_baseline', 'devtest_evaluation', 'devtest_evaluation_with_loc',
  'external_partial_physics', 'fi_ae_features', 'fi_rf_families', 'fi_rf_permutation', 'final_results_seed20261014', 'final_summary_seed20261014',
  'fusion_rf_vs_xgboost_bootstrap', 'fusion_rf_vs_xgboost_small_attacks', 'fusion_rf_vs_xgboost_test', 'generalisation_known_test',
  'generalisation_new_stealth', 'generalisation_unseen_type', 'gps_spoofing_budget', 'gps_spoofing_default', 'gps_spoofing_localisation',
  'griddefense_plus_classical', 'localisation_bus_difficulty', 'localisation_by_number_of_buses', 'localisation_per_bus', 'model_comparison',
  'model_comparison_vs_rf', 'physics_ablation', 'physics_ablation_differences', 'physics_ablation_localisation', 'physics_ablation_matched_fpr',
  'physics_ablation_per_bus', 'physics_ablation_repeatability', 'repeatability_e2e_per_seed', 'repeatability_e2e_summary',
  'repeatability_localiser_per_seed', 'repeatability_per_bus_ks', 'sensitivity_fusion_weights', 'sensitivity_physics_z',
  'small_attacks_model_comparison', 'small_attacks_vs_rf', 'stealthy_attack_stress_test', 'unseen_attack_type'])
const DET_ORDER = ['AE alone', 'RF alone', 'Physics alone', '2-of-3 voting', 'Weighted fusion']

const fmt = (v: unknown) => (typeof v === 'number' ? (Number.isInteger(v) ? v.toLocaleString() : Math.abs(v) < 1e-3 && v !== 0 ? v.toExponential(2) : v.toFixed(Math.abs(v) < 1 ? 4 : Math.abs(v) >= 100 ? 1 : 3)) : v == null ? '—' : String(v))

function Provenance({ f }: { f: FileEntry }) {
  const ok = f.source_md5 ? f.source_md5 === f.md5 : null
  return <p className="file-prov mono small">{f.file} · md5 {f.md5.slice(0, 10)}… {ok == null ? '(no Drive fingerprint in manifest)' : ok ? '✓ identical to the Drive file' : '✗ differs from the Drive file'}</p>
}

function CsvTable({ f }: { f: FileEntry }) {
  if (!f.rows) return <p className="dim small">{f.file}: {f.rows_total?.toLocaleString()} rows — too large to show here.</p>
  const numeric = (c: string) => f.rows!.some((r) => typeof r[c] === 'number')
  return (
    <div className="tbl-wrap"><table className="tbl research-tbl">
      <thead><tr>{f.columns!.map((c) => <th key={c} className={numeric(c) ? 'r' : ''}>{c.startsWith('Unnamed') ? '' : c}</th>)}</tr></thead>
      <tbody>{f.rows.map((r, i) => <tr key={i}>{f.columns!.map((c) => <td key={c} className={typeof r[c] === 'number' ? 'r mono' : ''}>{fmt(r[c])}</td>)}</tr>)}</tbody>
    </table></div>
  )
}

function DetectorTable({ data }: { data: Record<string, Record<string, unknown>> }) {
  const rows = DET_ORDER.filter((k) => data[k])
  if (!rows.length) return null
  const ci = (x: unknown) => (Array.isArray(x) ? `[${(x[0] as number).toFixed(2)}–${(x[1] as number).toFixed(2)}]` : '')
  return (
    <div className="tbl-wrap"><table className="tbl research-tbl">
      <thead><tr><th>Detector</th><th className="r">Detection %</th><th className="r">95 % CI</th><th className="r">False alarms %</th><th className="r">95 % CI</th><th className="r">F1</th><th className="r">ROC-AUC</th><th className="r">TN / FP / FN / TP</th></tr></thead>
      <tbody>{rows.map((k) => {
        const d = data[k]
        return <tr key={k} className={k === 'Weighted fusion' ? 'strong' : ''}><td>{k}</td>
          <td className="r mono">{(d.detection as number).toFixed(2)}</td><td className="r mono dim">{ci(d.detection_95ci)}</td>
          <td className="r mono">{(d.false_alarm as number).toFixed(2)}</td><td className="r mono dim">{ci(d.false_alarm_95ci)}</td>
          <td className="r mono">{d.f1 == null ? '—' : (d.f1 as number).toFixed(4)}</td>
          <td className="r mono">{d.roc_auc == null ? '—' : (d.roc_auc as number).toFixed(4)}</td>
          <td className="r mono dim">{Array.isArray(d.TN_FP_FN_TP) ? (d.TN_FP_FN_TP as number[]).map((n) => n.toLocaleString()).join(' / ') : '—'}</td></tr>
      })}</tbody>
    </table></div>
  )
}

function SizeChart({ f, x, xLabel }: { f: FileEntry; x: string; xLabel: string }) {
  const rows = f.rows ?? []
  if (!rows.length || !f.columns?.includes(x) || !f.columns.includes('detector') || !f.columns.includes('detection')) return null
  const sizes = Array.from(new Set(rows.map((r) => r[x] as number))).sort((a, b) => a - b)
  const dets = DET_ORDER.filter((d) => rows.some((r) => r.detector === d))
  const data = sizes.map((s) => Object.fromEntries([['size', s], ...dets.map((d) => [d, rows.find((r) => r[x] === s && r.detector === d)?.detection ?? null])]))
  const COL = ['var(--ae)', 'var(--rf)', 'var(--ph)', 'var(--ink-3)', 'var(--cyan)']
  return (
    <div className="research-chart" role="img" aria-label={`Detection versus ${xLabel}`}>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 18, left: 0 }}>
          <CartesianGrid stroke="#16242e" vertical={false} />
          <XAxis dataKey="size" tick={{ fill: '#9fb2bd', fontSize: 11 }} label={{ value: xLabel, fill: '#6f8794', fontSize: 11, position: 'insideBottom', dy: 8 }} />
          <YAxis domain={[0, 100]} tick={{ fill: '#9fb2bd', fontSize: 11 }} unit="%" />
          <Tooltip contentStyle={{ background: '#0b141b', border: '1px solid #22323e', fontSize: 12 }} formatter={(v) => `${Number(v).toFixed(2)}%`} labelFormatter={(l) => `${xLabel}: ${l}`} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {dets.map((d, i) => <Line key={d} dataKey={d} stroke={COL[i]} strokeWidth={d === 'Weighted fusion' ? 2.5 : 1.5} dot={{ r: 2.5 }} isAnimationActive={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function Research({ status, onBack }: { status: Status | null; onBack: () => void }) {
  const [perf, setPerf] = useState<Perf | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.performance().then((p) => setPerf(p as unknown as Perf)).catch((e) => setErr((e as Error).message)) }, [])
  const files = perf?.files ?? {}
  const used = new Set(SECTIONS.flatMap((s) => s.files))
  const others = Object.keys(files).filter((k) => !used.has(k) && CURRENT.has(k))
  const older = Object.keys(files).filter((k) => !CURRENT.has(k))
  const prov = perf?.provenance ?? status?.provenance
  return (
    <div className="research">
      <header className="research-top">
        <button className="btn sm" onClick={onBack}>← Back to console</button>
        <div><h1>Research results</h1>
          <p className="research-tag">Notebook results · saved files, not live. Nothing on this page is computed by the console.</p></div>
        {prov && <span className={`badge ${prov.status === 'verified' ? 'ok' : prov.status === 'development' ? 'warn' : 'bad'}`}>{prov.label} · {prov.bundle_id}</span>}
      </header>
      {prov && prov.status !== 'verified' && <div className={`prov-banner ${prov.status} static`}>
        {prov.status === 'development' ? 'Development bundle: these files may not be the notebook\'s result files.' : 'Bundle not verified — check the provenance panel before using these numbers.'}</div>}
      {err && <p className="err">{err}</p>}
      <nav className="research-nav">{SECTIONS.map((s) => <a key={s.id} href={`#research`} onClick={(e) => { e.preventDefault(); document.getElementById(`r-${s.id}`)?.scrollIntoView({ behavior: 'smooth' }) }}>{s.title}</a>)}</nav>
      {SECTIONS.map((s) => {
        const present = s.files.filter((f) => files[f])
        return (
          <section key={s.id} id={`r-${s.id}`} className="research-sec">
            <h2>{s.title}</h2>
            <p className="dim">{s.about}</p>
            {!present.length && <p className="missing">Not in this bundle: {s.files.map((f) => `${f}.${f.startsWith('final_summary') ? 'json' : 'csv'}`).join(', ')}. Run that notebook section, then re-export.</p>}
            {present.map((k) => {
              const f = files[k]
              return (
                <div key={k} className="research-file">
                  <p className="file-name mono small">{f.file}</p>
                  {f.kind === 'json' && k.startsWith('final_summary') ? <DetectorTable data={f.data as Record<string, Record<string, unknown>>} />
                    : <>{k === 'attack_size_sensitivity' && <SizeChart f={f} x="size_pct" xLabel="attack size (% of true value)" />}
                      {k === 'gps_spoofing_default' && <SizeChart f={f} x="offset_deg" xLabel="angle offset (degrees)" />}<CsvTable f={f} /></>}
                  <Provenance f={f} />
                </div>
              )
            })}
          </section>
        )
      })}
      {others.length > 0 && (
        <section className="research-sec">
          <h2>All other saved result files</h2>
          <p className="dim">Numbers in these tables are rounded for display (4 decimals below 1, otherwise 3); the files themselves are unchanged.</p>
          {others.map((k) => (
            <details key={k} className="research-file"><summary>{files[k].file}{files[k].rows_total != null ? ` · ${files[k].rows_total} rows` : ''}</summary>
              {files[k].kind === 'csv' ? <CsvTable f={files[k]} /> : <pre className="mono small wrap">{JSON.stringify(files[k].data, null, 2).slice(0, 4000)}</pre>}
              <Provenance f={files[k]} />
            </details>
          ))}
        </section>
      )}
      {older.length > 0 && (
        <section className="research-sec">
          <h2>Older files found in the results folder</h2>
          <p className="missing-warn">These files are in the Drive results folder but the current notebook does not write them, so they come from an earlier run. They are listed only so nothing is hidden — do not quote them as current results.</p>
          {older.map((k) => (
            <details key={k} className="research-file old"><summary>{files[k].file}{files[k].rows_total != null ? ` · ${files[k].rows_total} rows` : ''}</summary>
              {files[k].kind === 'csv' ? <CsvTable f={files[k]} /> : <pre className="mono small wrap">{JSON.stringify(files[k].data, null, 2).slice(0, 4000)}</pre>}
              <Provenance f={files[k]} />
            </details>
          ))}
        </section>
      )}
    </div>
  )
}
