// d3-force-3d ships no types; the few forces the 3D concept graph uses.
declare module 'd3-force-3d' {
  interface Force<N> {
    (alpha: number): void
    strength(value: number | ((node: N) => number)): Force<N>
  }
  export function forceX<N>(x?: number | ((node: N) => number)): Force<N>
  export function forceY<N>(y?: number | ((node: N) => number)): Force<N>
  export function forceZ<N>(z?: number | ((node: N) => number)): Force<N>
}
