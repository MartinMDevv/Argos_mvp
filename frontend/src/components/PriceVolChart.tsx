import { useCallback, useEffect, useRef, useState } from 'react'

import { obtenerVelas } from '@/lib/api'
import type { VelaJSON } from '@/lib/api'

/**
 * Precio y volumen de las últimas 24 horas, con datos reales.
 *
 * **Este era el último mock del frontend.** Hasta acá dibujaba veinte velas inventadas que
 * venían del boceto: una curva bonita que subía siempre, con un histograma de volumen que no
 * medía nada. Ahora sale de `GET /mercado/velas`, igual que el gráfico del Panel.
 *
 * ## Por qué no se reusó `CandleChart`
 * Porque cuentan cosas distintas y el encabezado de la tarjeta lo dice: ahí van velas OHLC para
 * leer la acción del precio; acá va la **forma** del día —hacia dónde fue el precio y con cuánto
 * volumen— de un vistazo. Una línea con el volumen debajo se lee más rápido que 96 velas, y para
 * eso alcanza un canvas de 60 líneas en vez de traer toda una librería de gráficos.
 *
 * ## Tramos de 15 minutos
 * 96 tramos de 15 minutos son exactamente 24 horas. En 1m serían 1.440 puntos para 600 píxeles
 * de ancho: se pisarían entre ellos y el dibujo tardaría más sin mostrar nada nuevo.
 */

/** Cuántos tramos se piden y de qué ancho. 96 × 15m = 24 h justas. */
const INTERVALO = '15m' as const
const TRAMOS = 96

/** Cada cuánto se refresca. El último tramo se sigue moviendo, pero no hace falta correrle. */
const REFRESCO = 30_000

const ALTO = 220

const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()

export function PriceVolChart({ par }: { par: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [velas, setVelas] = useState<VelaJSON[]>([])
  const [error, setError] = useState(false)

  useEffect(() => {
    const control = new AbortController()
    let vivo = true

    const pedir = async () => {
      try {
        const traidas = await obtenerVelas(par, INTERVALO, TRAMOS, control.signal)
        if (!vivo) return
        setVelas(traidas)
        setError(false)
      } catch {
        if (!vivo || control.signal.aborted) return
        setError(true)
      }
    }

    pedir()
    const reloj = setInterval(pedir, REFRESCO)
    return () => {
      vivo = false
      clearInterval(reloj)
      control.abort()
    }
  }, [par])

  const dibujar = useCallback(() => {
    const lienzo = ref.current
    if (!lienzo || velas.length === 0) return

    const dpr = window.devicePixelRatio || 1
    const ancho = lienzo.clientWidth
    if (!ancho) return

    lienzo.width = ancho * dpr
    lienzo.height = ALTO * dpr
    const c = lienzo.getContext('2d')!
    c.setTransform(dpr, 0, 0, dpr, 0, 0)
    c.clearRect(0, 0, ancho, ALTO)

    const teal = css('--teal')
    const bull = css('--bull')
    const bear = css('--bear')

    // El precio ocupa la parte de arriba y el volumen la de abajo, sin superponerse: dos
    // magnitudes distintas compartiendo eje vertical serían dos escalas mintiendo juntas.
    const arriba = 8
    const abajoPrecio = ALTO * 0.64
    const arribaVol = ALTO * 0.72
    const abajoVol = ALTO - 6

    const margen = 8
    const paso = (ancho - margen * 2) / velas.length
    const grosor = Math.max(1, paso * 0.55)

    const cierres = velas.map((vela) => Number(vela.cierre))
    const volumenes = velas.map((vela) => Number(vela.volumen_cotizado))
    const maxVol = Math.max(...volumenes, 1)

    // Volumen: cada barra se pinta según si ese tramo cerró arriba o abajo de su apertura.
    velas.forEach((vela, i) => {
      const x = margen + i * paso + paso / 2
      const alto = (volumenes[i] / maxVol) * (abajoVol - arribaVol)
      c.fillStyle = Number(vela.cierre) >= Number(vela.apertura) ? bull : bear
      c.globalAlpha = 0.45
      c.fillRect(x - grosor / 2, abajoVol - alto, grosor, alto)
      c.globalAlpha = 1
    })

    // Precio: la escala sale de los máximos y mínimos reales del tramo, no de los cierres,
    // para que la línea nunca toque el borde del área dibujada.
    const alto24 = Math.max(...velas.map((vela) => Number(vela.maximo)))
    const bajo24 = Math.min(...velas.map((vela) => Number(vela.minimo)))
    const rango = alto24 - bajo24 || 1
    const y = (valor: number) => abajoPrecio - ((valor - bajo24) / rango) * (abajoPrecio - arriba)

    const trazar = () => {
      c.beginPath()
      cierres.forEach((cierre, i) => {
        const x = margen + i * paso + paso / 2
        if (i === 0) c.moveTo(x, y(cierre))
        else c.lineTo(x, y(cierre))
      })
    }

    trazar()
    c.lineTo(ancho - margen, abajoPrecio)
    c.lineTo(margen, abajoPrecio)
    c.closePath()
    c.fillStyle = teal
    c.globalAlpha = 0.1
    c.fill()
    c.globalAlpha = 1

    trazar()
    c.strokeStyle = teal
    c.lineWidth = 1.8
    c.stroke()

    // El punto del final marca dónde está el precio ahora.
    const ultimoX = margen + (velas.length - 0.5) * paso
    c.fillStyle = teal
    c.beginPath()
    c.arc(ultimoX, y(cierres[cierres.length - 1]), 3, 0, Math.PI * 2)
    c.fill()
  }, [velas])

  useEffect(() => {
    dibujar()

    const alRedimensionar = () => dibujar()
    window.addEventListener('resize', alRedimensionar)

    // El canvas no se entera de que cambió el tema: hay que volver a pintarlo con los colores
    // nuevos, tanto si lo cambió el usuario (`data-theme`) como el sistema.
    const observador = new MutationObserver(dibujar)
    observador.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
    const consulta = matchMedia('(prefers-color-scheme: dark)')
    consulta.addEventListener('change', dibujar)

    return () => {
      window.removeEventListener('resize', alRedimensionar)
      observador.disconnect()
      consulta.removeEventListener('change', dibujar)
    }
  }, [dibujar])

  if (error) return <p className="vacio">No se pudieron traer las velas de {par}.</p>
  if (velas.length === 0) return <p className="vacio">Trayendo las últimas 24 horas…</p>

  return (
    <canvas
      ref={ref}
      style={{ height: ALTO }}
      aria-label={`Precio y volumen de ${par} en las últimas 24 horas`}
    />
  )
}
