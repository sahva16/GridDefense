// IEEE 14-bus test system. Branch list and order are the real case data (PYPOWER case14,
// identical to the backend). Positions follow the usual one-line diagram of the system.
// Buses 1–5: 132 kV transmission level. Buses 6–14: 33 kV sub-transmission level.

export type Role = 'generator' | 'condenser' | 'load' | 'capacitor'
export type BusDef = { bus: number; x: number; z: number; role: Role; name: string; kv: 132 | 33 }

export const BUSES: BusDef[] = [
  { bus: 1, x: -42, z: 12, role: 'generator', name: 'Generator 1 (slack)', kv: 132 },
  { bus: 2, x: -30, z: 32, role: 'generator', name: 'Generator 2', kv: 132 },
  { bus: 3, x: 12, z: 34, role: 'condenser', name: 'Sync. condenser 3', kv: 132 },
  { bus: 4, x: 14, z: 12, role: 'load', name: 'Substation 4', kv: 132 },
  { bus: 5, x: -18, z: 8, role: 'load', name: 'Substation 5', kv: 132 },
  { bus: 6, x: -18, z: -14, role: 'condenser', name: 'Sync. condenser 6', kv: 33 },
  { bus: 7, x: 32, z: 2, role: 'load', name: 'Junction 7', kv: 33 },
  { bus: 8, x: 48, z: 2, role: 'condenser', name: 'Sync. condenser 8', kv: 33 },
  { bus: 9, x: 26, z: -14, role: 'capacitor', name: 'Substation 9 (shunt C)', kv: 33 },
  { bus: 10, x: 9, z: -20, role: 'load', name: 'Substation 10', kv: 33 },
  { bus: 11, x: -5, z: -22, role: 'load', name: 'Substation 11', kv: 33 },
  { bus: 12, x: -30, z: -36, role: 'load', name: 'Substation 12', kv: 33 },
  { bus: 13, x: -8, z: -38, role: 'load', name: 'Substation 13', kv: 33 },
  { bus: 14, x: 24, z: -36, role: 'load', name: 'Substation 14', kv: 33 },
]

export const BRANCHES: [number, number][] = [
  [1, 2], [1, 5], [2, 3], [2, 4], [2, 5], [3, 4], [4, 5], [4, 7], [4, 9], [5, 6],
  [6, 11], [6, 12], [6, 13], [7, 8], [7, 9], [9, 10], [9, 14], [10, 11], [12, 13], [13, 14],
]
export const TRANSFORMERS = new Set(['4-7', '4-9', '5-6'])
export const branchName = (i: number) => `${BRANCHES[i][0]}–${BRANCHES[i][1]}`
export const busDef = (b: number) => BUSES[b - 1]
export const neighbours = (b: number) =>
  BRANCHES.flatMap(([f, t], i) => (f === b ? [{ bus: t, line: i }] : t === b ? [{ bus: f, line: i }] : []))
