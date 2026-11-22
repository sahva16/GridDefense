import { useEffect, useMemo, useState } from 'react'
import Network3D, { type BusVisual } from './scene/Network3D'
import { BRANCHES } from './grid'
import { api } from './api'
import { useStore } from './store'
import { DEMO } from './demo'
import { isMuted, setMuted } from './sound'
import { fmtTime, list } from './text'
import Detection from './ui/Detection'
import Alarms from './ui/Alarms'
import Scenarios from './ui/Scenarios'
import Timeline from './ui/Timeline'
import Charts from './ui/Charts'
import BusCard from './ui/BusCard'
import Inspector from './ui/Inspector'
import Verification, { ProvenanceBanner, ProvenanceBadge } from './ui/Verification'
import Research from './ui/Research'
import { truthKnown } from './text'

function Clock() {
  const [t, setT] = useState(new Date())
  useEffect(() => { const i = setInterval(() => setT(new Date()), 1000); return () => clearInterval(i) }, [])
  return <div className="clock mono"><b>{t.toLocaleTimeString([], { hour12: false })}</b><span>{t.toLocaleDateString([], { day: '2-digit', month: 'short', year: 'numeric' })}</span></div>
}

function Settings({ onClose }: { onClose: () => void }) {
  const { status, refreshStatus } = useStore()
  const [url, setUrl] = useState('')
  const [msg, setMsg] = useState('')
  if (!status) return null
  const set = async (b: Parameters<typeof api.live>[0]) => { await api.live(b); refreshStatus() }
  return (
    <div className="settings" role="dialog" aria-label="Settings">
      <header><b>Settings</b><button className="btn xs" onClick={onClose} aria-label="Close">✕</button></header>
      <label>Live feed
        <select value={status.running ? status.mode : 'off'} disabled={DEMO}
          onChange={(e) => (e.target.value === 'off' ? set({ running: false }) : set({ running: true, mode: e.target.value }))}>
          <option value="quiet">Normal snapshots only (demo)</option>
          <option value="realistic">Realistic mix (~8% attacks)</option>
          <option value="test">Independent test set as it is</option>
          <option value="off">Paused</option>
        </select>
      </label>
      <label>Phone alerts (n8n)
        <select value={status.alert_scope} disabled={DEMO} onChange={(e) => set({ alert_scope: e.target.value })}>
          <option value="visitor">Simulated attacks only</option>
          <option value="all">Every alarm</option>
          <option value="off">Off</option>
        </select>
      </label>
      <form className="row" onSubmit={(e) => { e.preventDefault(); void set({ webhook: url }); setUrl('') }}>
        <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} disabled={DEMO}
          placeholder={status.webhook ? 'Webhook set — paste to replace' : 'n8n webhook URL'} />
        <button className="btn sm" disabled={DEMO || !url}>Save</button>
        <button type="button" className="btn sm" disabled={DEMO || !status.webhook}
          onClick={async () => { try { const r = await api.webhookTest(); setMsg(r.ok ? 'Test alert delivered.' : `Failed: ${r.error ?? r.code}`) } catch (e) { setMsg((e as Error).message) } }}>Test</button>
      </form>
      {msg && <p className="dim small">{msg}</p>}
      <p className="dim small">
        Start-up check: {status.self_check.checks.alarm?.match ?? 0}/{status.self_check.snapshots} alarms and {status.self_check.checks.named_buses?.match ?? 0}/{status.self_check.snapshots} named-bus sets identical to the notebook. Model bundle {status.bundle_id}.
      </p>
    </div>
  )
}

export default function App() {
  const s = useStore()
  const { status, connected, shown, injecting, alarms, flows, showTruth, setShowTruth, selectedBus, selectBus, pinnedId, pin } = s
  const [quality, setQuality] = useState<'high' | 'low'>(() => { try { return (localStorage.getItem('gdc-q') as 'high' | 'low') || 'high' } catch { return 'high' } })
  const [muted, setMutedS] = useState(isMuted())
  const [settings, setSettings] = useState(false)
  const [viewKey, setViewKey] = useState(0)
  const [zoom, setZoom] = useState<{ n: number; dir: 1 | -1 }>({ n: 0, dir: 1 })
  const [top, setTop] = useState(0)
  const [expanded, setExpanded] = useState(false)
  const [inspect, setInspect] = useState(false)
  const [verif, setVerif] = useState(false)
  const [page, setPage] = useState<'console' | 'research'>(() => (!DEMO && location.hash === '#research' ? 'research' : 'console'))
  useEffect(() => { const f = () => setPage(!DEMO && location.hash === '#research' ? 'research' : 'console'); addEventListener('hashchange', f); return () => removeEventListener('hashchange', f) }, [])
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') { setInspect(false); setVerif(false); setExpanded(false) } }
    addEventListener('keydown', k); return () => removeEventListener('keydown', k)
  }, [])

  const r = shown?.result
  const named = r?.alarm ? r.named_buses : []
  const busState = useMemo(() => {
    const st: Record<number, BusVisual> = {}
    if (injecting) injecting.buses.forEach((b) => (st[b] = 'injecting'))
    else named.forEach((b) => (st[b] = 'alarm'))
    return st
  }, [injecting, named])
  const alarmLines = useMemo(() => new Set(injecting ? [] : BRANCHES.flatMap(([a, b], i) => (named.includes(a) || named.includes(b) ? [i] : []))), [injecting, named])
  const lineFlows = useMemo(() => {
    const lf = r?.line_flow_mva
    return lf ? lf.map((v, i) => v * (Math.sign(flows[i] ?? 1) || 1)) : flows
  }, [r, flows])
  const unack = alarms.filter((a) => a.status === 'new').length
  if (page === 'research') return <Research status={status} onBack={() => { location.hash = ''; setPage('console') }} />
  const sysAlarm = unack > 0 || !!r?.alarm

  return (
    <div className={`console ${expanded ? 'expanded' : ''}`}>
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" aria-hidden><path d="M16 2 4 7v8c0 7.5 5.1 13.4 12 15 6.9-1.6 12-7.5 12-15V7L16 2Z" /><path d="M17.5 8 11 18h4.5l-1 6L21 14h-4.5l1-6Z" className="bolt" /></svg>
          <div><strong>GridDefense</strong><span>FDI detection console · IEEE 14-bus</span></div>
        </div>
        <div className="sim-badge">SIMULATION MODE · not connected to a real grid</div>
        <div className={`sys ${sysAlarm ? 'alarm' : 'ok'}`}><span className="lamp" />{sysAlarm ? `ALARM · ${unack} unacknowledged` : 'SYSTEM NORMAL'}</div>
        <div className="top-right">
          {DEMO ? <span className="badge warn">Preview · recorded results</span>
            : <span className={`badge ${connected ? 'ok' : 'bad'}`}>{connected ? 'Backend online' : 'Backend offline'}</span>}
          {status?.provenance && <ProvenanceBadge status={status} onClick={() => setVerif(true)} />}
          {!DEMO && <a className="btn sm" href="#research" onClick={() => setPage('research')}>Research results</a>}
          <button className="icon" onClick={() => { setMuted(!muted); setMutedS(!muted) }} aria-label={muted ? 'Alarm tone off' : 'Alarm tone on'} title={muted ? 'Alarm tone off' : 'Alarm tone on'}>
            <svg viewBox="0 0 24 24" aria-hidden><path d="M4 9h4l5-4v14l-5-4H4z" className="fill" />{muted ? <path d="m16 9 5 6m0-6-5 6" /> : <path d="M16.5 8.5a5 5 0 0 1 0 7" />}</svg>
          </button>
          <button className="icon" onClick={() => setSettings((v) => !v)} aria-label="Settings" aria-expanded={settings}>
            <svg viewBox="0 0 24 24" aria-hidden><circle cx="12" cy="12" r="3" /><path d="M19.4 13.5a7.6 7.6 0 0 0 0-3l2-1.5-2-3.4-2.3 1a7.5 7.5 0 0 0-2.6-1.5L14 2.6h-4l-.5 2.5A7.5 7.5 0 0 0 6.9 6.6l-2.3-1-2 3.4 2 1.5a7.6 7.6 0 0 0 0 3l-2 1.5 2 3.4 2.3-1a7.5 7.5 0 0 0 2.6 1.5l.5 2.5h4l.5-2.5a7.5 7.5 0 0 0 2.6-1.5l2.3 1 2-3.4z" /></svg>
          </button>
          <Clock />
        </div>
        {settings && <Settings onClose={() => setSettings(false)} />}
      </header>
      {status?.provenance && <ProvenanceBanner status={status} onClick={() => setVerif(true)} />}

      <aside className="col-left"><Detection /></aside>

      <main className="view">
        <Network3D busState={busState} truthBuses={showTruth && !injecting && shown && truthKnown(shown) ? shown.truth.buses : []} vm={r?.measurements?.Vm ?? null}
          flows={lineFlows} alarmLines={alarmLines} selected={selectedBus} onSelect={selectBus} quality={quality} resetKey={viewKey} zoom={zoom} topView={top} />
        <div className="view-head">
          <span className="view-title">Network view</span>
          {pinnedId != null && shown && (
            <span className="pinned">{shown.source === 'live' ? 'Replay' : shown.scenario ? `Scenario ${shown.scenario.id}` : 'Custom attack'} · event #{shown.id} · {fmtTime(shown.time)}
              <button className="btn xs" onClick={() => pin(null)}>Back to live</button></span>
          )}
        </div>
        {injecting && <div className="injecting" role="status"><span className="spin" />Injecting false data · {injecting.label}{injecting.buses.length ? ` · ${list(injecting.buses)}` : ''} — scoring with GridDefense…</div>}
        <div className="view-tools">
          <label className="tog"><input type="checkbox" checked={showTruth} onChange={(e) => setShowTruth(e.target.checked)} /> Show ground truth</label>
          <button className="btn xs primary" onClick={() => setInspect(true)} disabled={!shown}>Details</button>
          <span className="tool-group" role="group" aria-label="Camera">
            <button className="btn xs" onClick={() => setZoom((z) => ({ n: z.n + 1, dir: 1 }))} aria-label="Zoom in" title="Zoom in">+</button>
            <button className="btn xs" onClick={() => setZoom((z) => ({ n: z.n + 1, dir: -1 }))} aria-label="Zoom out" title="Zoom out">−</button>
            <button className="btn xs" onClick={() => setTop((t) => t + 1)} title="View from above">Top</button>
            <button className="btn xs" onClick={() => setViewKey((k) => k + 1)}>Reset</button>
          </span>
          <button className="btn xs" onClick={() => setExpanded((v) => !v)} aria-pressed={expanded} title="Large network view (Esc to leave)">{expanded ? 'Exit large view' : 'Large view'}</button>
          <button className="btn xs" onClick={() => { const q = quality === 'high' ? 'low' : 'high'; setQuality(q); try { localStorage.setItem('gdc-q', q) } catch { /* ignore */ } }}>{quality === 'high' ? 'Quality: high' : 'Quality: fast'}</button>
        </div>
        <div className="view-legend">
          <span><i className="l-flow" />power flow</span>
          <span><i className="l-alarm" />bus named by GridDefense</span>
          <span><i className="l-line" />lines at alarmed bus</span>
          {showTruth && <span><i className="l-truth" />ground truth (attacked)</span>}
          <span className="dim">Labels: measured voltage (pu). Click a bus to inspect.</span>
        </div>
        <BusCard onDetails={() => setInspect(true)} />
      </main>
      {inspect && <Inspector onClose={() => setInspect(false)} />}
      {verif && status && <Verification status={status} onClose={() => setVerif(false)} />}

      <aside className="col-right">
        <Scenarios />
        <Alarms />
      </aside>

      <section className="bottom">
        <Timeline />
        <Charts />
      </section>
    </div>
  )
}
