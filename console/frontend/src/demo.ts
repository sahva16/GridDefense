// Preview mode (VITE_DEMO=1): no Python backend. Replays results recorded from the real
// backend with tools/record_preview.py — every scenario and attack there was a real call,
// scored by the models the backend had loaded.
import type { Alarm, GridEvent, Scenario, Status } from './api'

export const DEMO = import.meta.env.VITE_DEMO === '1'

type Data = {
  status: Status
  topology: { branches: [number, number][]; base_flow_mw: number[] }
  scenarios: Scenario[]
  live: GridEvent[]
  scenario_runs: Record<string, GridEvent>
  sims: Record<string, GridEvent>
}
let data: Data | null = null
const load = async () => (data ??= (await import('./demo-data.json')).default as unknown as Data)

const SIZES = [0.25, 0.5, 1.0, 1.5, 2.0, 3.0]
const py = (x: number) => (Number.isInteger(x) ? x.toFixed(1) : String(x))   // keys were written by Python
let nextId = 1
let cursor = 0
const alarms: Alarm[] = []
const history: GridEvent[] = []

function stamp(e: GridEvent, t = new Date()): GridEvent { return { ...e, id: nextId++, time: t.toISOString() } }
function toAlarm(e: GridEvent): Alarm | null {
  if (!e.result.alarm) return null
  const s = e.result.fusion.score
  const a: Alarm = { id: e.id, event_id: e.id, time: e.time, source: e.source, severity: s >= 0.75 ? 'critical' : s >= 0.55 ? 'high' : 'medium',
    attack_type: e.result.attack_type ?? 'Normal', buses: e.result.named_buses, score: s, status: 'new', notes: [], webhook: null }
  alarms.unshift(a)
  return a
}
async function seed() {
  const d = await load()
  if (history.length) return d
  const now = Date.now()
  for (let i = 0; i < 60; i++) {
    const e = stamp(d.live[cursor++ % d.live.length], new Date(now - (60 - i) * 2000))
    history.unshift(e)
    const a = toAlarm(e); if (a) a.status = 'acknowledged'
  }
  return d
}

export const demoApi = {
  status: async () => ({ ...(await seed()).status, webhook: false, alert_scope: 'off', mode: 'quiet', running: true }),
  topology: async () => (await load()).topology,
  events: async () => { await seed(); return history.slice() },
  alarms: async () => { await seed(); return alarms.map((a) => ({ ...a })) },
  scenarios: async () => (await load()).scenarios,
  runScenario: async (id: string) => {
    const d = await load()
    const e = stamp(d.scenario_runs[id])
    return { event: e, alarm: toAlarm(e) }
  },
  simulate: async (b: { attack: string; buses: number[]; size_pct: number; direction: number }) => {
    const d = await load()
    const size = SIZES.reduce((p, c) => (Math.abs(c - b.size_pct) < Math.abs(p - b.size_pct) ? c : p))
    const rec = d.sims[`${b.attack}|${b.buses[0]}|${py(size)}|${b.direction >= 0 ? 1 : -1}`]
    if (!rec) throw new Error('Not recorded for the preview')
    const e = stamp(rec)
    return { event: e, alarm: toAlarm(e) }
  },
  reset: async () => { alarms.forEach((a) => { if (['new', 'acknowledged', 'escalated'].includes(a.status)) a.status = 'cleared' }); return { ok: true } },
  alarmAction: async (id: number, action: string) => {
    const a = alarms.find((x) => x.id === id)!
    a.status = action === 'acknowledge' ? 'acknowledged' : 'resolved'
    return { ...a }
  },
  live: async () => ({ running: true, interval: 2, mode: 'quiet', webhook: '', alert_scope: 'off' }),
  webhookTest: async () => ({ ok: false, error: 'Phone alerts need the full app.' }),
}

/** Streams the recorded normal live snapshots, one every 2 s. */
export function subscribe(cb: (e: GridEvent, a: Alarm | null) => void) {
  const t = setInterval(async () => {
    const d = await seed()
    const e = stamp(d.live[cursor++ % d.live.length])
    cb(e, toAlarm(e))
  }, 2000)
  return () => clearInterval(t)
}
