// Alarm annunciator tone: three short, soft beeps (the kind of tone an EMS/SCADA console
// uses for a new high-priority alarm). Played once per new alarm, never looped.
// Generated with the Web Audio API; browsers allow it only after the first click.

let ctx: AudioContext | null = null
let muted = false
try { muted = localStorage.getItem('gdc-muted') === '1' } catch { /* storage unavailable */ }

export const isMuted = () => muted
export function setMuted(m: boolean) {
  muted = m
  try { localStorage.setItem('gdc-muted', m ? '1' : '0') } catch { /* ignore */ }
}

function ac() {
  if (!ctx) ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
  if (ctx.state === 'suspended') void ctx.resume()
  return ctx
}

/** Three 140 ms beeps at 880 Hz with soft edges; `critical` adds a second, lower group. */
export function annunciate(critical = false) {
  if (muted) return
  let a: AudioContext
  try { a = ac() } catch { return }
  const groups = critical ? [[880, 0], [660, 0.95]] : [[880, 0]]
  for (const [freq, offset] of groups) {
    for (let i = 0; i < 3; i++) {
      const t = a.currentTime + offset + i * 0.24
      const o = a.createOscillator(), g = a.createGain()
      o.type = 'sine'
      o.frequency.value = freq
      g.gain.setValueAtTime(0, t)
      g.gain.linearRampToValueAtTime(0.12, t + 0.015)
      g.gain.setValueAtTime(0.12, t + 0.125)
      g.gain.linearRampToValueAtTime(0, t + 0.14)
      o.connect(g).connect(a.destination)
      o.start(t); o.stop(t + 0.16)
    }
  }
}
