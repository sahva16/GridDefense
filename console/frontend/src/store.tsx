// Console state: data from the backend (status, events, alarms, scenarios) plus what the
// operator is looking at (live or a pinned/replayed event, the selected bus).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, type Alarm, type GridEvent, type Scenario, type Status } from './api'
import { DEMO, subscribe } from './demo'
import { annunciate } from './sound'

type Injecting = { buses: number[]; label: string } | null

type Store = {
  status: Status | null
  flows: number[]
  events: GridEvent[]
  alarms: Alarm[]
  scenarios: Scenario[]
  connected: boolean
  shown: GridEvent | undefined
  pinnedId: number | null
  selectedBus: number | null
  showTruth: boolean
  injecting: Injecting
  busy: boolean
  error: string
  setShowTruth: (v: boolean) => void
  selectBus: (b: number | null) => void
  pin: (id: number | null) => void
  runScenario: (s: Scenario) => Promise<void>
  runCustom: (b: { attack: string; buses: number[]; size_pct: number; direction: number }) => Promise<void>
  reset: () => Promise<void>
  ack: (id: number) => Promise<void>
  ackAll: () => Promise<void>
  refreshStatus: () => void
  pushEvent: (e: GridEvent, a: Alarm | null) => void
  scoreSnapshot: (snap: Record<string, unknown> | number[]) => Promise<void>
}

const Ctx = createContext<Store | null>(null)
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

export function StoreProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null)
  const [flows, setFlows] = useState<number[]>([])
  const [events, setEvents] = useState<GridEvent[]>([])
  const [alarms, setAlarms] = useState<Alarm[]>([])
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [connected, setConnected] = useState(false)
  const [pinnedId, setPinned] = useState<number | null>(null)
  const [selectedBus, selectBus] = useState<number | null>(null)
  const [showTruth, setShowTruth] = useState(true)
  const [injecting, setInjecting] = useState<Injecting>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const seenAlarms = useRef(new Set<number>())
  // while a simulated attack is being injected, live messages wait so the result is revealed in order
  const holding = useRef(false)
  const held = useRef<{ e: GridEvent; a: Alarm | null }[]>([])

  const refreshStatus = useCallback(() => {
    api.status().then((s) => { setStatus(s); setConnected(true) }).catch(() => setConnected(false))
  }, [])

  const upsertAlarm = useCallback((a: Alarm) => {
    setAlarms((list) => {
      const i = list.findIndex((x) => x.id === a.id)
      if (i < 0) return [a, ...list].slice(0, 300)
      // a webhook result can arrive before the HTTP reply that still says "pending"
      const old = list[i]
      const keepHook = old.webhook && !old.webhook.pending && a.webhook?.pending
      const keepStatus = old.status === 'cleared' && a.status === 'new'
      const next = list.slice()
      next[i] = { ...a, ...(keepHook ? { webhook: old.webhook } : {}), ...(keepStatus ? { status: old.status } : {}) }
      return next
    })
    if (!seenAlarms.current.has(a.id)) {
      seenAlarms.current.add(a.id)
      if (a.status === 'new') annunciate(a.severity === 'critical')
    }
  }, [])

  const pushEvent = useCallback((e: GridEvent, a: Alarm | null) => {
    setEvents((list) => (list.some((x) => x.id === e.id) ? list : [e, ...list].slice(0, 400)))
    if (a) upsertAlarm(a)
  }, [upsertAlarm])

  useEffect(() => {
    refreshStatus()
    api.topology().then((t) => setFlows(t.base_flow_mw)).catch(() => {})
    api.events(200).then(setEvents).catch(() => {})
    api.alarms().then((l) => { l.forEach((a) => seenAlarms.current.add(a.id)); setAlarms(l) }).catch(() => {})
    api.scenarios().then(setScenarios).catch(() => {})
    const t = setInterval(refreshStatus, 8000)
    return () => clearInterval(t)
  }, [refreshStatus])

  useEffect(() => {
    if (DEMO) { setConnected(true); return subscribe((e, a) => pushEvent(e, a)) }
    let stop = false
    let retry: ReturnType<typeof setTimeout>
    let ws: WebSocket | null = null
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws`)
      ws.onopen = () => setConnected(true)
      ws.onclose = () => { setConnected(false); if (!stop) retry = setTimeout(connect, 2000) }
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data)
        if (msg.type === 'event') { if (holding.current) held.current.push({ e: msg.event, a: msg.alarm }); else pushEvent(msg.event, msg.alarm) }
        if (msg.type === 'alarm_update') upsertAlarm(msg.alarm)
        if (msg.type === 'reset') setAlarms((l) => l.map((a) => (['new', 'acknowledged', 'escalated'].includes(a.status) ? { ...a, status: 'cleared' } : a)))
      }
    }
    connect()
    return () => { stop = true; clearTimeout(retry); ws?.close() }
  }, [pushEvent, upsertAlarm])

  const shown = useMemo(() => (pinnedId != null ? events.find((e) => e.id === pinnedId) : events[0]) ?? events[0], [events, pinnedId])

  const runAttack = useCallback(async (label: string, buses: number[], call: () => Promise<{ event: GridEvent; alarm: Alarm | null }>) => {
    setBusy(true); setError(''); holding.current = true
    setInjecting(buses.length ? { buses, label } : { buses: [], label })
    try {
      const [out] = await Promise.all([call(), wait(1600)])
      pushEvent(out.event, out.alarm)
      setPinned(out.event.id)
      selectBus(out.event.result.alarm && out.event.result.named_buses.length ? out.event.result.named_buses[0] : null)
    } catch (e) { setError((e as Error).message) }
    finally {
      holding.current = false
      held.current.splice(0).forEach((x) => pushEvent(x.e, x.a))
      setInjecting(null); setBusy(false)
    }
  }, [pushEvent])

  const value: Store = {
    status, flows, events, alarms, scenarios, connected, shown, pinnedId, selectedBus, showTruth, injecting, busy, error,
    setShowTruth, selectBus, pin: setPinned, refreshStatus, pushEvent,
    scoreSnapshot: async (snap) => {
      setBusy(true); setError('')
      try { const out = await api.score(snap); pushEvent(out.event, out.alarm); setPinned(out.event.id) }
      catch (e) { setError((e as Error).message); throw e }
      finally { setBusy(false) }
    },
    runScenario: (s) => runAttack(`${s.id} · ${s.title}`, s.buses, () => api.runScenario(s.id)),
    runCustom: (b) => runAttack(`Custom ${b.attack} ${b.size_pct}%`, b.buses, () => api.simulate(b)),
    reset: async () => {
      await api.reset().catch(() => {})
      setAlarms((l) => l.map((a) => (['new', 'acknowledged', 'escalated'].includes(a.status) ? { ...a, status: 'cleared' } : a)))
      setPinned(null); selectBus(null); setError('')
    },
    ack: async (id) => { upsertAlarm(await api.alarmAction(id, 'acknowledge')) },
    ackAll: async () => {
      for (const a of alarms.filter((x) => x.status === 'new')) upsertAlarm(await api.alarmAction(a.id, 'acknowledge'))
    },
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useStore() {
  const s = useContext(Ctx)
  if (!s) throw new Error('StoreProvider missing')
  return s
}
