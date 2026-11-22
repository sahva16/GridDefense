// Types and calls for the GridDefense FastAPI backend (backend/app/main.py).
import { DEMO, demoApi } from './demo'

export type BusInfo = {
  bus: number
  votes: number
  physics_alarm: boolean
  checks_failed: string[]
  z: Record<string, number>
  loc_probability: number
  named: boolean
  ae_error: number
}

export type Result = {
  alarm: boolean
  fusion: {
    score: number
    threshold: number
    parts: { ae: number; rf: number; physics: number }
    weights: { ae: number; rf: number; physics: number }
  }
  detectors: {
    ae: { score: number; error: number; flag: boolean }
    rf: { score: number; flag: boolean }
    physics: { score: number; flag: boolean }
  }
  attack_type: string | null
  type_probabilities: Record<string, number>
  named_buses: number[]
  line_flow_mva?: number[]
  buses: BusInfo[]
  measurements?: { Vm: number[]; Va: number[]; Pd: number[]; Qd: number[] }
  measurement_table?: MeasurementTable | null
  explanation?: { summary: string; lines: string[]; borderline: boolean }
}

export type MeasCell = { observed: number; normal_mean: number; normal_std: number; normal_p1: number; normal_p99: number; deviation: number; deviation_sd: number | null }
export type MeasurementTable = { source: string; rows: ({ bus: number } & Record<'Vm' | 'Va' | 'Pd' | 'Qd', MeasCell>)[] }
export type Verdict = { actual: number[]; predicted: number[]; correct: number[]; missed: number[]; extra: number[]; exact: boolean }

export type Simulation = { attack: string; buses: number[]; size_pct: number; direction: number; seed: number }

export type GridEvent = {
  id: number
  time: string
  source: 'live' | 'simulator' | 'scenario' | 'upload'
  snapshot: number | null
  result: Result
  bundle_id?: string | null
  truth: { type: string | null; buses: number[] }
  truth_known?: boolean
  verdict?: Verdict | null
  simulation?: Simulation
  scenario?: { id: string; title: string }
}

export type WebhookStatus = null | { ok: boolean | null; pending?: boolean; code?: number; error?: string; at: string }

export type Alarm = {
  id: number
  event_id: number
  time: string
  source: string
  severity: 'critical' | 'high' | 'medium'
  attack_type: string
  buses: number[]
  score: number
  status: 'new' | 'acknowledged' | 'escalated' | 'dismissed' | 'resolved' | 'cleared'
  notes: { time: string; action: string; note: string }[]
  webhook: WebhookStatus
}

export type Scenario = {
  id: string; title: string; attack: string; buses: number[]; size_pct: number; direction: number; seed: number; note: string
}

export type CheckRow = { match: number; total: number }
export type SelfCheck = {
  snapshots: number; checks: Record<string, CheckRow>; mismatches: Record<string, number[]>; fusion_max_abs_diff: number
  app_alarms: number; notebook_alarms: number; passed: boolean; tolerance: string; checked_at: string; seconds: number
}
export type Provenance = { status: 'verified' | 'development' | 'unverified'; kind: string | null; reasons: string[]; bundle_id: string; label: string }

export type Status = {
  self_check: SelfCheck
  provenance: Provenance
  bundle_id: string
  running: boolean
  interval: number
  mode: 'quiet' | 'realistic' | 'test'
  webhook: boolean
  alert_scope: 'visitor' | 'all' | 'off'
  stats: { scored: number; alarms: number; started: string }
  test_snapshots: number
  logged_events?: number
  model: {
    sklearn_bundle: string
    sklearn_app: string
    numpy_bundle: string
    numpy_app: string
    exported_at: string | null
    manifest_versions: Record<string, string | null> | null
    model_sha256: string | null
    source_md5: Record<string, string> | null
    integrity: { manifest_present: boolean; model_sha256_ok?: boolean; test_sha256_ok?: boolean }
    colab_checks: Record<string, number> | null
    features: { ae: number; rf: number; localiser: number; ae_cols: string[]; rf_cols: string[] }
    fusion_bounds: { ae_lo: number; ae_hi: number }
    fusion: { w_ae: number; w_rf: number; w_phys: number; threshold: number }
    physics: { Z: number; votes: number; checks: string[] }
    loc_threshold: number
    ae_threshold: number
  }
  config: Record<string, number | boolean>
}

export type Topology = { branches: [number, number][]; base_flow_mw: number[] }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try {
      const j = await r.json()
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail
        : j.detail.errors ? `${j.detail.message} ${j.detail.errors.join(' · ')}` : JSON.stringify(j.detail)
    } catch { /* keep status text */ }
    throw new Error(msg)
  }
  return r.json()
}

const realApi = {
  status: () => req<Status>('/api/status'),
  topology: () => req<Topology>('/api/topology'),
  events: (limit = 200) => req<GridEvent[]>(`/api/events?limit=${limit}`),
  alarms: () => req<Alarm[]>('/api/alarms'),
  scenarios: () => req<Scenario[]>('/api/scenarios'),
  runScenario: (id: string) => req<{ event: GridEvent; alarm: Alarm | null }>(`/api/scenarios/${id}/run`, { method: 'POST' }),
  reset: () => req<{ ok: boolean }>('/api/reset', { method: 'POST' }),
  alarmAction: (id: number, action: string, note = '') =>
    req<Alarm>(`/api/alarms/${id}`, { method: 'POST', body: JSON.stringify({ action, note }) }),
  live: (body: Partial<{ running: boolean; interval: number; mode: string; webhook: string; alert_scope: string }>) =>
    req<{ running: boolean; interval: number; mode: string; webhook: string; alert_scope: string }>('/api/live', {
      method: 'POST', body: JSON.stringify(body),
    }),
  simulate: (body: { attack: string; buses: number[]; size_pct: number; direction: number; seed?: number }) =>
    req<{ event: GridEvent; alarm: Alarm | null }>('/api/simulate', { method: 'POST', body: JSON.stringify(body) }),
  score: (snapshot: Record<string, unknown> | number[]) =>
    req<{ event: GridEvent; alarm: Alarm | null }>('/api/score', { method: 'POST', body: JSON.stringify({ snapshot }) }),
  performance: () => req<Record<string, unknown>>('/api/performance'),
  webhookTest: () => req<{ ok: boolean; code?: number; error?: string }>('/api/webhook/test', { method: 'POST' }),
}

export type Api = typeof realApi
export const api: Api = DEMO ? (demoApi as unknown as Api) : realApi
export const EXPORT_URL = '/api/export/events.csv'
