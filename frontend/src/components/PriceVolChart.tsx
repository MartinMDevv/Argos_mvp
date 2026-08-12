import { useCallback, useEffect, useRef } from 'react'

/**
 * ⚠️ **El único mock que queda en el frontend** (desde el paso 2.2b).
 *
 * Estos números vivían en `data/coins.ts` junto con los precios y porcentajes inventados del
 * boceto. Ese archivo se eliminó cuando todo lo demás pasó a datos reales; esto se mudó acá, al
 * lado del único componente que todavía lo usa, para que el mock no quede escondido en una
 * carpeta que aparenta ser una fuente de datos.
 *
 * Enchufarlo de verdad (volumen real bajo el gráfico) es parte de la **revisión completa del
 * frontend** anotada en `CHECKLIST.md` → "Anotado para más adelante", que va después del MVP
 * funcional. Hasta entonces el panel lo declara: el encabezado de la tarjeta dice `mock`.
 */
const CANDLES: [number, number, number, number][] = [
  [30, 42, 26, 38], [38, 46, 34, 35], [35, 40, 28, 30], [30, 33, 22, 32], [32, 44, 30, 41],
  [41, 48, 38, 39], [39, 41, 31, 34], [34, 45, 33, 44], [44, 52, 42, 46], [46, 49, 40, 42],
  [42, 44, 34, 36], [36, 50, 35, 49], [49, 58, 47, 52], [52, 55, 45, 47], [47, 49, 40, 44],
  [44, 57, 43, 55], [55, 62, 53, 58], [58, 60, 50, 52], [52, 54, 44, 49], [49, 63, 48, 61],
]
const VOLS = [4, 6, 3, 5, 7, 4, 3, 6, 8, 4, 3, 9, 7, 5, 4, 8, 9, 5, 4, 10]

const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()

// Gráfico de precio (línea + área) con histograma de volumen debajo.
export function PriceVolChart() {
  const ref = useRef<HTMLCanvasElement>(null)

  const draw = useCallback(() => {
    const cv = ref.current
    if (!cv) return
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = 220
    if (!W) return
    cv.width = W * dpr; cv.height = H * dpr
    const c = cv.getContext('2d')!
    c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, W, H)
    const teal = css('--teal'), bull = css('--bull'), bear = css('--bear')
    const pTop = 8, pBot = H * 0.64, vTop = H * 0.72, vBot = H - 6
    const pad = 8, slot = (W - pad * 2) / CANDLES.length, bw = slot * 0.5, vmax = Math.max(...VOLS)
    VOLS.forEach((v, i) => {
      const x = pad + i * slot + slot / 2, h = (v / vmax) * (vBot - vTop), up = CANDLES[i][3] >= CANDLES[i][0]
      c.fillStyle = up ? bull : bear; c.globalAlpha = 0.45; c.fillRect(x - bw / 2, vBot - h, bw, h); c.globalAlpha = 1
    })
    const hi = Math.max(...CANDLES.map(d => d[1])), lo = Math.min(...CANDLES.map(d => d[2]))
    const y = (v: number) => pBot - ((v - lo) / (hi - lo)) * (pBot - pTop)
    c.beginPath(); CANDLES.forEach((d, i) => { const x = pad + i * slot + slot / 2; i ? c.lineTo(x, y(d[3])) : c.moveTo(x, y(d[3])) })
    c.lineTo(W - pad, pBot); c.lineTo(pad, pBot); c.closePath()
    c.fillStyle = teal; c.globalAlpha = 0.1; c.fill(); c.globalAlpha = 1
    c.beginPath(); CANDLES.forEach((d, i) => { const x = pad + i * slot + slot / 2; i ? c.lineTo(x, y(d[3])) : c.moveTo(x, y(d[3])) })
    c.strokeStyle = teal; c.lineWidth = 1.8; c.stroke()
    const lx = pad + (CANDLES.length - 0.5) * slot, ly = y(CANDLES[CANDLES.length - 1][3])
    c.fillStyle = teal; c.beginPath(); c.arc(lx, ly, 3, 0, 7); c.fill()
  }, [])

  useEffect(() => {
    draw()
    const onResize = () => draw()
    window.addEventListener('resize', onResize)
    const mo = new MutationObserver(draw)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const mq = matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', draw)
    return () => { window.removeEventListener('resize', onResize); mo.disconnect(); mq.removeEventListener('change', draw) }
  }, [draw])

  return <canvas ref={ref} aria-label="Precio y volumen de BTC" />
}
