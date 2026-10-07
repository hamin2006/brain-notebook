'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from 'd3-force'
import { Maximize2, Minus, Plus, Search, Share2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useConceptGraph } from '@/lib/hooks/use-explore'
import { useWorkspaceStore } from '@/lib/stores/workspace-store'
import type { ConceptGraphData, GraphDocument } from '@/lib/api/explore'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { EmptyState } from '@/components/common/EmptyState'

// Document hues: evenly spaced around the wheel from the agent's iris, so neighbouring
// lectures never share a colour; lightness follows the theme.
export function documentHues(count: number, dark: boolean): string[] {
  const n = Math.max(count, 1)
  return Array.from({ length: n }, (_, i) => {
    const hue = (250 + (i * 360) / n) % 360
    return hslToHex(hue, dark ? 72 : 62, dark ? 66 : 46)
  })
}

function hslToHex(h: number, s: number, l: number): string {
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100)
  const f = (n: number) => {
    const k = (n + h / 30) % 12
    const c = l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))
    return Math.round(c * 255).toString(16).padStart(2, '0')
  }
  return `#${f(0)}${f(8)}${f(4)}`
}

interface Node extends SimulationNodeDatum {
  id: string
  name: string
  mentions: number
  documents: string[]
  home: string
  r: number
  doc: number
  rank: number
  // column the layout pulls it toward: between the documents that mention it, leaning to its home
  cx: number
}

interface Link extends SimulationLinkDatum<Node> {
  kind: 'relation' | 'co'
  label?: string | null
  weight: number
}

type Transform = { x: number; y: number; k: number }

interface Palette {
  docs: string[]
  ink: string
  faint: string
  bg: string
  iris: string
  font: string
  mono: string
}

function readPalette(documents: number): Palette {
  const css = getComputedStyle(document.documentElement)
  const v = (name: string) => css.getPropertyValue(name).trim() || '#888'
  return {
    docs: documentHues(documents, document.documentElement.classList.contains('dark')),
    ink: v('--ink'),
    faint: v('--ink-faint'),
    bg: v('--bg'),
    iris: v('--teal'),
    font: getComputedStyle(document.body).fontFamily || 'system-ui, sans-serif',
    mono: getComputedStyle(document.body).getPropertyValue('--font-geist-mono').trim() || 'ui-monospace, monospace',
  }
}

export function withAlpha(hex: string, alpha: number): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!m) return hex
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

const SPACING = 300 // world units between document columns

function buildGraph(data: ConceptGraphData) {
  const docIndex = new Map(data.documents.map((d, i) => [d.id, i]))
  const center = (data.documents.length - 1) / 2
  const degree = new Map<string, number>()
  for (const e of data.edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + (e.kind === 'relation' ? 2 : 1))
    degree.set(e.target, (degree.get(e.target) ?? 0) + (e.kind === 'relation' ? 2 : 1))
  }
  const nodes: Node[] = data.nodes.map((n) => {
    const doc = docIndex.get(n.home) ?? 0
    const spread = n.documents.map((d) => docIndex.get(d) ?? doc)
    const column = (doc * 2 + spread.reduce((a, b) => a + b, 0)) / (2 + spread.length)
    return {
      ...n,
      doc,
      cx: (column - center) * SPACING,
      r: Math.min(20, 3.5 + Math.sqrt(n.mentions) * 2.4),
      rank: n.documents.length * 4 + n.mentions + (degree.get(n.id) ?? 0) * 0.5,
      x: (column - center) * SPACING + (Math.random() - 0.5) * 120,
      y: (Math.random() - 0.5) * 360,
    }
  })
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const links: Link[] = data.edges
    .filter((e) => byId.has(e.source) && byId.has(e.target))
    .map((e) => ({ source: e.source, target: e.target, kind: e.kind, label: e.label, weight: e.weight }))
  const neighbors = new Map<string, Set<string>>()
  for (const l of links) {
    const a = l.source as string
    const b = l.target as string
    if (!neighbors.has(a)) neighbors.set(a, new Set())
    if (!neighbors.has(b)) neighbors.set(b, new Set())
    neighbors.get(a)!.add(b)
    neighbors.get(b)!.add(a)
  }
  // Labels everyone sees first: the most central concepts
  const labelled = new Set([...nodes].sort((a, b) => b.rank - a.rank).slice(0, 36).map((n) => n.id))
  return { nodes, links, byId, neighbors, labelled, center }
}

/**
 * The notebook's concept graph as a living map: concepts drift to the document
 * that introduces them (left to right in course order), stated relations pull
 * hard, shared sections pull gently. Hover to focus, click to open the concept.
 */
export function ConceptGraph2D({ notebookId }: { notebookId: string }) {
  const { t } = useTranslation()
  const { data, isLoading } = useConceptGraph(notebookId)
  const evidence = useWorkspaceStore((s) => s.evidence)
  const openEvidence = useWorkspaceStore((s) => s.openEvidence)
  const selectedId = evidence?.kind === 'concept' ? evidence.conceptId : null

  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const transformRef = useRef<Transform>({ x: 0, y: 0, k: 0.5 })
  const sizeRef = useRef({ w: 800, h: 600 })
  const paletteRef = useRef<Palette | null>(null)
  const simRef = useRef<Simulation<Node, Link> | null>(null)
  const frameRef = useRef<number | null>(null)
  const fittedRef = useRef(false)
  const hoverRef = useRef<string | null>(null)
  const [hover, setHover] = useState<{ node: Node; x: number; y: number } | null>(null)
  const [showCo, setShowCo] = useState(true)
  const [docFilter, setDocFilter] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const stateRef = useRef({ selectedId, showCo, docFilter })
  stateRef.current = { selectedId, showCo, docFilter }

  const graph = useMemo(() => (data ? buildGraph(data) : null), [data])

  const draw = useCallback(() => {
    frameRef.current = null
    const canvas = canvasRef.current
    if (!canvas || !graph) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const pal = paletteRef.current ?? (paletteRef.current = readPalette(data!.documents.length))
    const { w, h } = sizeRef.current
    const dpr = window.devicePixelRatio || 1
    const { x, y, k } = transformRef.current
    const { selectedId: selected, showCo: co, docFilter: only } = stateRef.current
    const focus = hoverRef.current ?? selected
    const near = focus ? graph.neighbors.get(focus) ?? new Set<string>() : null
    const onlyDoc = only !== null ? data!.documents[only]?.id : null
    const inFilter = (n: Node) => !onlyDoc || n.documents.includes(onlyDoc)

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)
    ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * x, dpr * y)

    // Document columns: a faint band and title per lecture, the course as a timeline
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    data!.documents.forEach((doc, i) => {
      const cx = (i - graph.center) * SPACING
      const color = pal.docs[i % pal.docs.length]
      ctx.fillStyle = withAlpha(color, only === i ? 0.09 : 0.035)
      ctx.fillRect(cx - SPACING / 2 + 6, -2000, SPACING - 12, 4000)
      ctx.font = `600 ${12 / k}px ${pal.font}`
      ctx.fillStyle = withAlpha(color, 0.9)
      ctx.fillText(shortTitle(doc).toUpperCase(), cx, (76 - y) / k)
    })

    // Edges: co-occurrence as hairlines, relations as stronger arcs
    for (const l of graph.links) {
      if (l.kind === 'co' && !co) continue
      const a = l.source as Node
      const b = l.target as Node
      const touched = focus && (a.id === focus || b.id === focus)
      if (only !== null && !(inFilter(a) && inFilter(b))) continue
      let alpha = l.kind === 'relation' ? 0.32 : 0.07
      if (focus) alpha = touched ? (l.kind === 'relation' ? 0.9 : 0.45) : alpha * 0.25
      ctx.strokeStyle = l.kind === 'relation' ? withAlpha(pal.docs[a.doc % pal.docs.length], alpha) : withAlpha(pal.ink, alpha)
      ctx.lineWidth = (l.kind === 'relation' ? 1.3 : 0.8) / Math.sqrt(k)
      ctx.beginPath()
      ctx.moveTo(a.x!, a.y!)
      if (l.kind === 'relation') {
        // a gentle curve reads as a directed relation
        const mx = (a.x! + b.x!) / 2 + (b.y! - a.y!) * 0.12
        const my = (a.y! + b.y!) / 2 - (b.x! - a.x!) * 0.12
        ctx.quadraticCurveTo(mx, my, b.x!, b.y!)
        if (touched && l.label) {
          ctx.font = `${10.5 / k}px ${pal.mono}`
          ctx.lineWidth = 3 / k
          ctx.strokeStyle = pal.bg
          ctx.stroke()
          ctx.beginPath()
          ctx.strokeStyle = withAlpha(pal.docs[a.doc % pal.docs.length], alpha)
          ctx.lineWidth = 1.3 / Math.sqrt(k)
          ctx.moveTo(a.x!, a.y!)
          ctx.quadraticCurveTo(mx, my, b.x!, b.y!)
          ctx.stroke()
          ctx.strokeStyle = pal.bg
          ctx.lineWidth = 3 / k
          ctx.strokeText(l.label, mx, my)
          ctx.fillStyle = pal.faint
          ctx.fillText(l.label, mx, my)
          continue
        }
      } else {
        ctx.lineTo(b.x!, b.y!)
      }
      ctx.stroke()
    }

    // Nodes
    for (const n of graph.nodes) {
      const dim = (focus && n.id !== focus && !near!.has(n.id)) || (only !== null && !inFilter(n))
      const color = pal.docs[n.doc % pal.docs.length]
      const isFocus = n.id === focus || n.id === selected
      if (!dim && n.rank > 30) {
        ctx.shadowColor = withAlpha(color, 0.6)
        ctx.shadowBlur = 14 * k
      }
      ctx.beginPath()
      ctx.arc(n.x!, n.y!, n.r, 0, Math.PI * 2)
      ctx.fillStyle = dim ? withAlpha(color, 0.12) : color
      ctx.fill()
      ctx.shadowBlur = 0
      if (n.documents.length > 1 && !dim) {
        // a ring for concepts that span documents
        ctx.lineWidth = 1.5 / k
        ctx.strokeStyle = withAlpha(pal.bg, 0.9)
        ctx.stroke()
        ctx.beginPath()
        ctx.arc(n.x!, n.y!, n.r + 2.5 / k + 1, 0, Math.PI * 2 * Math.min(1, n.documents.length / data!.documents.length))
        ctx.strokeStyle = withAlpha(color, 0.55)
        ctx.lineWidth = 1.4 / k
        ctx.stroke()
      }
      if (isFocus) {
        ctx.beginPath()
        ctx.arc(n.x!, n.y!, n.r + 5 / k, 0, Math.PI * 2)
        ctx.strokeStyle = pal.ink
        ctx.lineWidth = 1.8 / k
        ctx.stroke()
      }
    }

    // Labels: central concepts always, more as you zoom in, the focus and its neighbours.
    // Drawn most important first; a label that would overlap one already drawn is skipped.
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    const candidates = graph.nodes
      .filter((n) => {
        if (only !== null && !inFilter(n)) return false
        const isNear = focus ? n.id === focus || near!.has(n.id) : false
        return isNear || n.id === selected || (!focus && (graph.labelled.has(n.id) || n.r * k > 9))
      })
      .sort((a, b) => {
        const pa = a.id === focus || a.id === selected ? 1e9 : a.rank
        const pb = b.id === focus || b.id === selected ? 1e9 : b.rank
        return pb - pa
      })
    const placed: [number, number, number, number][] = []
    for (const n of candidates) {
      const important = n.id === focus || n.id === selected
      const size = (important ? 13.5 : 11.5) / Math.min(Math.max(k, 0.45), 1.6)
      ctx.font = `${important ? 600 : 500} ${size}px ${pal.font}`
      const width = ctx.measureText(n.name).width
      const box: [number, number, number, number] = [n.x! - width / 2 - 2 / k, n.y! + n.r + 2 / k, width + 4 / k, size + 2 / k]
      const overlaps = placed.some(([x0, y0, w0, h0]) => box[0] < x0 + w0 && x0 < box[0] + box[2] && box[1] < y0 + h0 && y0 < box[1] + box[3])
      if (overlaps && !important) continue
      placed.push(box)
      const isNear = focus ? n.id === focus || near!.has(n.id) : false
      ctx.lineWidth = 3.5 / k
      ctx.strokeStyle = withAlpha(pal.bg, 0.92)
      ctx.strokeText(n.name, n.x!, n.y! + n.r + 3 / k)
      ctx.fillStyle = focus && !isNear ? pal.faint : pal.ink
      ctx.fillText(n.name, n.x!, n.y! + n.r + 3 / k)
    }
  }, [graph, data])

  const requestDraw = useCallback(() => {
    if (frameRef.current === null) frameRef.current = requestAnimationFrame(draw)
  }, [draw])

  const fit = useCallback((animate = true) => {
    if (!graph?.nodes.length) return
    const { w, h } = sizeRef.current
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    // keep every document column (and its title) in view
    minX = -graph.center * SPACING - SPACING / 2
    maxX = graph.center * SPACING + SPACING / 2
    for (const n of graph.nodes) {
      minX = Math.min(minX, n.x! - n.r); maxX = Math.max(maxX, n.x! + n.r)
      minY = Math.min(minY, n.y! - n.r); maxY = Math.max(maxY, n.y! + n.r)
    }
    const k = Math.min(2, Math.max(0.15, Math.min((w - 80) / (maxX - minX), (h - 120) / (maxY - minY))))
    const target = { k, x: w / 2 - ((minX + maxX) / 2) * k, y: h / 2 + 20 - ((minY + maxY) / 2) * k }
    flyTo(target, animate)
  }, [graph]) // eslint-disable-line react-hooks/exhaustive-deps

  const flyTo = useCallback((target: Transform, animate = true) => {
    if (!animate) {
      transformRef.current = target
      requestDraw()
      return
    }
    const start = { ...transformRef.current }
    const t0 = performance.now()
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / 550)
      const e = 1 - Math.pow(1 - p, 3)
      transformRef.current = {
        x: start.x + (target.x - start.x) * e,
        y: start.y + (target.y - start.y) * e,
        k: start.k + (target.k - start.k) * e,
      }
      draw()
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [draw, requestDraw])

  // Simulation
  useEffect(() => {
    if (!graph) return
    fittedRef.current = false
    const sim = forceSimulation<Node, Link>(graph.nodes)
      .force('link', forceLink<Node, Link>(graph.links)
        .id((d) => d.id)
        .distance((l) => (l.kind === 'relation' ? 45 : 70))
        .strength((l) => (l.kind === 'relation' ? 0.35 : Math.min(0.12, 0.03 * l.weight))))
      .force('charge', forceManyBody<Node>().strength((d) => -40 - d.r * 8).distanceMax(450))
      .force('collide', forceCollide<Node>((d) => d.r + 3))
      .force('x', forceX<Node>((d) => d.cx).strength(0.09))
      .force('y', forceY<Node>(0).strength(0.04))
      .velocityDecay(0.32)
    sim.on('tick', () => {
      if (!fittedRef.current && sim.alpha() < 0.5) {
        fittedRef.current = true
        fit(true)
      }
      requestDraw()
    })
    simRef.current = sim
    return () => {
      sim.stop()
    }
  }, [graph, fit, requestDraw])

  // Size and theme
  useEffect(() => {
    const el = containerRef.current
    const canvas = canvasRef.current
    if (!el || !canvas) return
    const resize = () => {
      const { width, height } = el.getBoundingClientRect()
      const dpr = window.devicePixelRatio || 1
      sizeRef.current = { w: width, h: height }
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      requestDraw()
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(el)
    const mo = new MutationObserver(() => {
      paletteRef.current = null
      requestDraw()
    })
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    return () => {
      ro.disconnect()
      mo.disconnect()
    }
  }, [requestDraw, graph])

  useEffect(() => requestDraw(), [selectedId, showCo, docFilter, requestDraw])

  // Pointer: pan, drag nodes, hover, click; wheel zoom
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !graph) return
    const toWorld = (cx: number, cy: number) => {
      const { x, y, k } = transformRef.current
      return { x: (cx - x) / k, y: (cy - y) / k }
    }
    const pick = (cx: number, cy: number) => {
      const p = toWorld(cx, cy)
      const k = transformRef.current.k
      let best: Node | null = null
      let bestD = Infinity
      for (const n of graph.nodes) {
        const d = Math.hypot(n.x! - p.x, n.y! - p.y)
        if (d < n.r + 6 / k && d < bestD) {
          best = n
          bestD = d
        }
      }
      return best
    }
    let mode: 'pan' | 'drag' | null = null
    let dragged: Node | null = null
    let startX = 0, startY = 0, moved = false
    const local = (e: PointerEvent | WheelEvent) => {
      const rect = canvas.getBoundingClientRect()
      return { cx: e.clientX - rect.left, cy: e.clientY - rect.top }
    }
    const down = (e: PointerEvent) => {
      const { cx, cy } = local(e)
      startX = cx; startY = cy; moved = false
      dragged = pick(cx, cy)
      mode = dragged ? 'drag' : 'pan'
      canvas.setPointerCapture(e.pointerId)
      if (dragged) {
        dragged.fx = dragged.x
        dragged.fy = dragged.y
        simRef.current?.alphaTarget(0.15).restart()
      }
    }
    const move = (e: PointerEvent) => {
      const { cx, cy } = local(e)
      if (mode) {
        if (Math.hypot(cx - startX, cy - startY) > 3) moved = true
        if (mode === 'pan') {
          transformRef.current = { ...transformRef.current, x: transformRef.current.x + e.movementX, y: transformRef.current.y + e.movementY }
          requestDraw()
        } else if (dragged) {
          const p = toWorld(cx, cy)
          dragged.fx = p.x
          dragged.fy = p.y
        }
        return
      }
      const n = pick(cx, cy)
      const id = n?.id ?? null
      canvas.style.cursor = n ? 'pointer' : 'grab'
      if (id !== hoverRef.current) {
        hoverRef.current = id
        requestDraw()
      }
      setHover(n ? { node: n, x: cx, y: cy } : null)
    }
    const up = (e: PointerEvent) => {
      const { cx, cy } = local(e)
      if (dragged) {
        dragged.fx = null
        dragged.fy = null
        simRef.current?.alphaTarget(0)
      }
      if (!moved) {
        const n = pick(cx, cy)
        if (n) openEvidence({ kind: 'concept', conceptId: n.id, name: n.name })
      }
      mode = null
      dragged = null
    }
    const leave = () => {
      hoverRef.current = null
      setHover(null)
      requestDraw()
    }
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      const { cx, cy } = local(e)
      const { x, y, k } = transformRef.current
      const nk = Math.min(4, Math.max(0.12, k * Math.exp(-e.deltaY * 0.0016)))
      transformRef.current = { k: nk, x: cx - ((cx - x) / k) * nk, y: cy - ((cy - y) / k) * nk }
      requestDraw()
    }
    canvas.addEventListener('pointerdown', down)
    canvas.addEventListener('pointermove', move)
    canvas.addEventListener('pointerup', up)
    canvas.addEventListener('pointerleave', leave)
    canvas.addEventListener('wheel', wheel, { passive: false })
    return () => {
      canvas.removeEventListener('pointerdown', down)
      canvas.removeEventListener('pointermove', move)
      canvas.removeEventListener('pointerup', up)
      canvas.removeEventListener('pointerleave', leave)
      canvas.removeEventListener('wheel', wheel)
    }
  }, [graph, openEvidence, requestDraw])

  const zoomBy = (factor: number) => {
    const { w, h } = sizeRef.current
    const { x, y, k } = transformRef.current
    const nk = Math.min(4, Math.max(0.12, k * factor))
    flyTo({ k: nk, x: w / 2 - ((w / 2 - x) / k) * nk, y: h / 2 - ((h / 2 - y) / k) * nk })
  }

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q || !graph) return []
    return graph.nodes.filter((n) => n.name.toLowerCase().includes(q)).sort((a, b) => b.rank - a.rank).slice(0, 8)
  }, [query, graph])

  const focusNode = (n: Node) => {
    const { w, h } = sizeRef.current
    const k = Math.max(transformRef.current.k, 1.3)
    flyTo({ k, x: w / 2 - n.x! * k, y: h / 2 - n.y! * k })
    openEvidence({ kind: 'concept', conceptId: n.id, name: n.name })
    setQuery('')
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }
  if (!data || data.nodes.length === 0) {
    return <EmptyState icon={Share2} title={t('brain.noConcepts')} description={t('brain.noConceptsDesc')} />
  }

  const relations = data.edges.filter((e) => e.kind === 'relation').length
  const pal = typeof window !== 'undefined' ? paletteRef.current ?? readPalette(data.documents.length) : null

  return (
    <div ref={containerRef} className="relative h-full min-h-0 flex-1 overflow-hidden bg-background paper-dots">
      <canvas ref={canvasRef} className="absolute inset-0 cursor-grab touch-none" aria-label={t('brain.graphTitle')} role="img" />

      {/* Search */}
      <div className="absolute left-4 top-4 w-64">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && matches[0] && focusNode(matches[0])}
            placeholder={t('brain.findConcept')}
            aria-label={t('brain.findConcept')}
            className="h-9 w-full rounded-xl border bg-card/90 pl-8 pr-3 text-[13px] shadow-lift outline-none backdrop-blur focus:border-iris/50"
          />
        </div>
        {matches.length > 0 && (
          <div className="mt-1.5 overflow-hidden rounded-xl border bg-popover p-1 shadow-pop">
            {matches.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => focusNode(n)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-accent"
              >
                <span className="size-2 shrink-0 rounded-full" style={{ background: pal?.docs[n.doc % pal.docs.length] }} />
                <span className="flex-1 truncate">{n.name}</span>
                <span className="font-mono text-[10px] text-muted-foreground">{n.mentions}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Stats and toggles */}
      <div className="absolute right-4 top-4 flex items-center gap-2">
        <span className="rounded-full border bg-card/90 px-3 py-1.5 font-mono text-[11px] text-muted-foreground shadow-soft backdrop-blur">
          {t('brain.graphStats', { shown: data.nodes.length, total: data.total_concepts, relations })}
        </span>
        <button
          type="button"
          onClick={() => setShowCo((v) => !v)}
          aria-pressed={showCo}
          className={cn(
            'rounded-full border px-3 py-1.5 text-[11px] font-medium shadow-soft backdrop-blur transition-colors',
            showCo ? 'bg-card/90 text-foreground' : 'bg-transparent text-muted-foreground'
          )}
        >
          {t('brain.graphCoLinks')}
        </button>
      </div>

      {/* Zoom */}
      <div className="absolute bottom-4 right-4 flex flex-col overflow-hidden rounded-xl border bg-card/90 shadow-lift backdrop-blur">
        <button type="button" onClick={() => zoomBy(1.4)} className="p-2 hover:bg-accent" aria-label={t('brain.zoomIn')}><Plus className="h-4 w-4" /></button>
        <button type="button" onClick={() => zoomBy(1 / 1.4)} className="border-y p-2 hover:bg-accent" aria-label={t('brain.zoomOut')}><Minus className="h-4 w-4" /></button>
        <button type="button" onClick={() => fit(true)} className="p-2 hover:bg-accent" aria-label={t('brain.fitGraph')}><Maximize2 className="h-4 w-4" /></button>
      </div>

      {/* Legend: documents in course order */}
      <div className="absolute bottom-4 left-4 max-w-[calc(100%-6rem)] rounded-xl border bg-card/90 p-2 shadow-lift backdrop-blur">
        <p className="px-1.5 pb-1 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{t('brain.graphLegend')}</p>
        <div className="flex flex-wrap gap-1">
          {data.documents.map((doc, i) => (
            <button
              key={doc.id}
              type="button"
              onClick={() => setDocFilter((f) => (f === i ? null : i))}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11.5px] transition-colors',
                docFilter === i ? 'bg-accent text-foreground' : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground',
                docFilter !== null && docFilter !== i && 'opacity-50'
              )}
              title={doc.title}
            >
              <span className="size-2.5 rounded-full" style={{ background: pal?.docs[i % pal.docs.length] }} />
              {shortTitle(doc)}
            </button>
          ))}
        </div>
      </div>

      {/* Hover card */}
      {hover && (
        <div
          className="pointer-events-none absolute z-10 w-60 rounded-xl border bg-popover p-3 shadow-pop animate-in fade-in-0 zoom-in-95"
          style={{ left: Math.min(hover.x + 14, sizeRef.current.w - 250), top: Math.min(hover.y + 14, sizeRef.current.h - 120) }}
        >
          <p className="text-[13px] font-semibold leading-snug">{hover.node.name}</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {t('brain.conceptSpread', { documents: hover.node.documents.length, mentions: hover.node.mentions })}
          </p>
          <div className="mt-2 flex flex-wrap gap-1">
            {hover.node.documents.map((id) => {
              const i = data.documents.findIndex((d) => d.id === id)
              return (
                <span key={id} className="flex items-center gap-1 rounded-full bg-surface-recessed px-1.5 py-0.5 text-[10px]">
                  <span className="size-1.5 rounded-full" style={{ background: pal?.docs[i % pal.docs.length] }} />
                  {i >= 0 ? shortTitle(data.documents[i]) : ''}
                </span>
              )
            })}
          </div>
          <p className="mt-2 text-[10.5px] text-iris">{t('brain.graphClickHint')}</p>
        </div>
      )}
    </div>
  )
}

/** "AI 360 Lecture 2 - Universality and Backprop (1).pdf" -> "Lecture 2". */
export function shortTitle(doc: GraphDocument): string {
  const lecture = /(lecture|week|chapter|part|unit)\s*(\d+)/i.exec(doc.title)
  if (lecture) return `${lecture[1][0].toUpperCase()}${lecture[1].slice(1).toLowerCase()} ${lecture[2]}`
  const clean = doc.title.replace(/\.(pdf|pptx?|docx?)$/i, '').replace(/\s*\(\d+\)$/, '')
  return clean.length > 22 ? `${clean.slice(0, 21)}…` : clean
}
