// Alarm summary in the usual SCADA layout: newest first, priority, state, acknowledge.
import { useStore } from '../store'
import { fmtTime, list } from '../text'
import Panel from './Panel'

const PRI: Record<string, string> = { critical: '1', high: '2', medium: '3' }
const STATE: Record<string, string> = { new: 'UNACK', acknowledged: 'ACK', escalated: 'ESC', dismissed: 'DISM', resolved: 'RES', cleared: 'CLR' }

export default function Alarms() {
  const { alarms, ack, ackAll, pin, pinnedId, events } = useStore()
  const active = alarms.filter((a) => ['new', 'acknowledged', 'escalated'].includes(a.status))
  const unack = alarms.filter((a) => a.status === 'new').length
  const shownId = pinnedId ?? events[0]?.id
  return (
    <Panel title="Alarm summary" meta={<><b className={unack ? 'red' : ''}>{unack}</b> unack · {active.length} active</>}
      actions={<button className="btn sm" disabled={!unack} onClick={ackAll}>Ack all</button>}>
      {alarms.length === 0 ? <p className="dim">No alarms.</p> : (
        <div className="scroll">
          <table className="tbl alarms">
            <thead><tr><th>Time</th><th>P</th><th>Description</th><th className="r">Score</th><th>State</th><th /></tr></thead>
            <tbody>
              {alarms.slice(0, 60).map((a) => (
                <tr key={a.id} className={`sev-${a.severity} st-${a.status} ${a.event_id === shownId ? 'shown' : ''}`} onClick={() => pin(a.event_id)}>
                  <td className="mono">{fmtTime(a.time)}</td>
                  <td><span className={`pri p${PRI[a.severity]}`}>{PRI[a.severity]}</span></td>
                  <td>{a.attack_type === 'Normal' ? 'Anomaly' : `${a.attack_type} FDI`} · {a.buses.length ? list(a.buses) : 'no bus named'}
                    {a.webhook?.ok && <span className="sent" title="Sent to the operator's phone through n8n">phone ✓</span>}</td>
                  <td className="r mono">{a.score.toFixed(2)}</td>
                  <td><span className={`state ${a.status}`}>{STATE[a.status] ?? a.status}</span></td>
                  <td>{a.status === 'new' && <button className="btn xs" onClick={(ev) => { ev.stopPropagation(); void ack(a.id) }}>Ack</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
