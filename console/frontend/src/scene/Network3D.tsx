// 3D network view of the IEEE 14-bus system in an operator-console style: dark floor grid,
// wireframe substations and lattice towers, power-flow particles, live voltages on every bus,
// and alarm states coming from GridDefense.
import { useMemo, useRef } from 'react'
import { Canvas, useFrame, type ThreeEvent } from '@react-three/fiber'
import { Edges, Grid, Html, OrbitControls } from '@react-three/drei'
import { Bloom, EffectComposer } from '@react-three/postprocessing'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { BRANCHES, BUSES, TRANSFORMERS, type BusDef, busDef } from '../grid'

export type BusVisual = 'normal' | 'alarm' | 'injecting'
export type NetworkProps = {
  busState: Record<number, BusVisual>
  truthBuses: number[]
  vm: number[] | null
  flows: number[]          // MVA or MW per branch; sign gives direction
  alarmLines: Set<number>  // branch indexes touching an alarmed bus
  selected: number | null
  onSelect: (b: number | null) => void
  quality: 'high' | 'low'
  resetKey: number
  zoom?: { n: number; dir: 1 | -1 }   // each change zooms one step in (1) or out (-1)
  topView?: number                    // each change moves the camera straight above the grid
}

const CYAN = new THREE.Color(0.2, 0.78, 0.9)
const RED = new THREE.Color(3.2, 0.25, 0.2)
const AMBER = new THREE.Color(2.6, 1.4, 0.2)
const ORANGE = new THREE.Color(2.4, 0.8, 0.2)
const BUS_Y = 2.6

// ── lattice tower as line segments (local coords; cross-arm along X, line along Z) ──
function latticeSegments(h: number): number[] {
  const s: number[] = []
  const seg = (a: number[], b: number[]) => s.push(...a, ...b)
  const base = h * 0.13, top = h * 0.045
  const w = (y: number) => base + (top - base) * (y / h)
  const levels = [0, h * 0.22, h * 0.44, h * 0.62, h * 0.78, h]
  const corner = (y: number, i: number) => {
    const k = w(y); return [[-k, y, -k], [k, y, -k], [k, y, k], [-k, y, k]][i]
  }
  for (let l = 0; l < levels.length; l++) {
    for (let i = 0; i < 4; i++) seg(corner(levels[l], i), corner(levels[l], (i + 1) % 4))
    if (l < levels.length - 1) for (let i = 0; i < 4; i++) {
      seg(corner(levels[l], i), corner(levels[l + 1], i))
      seg(corner(levels[l], i), corner(levels[l + 1], (i + 1) % 4))
      seg(corner(levels[l], (i + 1) % 4), corner(levels[l + 1], i))
    }
  }
  const armY = [h * 0.78, h * 0.92]
  const armW = [h * 0.3, h * 0.2]
  armY.forEach((y, j) => {
    seg([-armW[j], y, 0], [armW[j], y, 0])
    seg([-armW[j], y, 0], [-w(y), y - h * 0.08, 0])
    seg([armW[j], y, 0], [w(y), y - h * 0.08, 0])
    // insulator strings
    seg([-armW[j] * 0.9, y, 0], [-armW[j] * 0.9, y - h * 0.07, 0])
    seg([armW[j] * 0.9, y, 0], [armW[j] * 0.9, y - h * 0.07, 0])
  })
  seg([0, h, 0], [0, h * 1.08, 0])
  return s
}

type LineGeo = { towers: { p: THREE.Vector3; yaw: number; h: number }[]; wires: number[]; path: THREE.Vector3[]; cum: number[]; len: number; mid: THREE.Vector3 }

function buildLines(): LineGeo[] {
  return BRANCHES.map(([a, b]) => {
    const A = busDef(a), B = busDef(b)
    const hv = (A.kv === 132 && B.kv === 132) || TRANSFORMERS.has(`${a}-${b}`)
    const h = hv ? 7 : 5
    const d = new THREE.Vector3(B.x - A.x, 0, B.z - A.z)
    const L = d.length(); d.normalize()
    const yaw = Math.atan2(d.x, d.z)
    const right = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw))
    const start = new THREE.Vector3(A.x, 0, A.z).addScaledVector(d, 4.2)
    const end = new THREE.Vector3(B.x, 0, B.z).addScaledVector(d, -4.2)
    const n = Math.max(1, Math.round((L - 8.4) / 19))
    const towers = Array.from({ length: n }, (_, i) => ({ p: start.clone().lerp(end, (i + 1) / (n + 1)), yaw, h }))
    const armY = h * 0.78 - h * 0.07, off = h * 0.3 * 0.9
    const phases = [-off, off, 0]
    const wires: number[] = []
    let path: THREE.Vector3[] = []
    phases.forEach((o, k) => {
      const yTop = k === 2 ? h * 0.92 - h * 0.07 : armY
      const pts = [new THREE.Vector3(A.x, BUS_Y, A.z).addScaledVector(right, o * 0.25),
        ...towers.map((t) => t.p.clone().add(new THREE.Vector3(0, yTop, 0)).addScaledVector(right, k === 2 ? -h * 0.2 * 0.9 : o)),
        new THREE.Vector3(B.x, BUS_Y, B.z).addScaledVector(right, o * 0.25)]
      const full: THREE.Vector3[] = []
      for (let i = 0; i < pts.length - 1; i++) {
        const span = pts[i].distanceTo(pts[i + 1])
        const sag = Math.min(1.1, span * 0.05)
        for (let j = 0; j <= 10; j++) {
          const t = j / 10
          const p = pts[i].clone().lerp(pts[i + 1], t)
          p.y -= sag * 4 * t * (1 - t)
          if (j > 0 || i === 0) full.push(p)
        }
      }
      for (let i = 0; i < full.length - 1; i++) wires.push(full[i].x, full[i].y, full[i].z, full[i + 1].x, full[i + 1].y, full[i + 1].z)
      if (k === 0) path = full
    })
    const cum = [0]
    for (let i = 1; i < path.length; i++) cum.push(cum[i - 1] + path[i].distanceTo(path[i - 1]))
    return { towers, wires, path, cum, len: cum[cum.length - 1], mid: path[Math.floor(path.length / 2)].clone() }
  })
}

function pointOn(l: LineGeo, s: number, out: THREE.Vector3) {
  let lo = 0, hi = l.cum.length - 1
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (l.cum[m] < s) lo = m; else hi = m }
  const seg = l.cum[hi] - l.cum[lo] || 1
  return out.copy(l.path[lo]).lerp(l.path[hi], (s - l.cum[lo]) / seg)
}

function Network({ lines, flows, alarmLines }: { lines: LineGeo[]; flows: number[]; alarmLines: Set<number> }) {
  const towerGeom = useMemo(() => {
    const all: number[] = []
    const hv = latticeSegments(7), mv = latticeSegments(5)
    lines.forEach((l) => l.towers.forEach((t) => {
      const src = t.h > 6 ? hv : mv
      const c = Math.cos(t.yaw), s = Math.sin(t.yaw)
      for (let i = 0; i < src.length; i += 3) {
        const x = src[i], y = src[i + 1], z = src[i + 2]
        all.push(t.p.x + x * c + z * s, y, t.p.z - x * s + z * c)
      }
    }))
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(all, 3)); return g
  }, [lines])
  const wireGeoms = useMemo(() => lines.map((l) => {
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(l.wires, 3)); return g
  }), [lines])

  // flow particles
  const parts = useMemo(() => {
    const list: { line: number; off: number }[] = []
    lines.forEach((l, i) => { const n = Math.max(2, Math.round(l.len / 5)); for (let k = 0; k < n; k++) list.push({ line: i, off: (k / n) * l.len }) })
    return list
  }, [lines])
  const pRef = useRef<THREE.InstancedMesh>(null!)
  const tmp = useMemo(() => new THREE.Vector3(), [])
  const m = useMemo(() => new THREE.Matrix4(), [])
  const col = useMemo(() => new THREE.Color(), [])
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    parts.forEach((p, i) => {
      const l = lines[p.line], f = flows[p.line] ?? 0
      if (Math.abs(f) < 0.3) { m.makeScale(0, 0, 0); pRef.current.setMatrixAt(i, m); return }
      const speed = 2.5 + Math.sqrt(Math.abs(f)) * 0.7
      let s = (p.off + t * speed) % l.len
      if (f < 0) s = l.len - s
      pointOn(l, s, tmp)
      m.makeTranslation(tmp.x, tmp.y, tmp.z)
      pRef.current.setMatrixAt(i, m)
      pRef.current.setColorAt(i, alarmLines.has(p.line) ? col.copy(ORANGE) : col.setRGB(0.5, 2.2, 2.6))
    })
    pRef.current.instanceMatrix.needsUpdate = true
    if (pRef.current.instanceColor) pRef.current.instanceColor.needsUpdate = true
  })

  return (
    <group>
      <lineSegments geometry={towerGeom}>
        <lineBasicMaterial color={[0.18, 0.62, 0.72]} transparent opacity={0.75} toneMapped={false} />
      </lineSegments>
      {wireGeoms.map((g, i) => (
        <lineSegments key={i} geometry={g}>
          <lineBasicMaterial color={alarmLines.has(i) ? ORANGE : new THREE.Color(0.28, 0.9, 1.05)} transparent opacity={alarmLines.has(i) ? 1 : 0.85} toneMapped={false} />
        </lineSegments>
      ))}
      <instancedMesh ref={pRef} args={[undefined, undefined, parts.length]} frustumCulled={false}>
        <sphereGeometry args={[0.17, 8, 8]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
    </group>
  )
}

const glass = (c = '#0d2730', o = 0.22) => <meshStandardMaterial color={c} transparent opacity={o} roughness={0.2} metalness={0.4} depthWrite={false} />

function Equipment({ d, edge }: { d: BusDef; edge: THREE.Color }) {
  const E = <Edges color={edge} threshold={15} />
  return (
    <group>
      <mesh position={[0, BUS_Y, -1.3]}><boxGeometry args={[5.6, 0.08, 0.08]} /><meshBasicMaterial color={edge} toneMapped={false} /></mesh>
      {[-2.2, 0, 2.2].map((x) => (
        <mesh key={x} position={[x, BUS_Y / 2, -1.3]}><boxGeometry args={[0.05, BUS_Y, 0.05]} /><meshBasicMaterial color={edge} toneMapped={false} /></mesh>
      ))}
      {d.role === 'generator' && (
        <group position={[-1.2, 1.25, 1.1]}>
          <mesh>{<cylinderGeometry args={[1.15, 1.15, 2.2, 18]} />}{glass()}{E}</mesh>
          <mesh position={[0, 1.3, 0]}><torusGeometry args={[0.55, 0.05, 6, 24]} /><meshBasicMaterial color={edge} toneMapped={false} /></mesh>
        </group>
      )}
      {d.role === 'condenser' && (
        <mesh position={[-1, 0.95, 1.1]} rotation={[0, 0, Math.PI / 2]}><cylinderGeometry args={[0.8, 0.8, 2.4, 16]} />{glass()}{E}</mesh>
      )}
      {d.role === 'capacitor' && [-1.6, -0.8, 0, 0.8].map((x) => (
        <mesh key={x} position={[x, 0.8, 1.3]}><boxGeometry args={[0.5, 1.2, 0.5]} />{glass()}{E}</mesh>
      ))}
      {(d.role === 'load' || d.role === 'capacitor') && (
        <mesh position={[2.0, 1.0, 1.3]}><boxGeometry args={[1.5, 1.6, 1.2]} />{glass()}{E}</mesh>
      )}
      {d.role === 'load' && (
        <mesh position={[-1.4, 1.0, 1.3]} rotation={[Math.PI, 0, 0]}><coneGeometry args={[0.6, 1.4, 4]} />{glass()}{E}</mesh>
      )}
      {d.role !== 'load' && d.role !== 'capacitor' && (
        <mesh position={[2.0, 0.9, 1.3]}><boxGeometry args={[1.4, 1.4, 1.1]} />{glass()}{E}</mesh>
      )}
    </group>
  )
}

function BusNode({ d, state, truth, selected, vm, onSelect }: {
  d: BusDef; state: BusVisual; truth: boolean; selected: boolean; vm: number | null; onSelect: (b: number) => void
}) {
  const ring = useRef<THREE.MeshBasicMaterial>(null!)
  const pulse = useRef<THREE.Mesh>(null!)
  const beam = useRef<THREE.Mesh>(null!)
  const edge = state === 'alarm' ? RED : state === 'injecting' ? AMBER : CYAN
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    const k = state === 'alarm' ? 0.6 + 0.4 * Math.sin(t * 6) : state === 'injecting' ? (Math.sin(t * 20) > 0 ? 1 : 0.3) : selected ? 0.9 : 0.45
    ring.current.color.copy(state === 'normal' ? (selected ? new THREE.Color(2, 2, 2) : CYAN) : edge).multiplyScalar(k)
    if (pulse.current) {
      const p = (t * 0.7) % 1
      pulse.current.visible = state === 'alarm'
      pulse.current.scale.setScalar(1 + p * 2.2)
      ;(pulse.current.material as THREE.MeshBasicMaterial).opacity = 0.7 * (1 - p)
    }
    if (beam.current) beam.current.visible = state === 'alarm'
  })
  const click = (e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); if (e.delta < 6) onSelect(d.bus) }
  return (
    <group position={[d.x, 0, d.z]}>
      <mesh position={[0, 0.18, 0]} onClick={click}
        onPointerOver={() => (document.body.style.cursor = 'pointer')} onPointerOut={() => (document.body.style.cursor = '')}>
        <cylinderGeometry args={[3.9, 3.9, 0.36, 6]} />
        <meshStandardMaterial color={state === 'alarm' ? '#3a0c0c' : '#0a1c24'} transparent opacity={0.85} roughness={0.3} metalness={0.5} />
        <Edges color={edge} />
      </mesh>
      <Equipment d={d} edge={edge} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.4, 0]}>
        <ringGeometry args={[4.3, 4.65, 6]} />
        <meshBasicMaterial ref={ring} toneMapped={false} />
      </mesh>
      {truth && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.42, 0]}>
          <ringGeometry args={[5.1, 5.35, 24, 1, 0, Math.PI * 2]} />
          <meshBasicMaterial color={AMBER} toneMapped={false} transparent opacity={0.9} wireframe />
        </mesh>
      )}
      <mesh ref={pulse} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.45, 0]} visible={false}>
        <ringGeometry args={[4.3, 4.6, 6]} />
        <meshBasicMaterial color={RED} toneMapped={false} transparent depthWrite={false} />
      </mesh>
      <mesh ref={beam} position={[0, 12, 0]} visible={false}>
        <cylinderGeometry args={[0.18, 0.5, 24, 10, 1, true]} />
        <meshBasicMaterial color={RED} toneMapped={false} transparent opacity={0.45} depthWrite={false} blending={THREE.AdditiveBlending} />
      </mesh>
      <mesh position={[0, 3, 0]} onClick={click}>
        <boxGeometry args={[8, 6, 8]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      <Html position={[0, 6.4, 0]} center zIndexRange={[10, 0]} style={{ pointerEvents: 'auto' }}>
        <button className={`node-tag st-${state} ${selected ? 'sel' : ''} ${truth ? 'truth' : ''}`} onClick={() => onSelect(d.bus)}>
          <b>B{d.bus}</b>
          <span className="v">{vm != null ? `${vm.toFixed(3)} pu` : '—'}</span>
          {state === 'injecting' && <span className="flag">INJECTING</span>}
          {state === 'alarm' && <span className="flag">FDI SUSPECTED</span>}
        </button>
      </Html>
    </group>
  )
}

function Controls({ resetKey, zoom, topView }: { resetKey: number; zoom?: { n: number; dir: 1 | -1 }; topView?: number }) {
  const ref = useRef<OrbitControlsImpl>(null!)
  const last = useRef(resetKey)
  const lastZoom = useRef(zoom?.n ?? 0)
  const lastTop = useRef(topView ?? 0)
  useFrame(({ camera }) => {
    if (zoom && lastZoom.current !== zoom.n) {
      lastZoom.current = zoom.n
      const t = ref.current.target
      const off = camera.position.clone().sub(t)
      const d = THREE.MathUtils.clamp(off.length() * (zoom.dir > 0 ? 0.8 : 1.25), 30, 220)
      camera.position.copy(t.clone().add(off.setLength(d)))
      ref.current.update()
    }
    if (topView !== undefined && lastTop.current !== topView) {
      lastTop.current = topView
      ref.current.target.set(4, 0, -2)
      camera.position.set(4, 150, 30)
      ref.current.update()
    }
    if (last.current !== resetKey) {
      last.current = resetKey
      camera.position.set(-26, 74, 82)
      ref.current.target.set(4, 0, -2)
      ref.current.update()
    }
  })
  return <OrbitControls ref={ref} makeDefault target={[4, 0, -2]} enableDamping dampingFactor={0.08} maxPolarAngle={1.3} minDistance={30} maxDistance={220} />
}

export default function Network3D(p: NetworkProps) {
  const lines = useMemo(buildLines, [])
  return (
    <Canvas dpr={p.quality === 'high' ? [1, 1.75] : 1} camera={{ position: [-26, 74, 82], fov: 38, near: 0.5, far: 1200 }}
      gl={{ antialias: true }} onPointerMissed={() => p.onSelect(null)}>
      <color attach="background" args={['#04080c']} />
      <fog attach="fog" args={['#04080c', 140, 320]} />
      <ambientLight intensity={0.5} />
      <directionalLight position={[40, 80, 30]} intensity={1.2} />
      <Grid position={[0, -0.02, 0]} infiniteGrid cellSize={2} cellThickness={0.5} cellColor="#0c2229" sectionSize={10}
        sectionThickness={1} sectionColor="#123844" fadeDistance={260} fadeStrength={1.4} />
      <mesh position={[3, -0.3, -2]}>
        <boxGeometry args={[118, 0.5, 96]} />
        <meshStandardMaterial color="#0a2129" transparent opacity={0.25} depthWrite={false} />
        <Edges color="#2c8fa0" />
      </mesh>
      <Network lines={lines} flows={p.flows} alarmLines={p.alarmLines} />
      {BUSES.map((d) => (
        <BusNode key={d.bus} d={d} state={p.busState[d.bus] ?? 'normal'} truth={p.truthBuses.includes(d.bus)}
          selected={p.selected === d.bus} vm={p.vm ? p.vm[d.bus - 1] : null} onSelect={p.onSelect} />
      ))}
      <Controls resetKey={p.resetKey} zoom={p.zoom} topView={p.topView} />
      {p.quality === 'high' ? (
        <EffectComposer multisampling={4}>
          <Bloom intensity={0.9} luminanceThreshold={0.85} luminanceSmoothing={0.2} mipmapBlur radius={0.6} />
        </EffectComposer>
      ) : <></>}
    </Canvas>
  )
}
