import type { GridEvent, Result } from './api'

export const CHECK_TEXT: Record<string, { short: string; long: string }> = {
  P_res: { short: 'P balance', long: 'Real-power balance: power computed from the measured voltages does not match the measured injection' },
  Q_res: { short: 'Q balance', long: 'Reactive-power balance: reactive power from the measured voltages does not match the measured injection' },
  Va_neighbor: { short: 'Angle vs nbrs', long: 'The angle difference to neighbouring buses is outside its normal range' },
  Vm_neighbor: { short: 'Voltage vs nbrs', long: 'The voltage difference to neighbouring buses is outside its normal range' },
  S_loading: { short: 'Line loading', long: 'A connected line is loaded beyond its rating' },
}

export const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString([], { hour12: false })
export const list = (xs: number[]) => (xs.length ? xs.map((b) => `B${b}`).join(', ') : '—')
export const pct = (x: number, d = 0) => `${(x * 100).toFixed(d)}%`

export function sourceLabel(e: GridEvent) {
  if (e.source === 'scenario') return `Scenario ${e.scenario?.id ?? ''}`
  if (e.source === 'simulator') return e.simulation?.attack === 'Normal' ? 'Simulated normal' : 'Custom attack'
  if (e.source === 'upload') return 'Uploaded snapshot'
  return e.snapshot != null ? `Test-set replay · snapshot ${e.snapshot}` : 'Test-set replay'
}

/** Headline for a decision; honest when the classifier and the fusion disagree. */
export function decisionText(r: Result) {
  if (!r.alarm) return 'Normal'
  if (!r.attack_type || r.attack_type === 'Normal') return 'Anomaly · type unclassified'
  return `${r.attack_type} FDI suspected`
}

/** Ground truth is known only for the simulator, scenarios and test-set replay — never for uploads. */
export const truthKnown = (e: GridEvent) => e.truth_known !== false && e.truth.type != null
