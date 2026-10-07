'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { Pause, Play, Search } from 'lucide-react'
import type { ForceGraph3DInstance } from '3d-force-graph'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useConceptGraph } from '@/lib/hooks/use-explore'
import { useWorkspaceStore } from '@/lib/stores/workspace-store'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { documentHues, shortTitle, withAlpha } from './ConceptGraph'

const SPACING = 260

interface Node3D {
  id: string
  name: string
  mentions: number
  documents: string[]
  doc: number
  cx: number
  rank: number
  x?: number
  y?: number
  z?: number
}

interface Link3D {
  source: string | Node3D
  target: string | Node3D
  kind: 'relation' | 'co'
  label?: string | null
}

const endId = (end: string | Node3D) => (typeof end === 'string' ? end : end.id)

function escapeHtml(text: string) {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
}

/**
 * The concept graph in 3D (WebGL): the same data and the same course-order
 * x-axis as the 2D map, orbiting slowly until you take the controls. Hover
 * lights a concept's neighbourhood and sends particles along its relations;
 * click flies to it and opens it in the evidence panel.
 */
export function ConceptGraph3D({ notebookId }: { notebookId: string }) {
  const { t } = useTranslation()
  const { data, isLoading } = useConceptGraph(notebookId)
  const evidence = useWorkspaceStore((s) => s.evidence)
  const openEvidence = useWorkspaceStore((s) => s.openEvidence)
  const selectedId = evidence?.kind === 'concept' ? evidence.conceptId : null

  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<ForceGraph3DInstance | null>(null)
  const focusRef = useRef<{ hover: string | null; selected: string | null; doc: number | null }>({ hover: null, selected: null, doc: null })
  const [ready, setReady] = useState(false)
  const [spinning, setSpinning] = useState(true)
  const [showCo, setShowCo] = useState(false)
  const [docFilter, setDocFilter] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [dark, setDark] = useState(false)
  const refreshRef = useRef<() => void>(() => {})
  const flyRef = useRef<(n: Node3D) => void>(() => {})
  const spinRef = useRef<(on: boolean) => void>(() => {})
  const showCoRef = useRef(showCo)

  const model = useMemo(() => {
    if (!data) return null
    const docIndex = new Map(data.documents.map((d, i) => [d.id, i]))
    const center = (data.documents.length - 1) / 2
    const nodes: Node3D[] = data.nodes.map((n) => {
      const doc = docIndex.get(n.home) ?? 0
      const spread = n.documents.map((d) => docIndex.get(d) ?? doc)
      const column = (doc * 2 + spread.reduce((a, b) => a + b, 0)) / (2 + spread.length)
      return {
        id: n.id,
        name: n.name,
        mentions: n.mentions,
        documents: n.documents,
        doc,
        cx: (column - center) * SPACING,
        rank: n.documents.length * 4 + n.mentions,
      }
    })
    const ids = new Set(nodes.map((n) => n.id))
    const links: Link3D[] = data.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({ source: e.source, target: e.target, kind: e.kind, label: e.label }))
    const neighbors = new Map<string, Set<string>>()
    for (const l of links) {
      const a = endId(l.source)
      const b = endId(l.target)
      if (!neighbors.has(a)) neighbors.set(a, new Set())
      if (!neighbors.has(b)) neighbors.set(b, new Set())
      neighbors.get(a)!.add(b)
      neighbors.get(b)!.add(a)
    }
    const labelled = new Set([...nodes].sort((a, b) => b.rank - a.rank).slice(0, 28).map((n) => n.id))
    return { nodes, links, neighbors, labelled }
  }, [data])

  // Build the WebGL scene once per graph
  useEffect(() => {
    const el = containerRef.current
    if (!el || !model || !data) return
    let disposed = false
    let graph: ForceGraph3DInstance | null = null
    let ro: ResizeObserver | null = null
    let mo: MutationObserver | null = null

    ;(async () => {
      const [{ default: ForceGraph3D }, { CSS2DRenderer, CSS2DObject }, { forceX }, { UnrealBloomPass }] = await Promise.all([
        import('3d-force-graph'),
        import('three/examples/jsm/renderers/CSS2DRenderer.js'),
        import('d3-force-3d'),
        import('three/examples/jsm/postprocessing/UnrealBloomPass.js'),
      ])
      if (disposed) return

      const css = getComputedStyle(document.documentElement)
      const isDark = () => document.documentElement.classList.contains('dark')
      let hues = documentHues(data.documents.length, isDark())
      let ink = css.getPropertyValue('--ink').trim() || '#888'
      let bg = css.getPropertyValue('--bg').trim() || '#000'

      const focusOf = () => focusRef.current.hover ?? focusRef.current.selected
      const lit = (id: string) => {
        const focus = focusOf()
        const doc = focusRef.current.doc
        const node = model.nodes.find((n) => n.id === id)
        if (doc !== null && node && !node.documents.includes(data.documents[doc]?.id)) return false
        return !focus || id === focus || !!model.neighbors.get(focus)?.has(id)
      }
      const touches = (l: Link3D) => {
        const focus = focusOf()
        return !!focus && (endId(l.source) === focus || endId(l.target) === focus)
      }

      // Label elements currently on screen; CSS2DRenderer leaves an element in the DOM when
      // its object is replaced, so a refresh removes the old ones itself
      const labels = new Set<HTMLElement>()

      // Labels are HTML over the scene: crisp, themed, and untouched by the glow
      graph = new ForceGraph3D(el, { controlType: 'orbit', extraRenderers: [new CSS2DRenderer() as never] })
      graph
        .backgroundColor('rgba(0,0,0,0)')
        .showNavInfo(false)
        .width(el.clientWidth)
        .height(el.clientHeight)
        .nodeId('id')
        .nodeVal((n) => 1 + Math.sqrt((n as Node3D).mentions) * 1.6)
        .nodeRelSize(3.2)
        .nodeResolution(18)
        .nodeOpacity(0.95)
        .nodeColor((n) => {
          const node = n as Node3D
          return lit(node.id) ? hues[node.doc % hues.length] : withAlpha(hues[node.doc % hues.length], isDark() ? 0.12 : 0.18)
        })
        .nodeLabel((n) => {
          const node = n as Node3D
          const docs = node.documents
            .map((id) => {
              const i = data.documents.findIndex((d) => d.id === id)
              return `<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 4px 0 0"><span style="width:6px;height:6px;border-radius:9px;background:${hues[i % hues.length]}"></span>${escapeHtml(shortTitle(data.documents[i]))}</span>`
            })
            .join('')
          return `<div class="graph3d-tip"><b>${escapeHtml(node.name)}</b><div class="graph3d-tip-sub">${escapeHtml(t('brain.conceptSpread', { documents: node.documents.length, mentions: node.mentions }))}</div><div>${docs}</div></div>`
        })
        .nodeThreeObjectExtend(true)
        .nodeThreeObject((n) => {
          const node = n as Node3D
          const focus = focusOf()
          const isFocus = node.id === focus
          const near = !!focus && !!model.neighbors.get(focus)?.has(node.id)
          if (!isFocus && !near && !(model.labelled.has(node.id) && !focus)) {
            return undefined as unknown as never
          }
          const wrap = document.createElement('div')
          const label = document.createElement('span')
          label.textContent = node.name
          label.className = cn('graph3d-label', isFocus && 'is-focus', !lit(node.id) && 'is-dim')
          label.style.marginTop = `${10 + Math.sqrt(node.mentions) * 3}px`
          wrap.appendChild(label)
          labels.add(wrap)
          return new CSS2DObject(wrap) as never
        })
        .linkSource('source')
        .linkTarget('target')
        .linkVisibility((l) => (l as Link3D).kind === 'relation' || showCoRef.current)
        .linkColor((l) => {
          const link = l as Link3D
          const src = model.nodes.find((n) => n.id === endId(link.source))
          if (link.kind === 'co') return withAlpha(ink, touches(link) ? 0.35 : 0.08)
          const color = hues[(src?.doc ?? 0) % hues.length]
          return focusOf() ? (touches(link) ? color : withAlpha(color, 0.06)) : withAlpha(color, 0.45)
        })
        .linkOpacity(0.9)
        .linkWidth((l) => ((l as Link3D).kind === 'relation' ? (touches(l as Link3D) ? 0.7 : 0.35) : 0))
        .linkCurvature((l) => ((l as Link3D).kind === 'relation' ? 0.18 : 0))
        .linkDirectionalParticles((l) => ((l as Link3D).kind === 'relation' && touches(l as Link3D) ? 3 : 0))
        .linkDirectionalParticleWidth(1.8)
        .linkDirectionalParticleSpeed(0.008)
        .linkDirectionalParticleColor((l) => {
          const src = model.nodes.find((n) => n.id === endId((l as Link3D).source))
          return hues[(src?.doc ?? 0) % hues.length]
        })
        .onNodeHover((n) => {
          focusRef.current.hover = (n as Node3D | null)?.id ?? null
          el.style.cursor = n ? 'pointer' : 'grab'
          refresh()
        })
        .onNodeClick((n) => {
          const node = n as Node3D
          flyTo(node)
          openEvidence({ kind: 'concept', conceptId: node.id, name: node.name })
        })
        .onBackgroundClick(() => {
          focusRef.current.hover = null
          refresh()
        })
        .cooldownTicks(220)
        .d3VelocityDecay(0.3)
        .graphData({ nodes: model.nodes, links: model.links })

      graph.d3Force('x', forceX<Node3D>((n) => n.cx).strength(0.08) as never)
      const charge = graph.d3Force('charge') as unknown as { strength: (s: number) => void; distanceMax?: (d: number) => void }
      charge?.strength(-55)
      const link = graph.d3Force('link') as unknown as { distance: (fn: (l: Link3D) => number) => void }
      link?.distance((l) => (l.kind === 'relation' ? 40 : 70))

      let fitted = false
      setTimeout(() => graph?.zoomToFit(800, 20), 1800)
      graph.onEngineStop(() => {
        if (!fitted && graph) {
          fitted = true
          graph.zoomToFit(900, 20)
        }
      })

      // Glow in the dark theme
      const applyBloom = () => {
        if (!graph) return
        const composer = graph.postProcessingComposer()
        while (composer.passes.length > 1) composer.removePass(composer.passes[composer.passes.length - 1])
        if (isDark()) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const bloom = new UnrealBloomPass(undefined as any, 0.55, 0.35, 0.2)
          composer.addPass(bloom)
        }
      }
      applyBloom()

      // Slow orbit until the user takes over
      const controls = graph.controls() as { autoRotate: boolean; autoRotateSpeed: number; addEventListener: (e: string, fn: () => void) => void }
      controls.autoRotate = true
      controls.autoRotateSpeed = 0.55
      controls.addEventListener('start', () => {
        controls.autoRotate = false
        setSpinning(false)
      })

      function refresh() {
        if (!graph) return
        for (const wrap of labels) wrap.remove()
        labels.clear()
        graph
          .nodeColor(graph.nodeColor())
          .nodeThreeObject(graph.nodeThreeObject())
          .linkColor(graph.linkColor())
          .linkWidth(graph.linkWidth())
          .linkDirectionalParticles(graph.linkDirectionalParticles())
      }
      function flyTo(node: Node3D) {
        if (!graph || node.x === undefined) return
        const distance = 140
        const ratio = 1 + distance / Math.max(1, Math.hypot(node.x!, node.y!, node.z!))
        controls.autoRotate = false
        setSpinning(false)
        graph.cameraPosition({ x: node.x! * ratio, y: node.y! * ratio, z: node.z! * ratio }, { x: node.x!, y: node.y!, z: node.z! }, 1400)
      }
      refreshRef.current = refresh
      flyRef.current = flyTo
      spinRef.current = (on: boolean) => {
        controls.autoRotate = on
      }

      ro = new ResizeObserver(() => graph?.width(el.clientWidth).height(el.clientHeight))
      ro.observe(el)
      mo = new MutationObserver(() => {
        hues = documentHues(data.documents.length, isDark())
        const css2 = getComputedStyle(document.documentElement)
        ink = css2.getPropertyValue('--ink').trim() || ink
        bg = css2.getPropertyValue('--bg').trim() || bg
        setDark(isDark())
        applyBloom()
        refresh()
      })
      mo.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
      setDark(isDark())
      graphRef.current = graph
      setReady(true)
    })()

    return () => {
      disposed = true
      ro?.disconnect()
      mo?.disconnect()
      if (graph) {
        graph.pauseAnimation()
        graph._destructor()
        el.innerHTML = ''
      }
      graphRef.current = null
      setReady(false)
    }
  }, [model, data, openEvidence, t])


  useEffect(() => {
    focusRef.current.selected = selectedId
    focusRef.current.doc = docFilter
    refreshRef.current()
  }, [selectedId, docFilter])

  useEffect(() => {
    showCoRef.current = showCo
    const graph = graphRef.current
    if (graph) graph.linkVisibility(graph.linkVisibility())
  }, [showCo])

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q || !model) return []
    return model.nodes.filter((n) => n.name.toLowerCase().includes(q)).sort((a, b) => b.rank - a.rank).slice(0, 8)
  }, [query, model])

  const focusNode = (n: Node3D) => {
    flyRef.current(n)
    openEvidence({ kind: 'concept', conceptId: n.id, name: n.name })
    setQuery('')
  }

  const hues = data ? documentHues(data.documents.length, dark) : []

  return (
    <div className="relative h-full min-h-0 flex-1 overflow-hidden bg-background">
      {/* radial vignette behind the scene */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_center,color-mix(in_oklab,var(--teal)_10%,transparent),transparent_65%)]" />
      <div ref={containerRef} className="absolute inset-0 cursor-grab" aria-label={t('brain.graphTitle')} role="img" />
      {(isLoading || !ready) && (
        <div className="absolute inset-0 flex items-center justify-center">
          <LoadingSpinner size="lg" />
        </div>
      )}

      {data && (
        <>
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
                    <span className="size-2 shrink-0 rounded-full" style={{ background: hues[n.doc % hues.length] }} />
                    <span className="flex-1 truncate">{n.name}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">{n.mentions}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="absolute right-4 top-4 flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                const next = !spinning
                setSpinning(next)
                spinRef.current(next)
              }}
              className="flex items-center gap-1.5 rounded-full border bg-card/90 px-3 py-1.5 text-[11px] font-medium shadow-soft backdrop-blur"
              aria-pressed={spinning}
            >
              {spinning ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
              {t('brain.graphOrbit')}
            </button>
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

          <div className="absolute bottom-4 left-4 max-w-[calc(100%-2rem)] rounded-xl border bg-card/90 p-2 shadow-lift backdrop-blur">
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
                  <span className="size-2.5 rounded-full" style={{ background: hues[i % hues.length] }} />
                  {shortTitle(doc)}
                </button>
              ))}
            </div>
          </div>

          <p className="pointer-events-none absolute bottom-4 right-4 text-[11px] text-muted-foreground">{t('brain.graph3dHint')}</p>
        </>
      )}
    </div>
  )
}
