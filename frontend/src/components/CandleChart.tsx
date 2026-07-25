import { useCallback, useEffect, useRef } from 'react'
import { CANDLES } from '@/data/coins'

const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()

// Gráfico de velas con crosshair (línea + precio bajo el cursor + O/H/L/C).
// En Fase 2 esto se reemplaza por TradingView lightweight-charts con datos reales.
export function CandleChart() {
  const ref = useRef<HTMLCanvasElement>(null)
  const cross = useRef<{ x: number; y: number } | null>(null)

  const draw = useCallback(() => {
    const cv = ref.current
    if (!cv) return
    const dpr = window.devicePixelRatio || 1, W = cv.clientWidth, H = 230
    if (!W) return
    cv.width = W * dpr; cv.height = H * dpr
    const c = cv.getContext('2d')!
    c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, W, H)
    const line = css('--line-soft'), bull = css('--bull'), bear = css('--bear'), gold = css('--gold')
    c.strokeStyle = line; c.lineWidth = 1
    for (let i = 0; i <= 4; i++) { const y = 10 + (i * (H - 30)) / 4; c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke() }
    const pad = 8, top = 10, bot = H - 20
    const hi = Math.max(...CANDLES.map(d => d[1])), lo = Math.min(...CANDLES.map(d => d[2]))
    const y = (v: number) => bot - ((v - lo) / (hi - lo)) * (bot - top)
    const slot = (W - pad * 2) / CANDLES.length, bw = slot * 0.56
    CANDLES.forEach((d, i) => {
      const x = pad + i * slot + slot / 2, up = d[3] >= d[0], col = up ? bull : bear
      c.strokeStyle = col; c.fillStyle = col; c.lineWidth = 1.4
      c.beginPath(); c.moveTo(x, y(d[1])); c.lineTo(x, y(d[2])); c.stroke()
      const yo = y(d[0]), yc = y(d[3]); c.fillRect(x - bw / 2, Math.min(yo, yc), bw, Math.max(2, Math.abs(yc - yo)))
    })
    const last = CANDLES[CANDLES.length - 1], lx = pad + (CANDLES.length - 0.5) * slot, ly = y(last[3])
    c.setLineDash([3, 4]); c.strokeStyle = gold; c.globalAlpha = 0.5
    c.beginPath(); c.moveTo(0, ly); c.lineTo(W, ly); c.stroke(); c.setLineDash([]); c.globalAlpha = 1
    c.fillStyle = gold; c.beginPath(); c.arc(lx, ly, 3.4, 0, 7); c.fill()

    const cr = cross.current
    if (cr) {
      const px = (v: number) => 62100 + ((v - lo) / (hi - lo)) * 2800
      const fmt = (v: number) => '$' + Math.round(v).toLocaleString('es-CL')
      const i = Math.max(0, Math.min(CANDLES.length - 1, Math.floor((cr.x - pad) / slot)))
      const cx2 = pad + i * slot + slot / 2, cy = Math.max(top, Math.min(bot, cr.y))
      c.setLineDash([2, 3]); c.strokeStyle = css('--faint'); c.globalAlpha = 0.7
      c.beginPath(); c.moveTo(cx2, top); c.lineTo(cx2, bot); c.stroke()
      c.beginPath(); c.moveTo(0, cy); c.lineTo(W, cy); c.stroke(); c.setLineDash([]); c.globalAlpha = 1
      const p = px(lo + ((bot - cy) * (hi - lo)) / (bot - top)), lab = fmt(p)
      c.font = '10px JBMono, monospace'; const tw = c.measureText(lab).width + 10
      c.fillStyle = css('--surface-2'); c.strokeStyle = css('--line')
      c.beginPath(); c.roundRect(W - tw - 4, cy - 8, tw, 16, 4); c.fill(); c.stroke()
      c.fillStyle = css('--text'); c.fillText(lab, W - tw + 1, cy + 3.5)
      const d = CANDLES[i]
      c.fillStyle = css('--faint'); c.font = '9.5px JBMono, monospace'
      c.fillText(`O ${fmt(px(d[0]))}  H ${fmt(px(d[1]))}  L ${fmt(px(d[2]))}  C ${fmt(px(d[3]))}`, 8, top + 8)
    }
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

  return (
    <canvas
      ref={ref}
      style={{ cursor: 'crosshair' }}
      aria-label="Velas de BTC"
      onMouseMove={e => {
        const r = ref.current!.getBoundingClientRect()
        cross.current = { x: e.clientX - r.left, y: e.clientY - r.top }
        draw()
      }}
      onMouseLeave={() => { cross.current = null; draw() }}
    />
  )
}
