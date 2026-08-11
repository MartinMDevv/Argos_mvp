/**
 * Gráfico de velas con datos reales (paso 2.1).
 *
 * Reemplaza al canvas dibujado a mano del paso 0.4, que era una ilustración: velas inventadas y
 * precios de mentira. Ahora las velas salen de TimescaleDB y se mueven solas.
 *
 * ## Dos fuentes, cada una en lo que es buena
 * - **REST (`/mercado/velas`)** → la HISTORIA y la VERDAD. La base agrupa los ticks con
 *   `time_bucket` y devuelve el máximo, el mínimo y el volumen exactos del tramo.
 * - **WebSocket (`/ws/mercado`)** → el AHORA. Manda una foto del último precio cada 0,5 s.
 *
 * El WebSocket no manda velas, manda precios sueltos. Así que la vela en curso se arma acá:
 * llega un precio, se estira el cierre, y el máximo/mínimo se corren si el precio los pasó.
 *
 * ## Por qué igual le seguimos preguntando a la base
 * La foto del WebSocket viaja cada 0,5 s **y solo si cambió algo**: entre dos fotos puede haber
 * habido un pico que no vimos. Si nos quedáramos solo con eso, el máximo de la vela sería "el
 * máximo de lo que alcanzamos a mirar", que no es lo mismo que el máximo real — y esta es la
 * clase de número que Argos no puede permitirse aproximar.
 *
 * Por eso cada `RECONCILIACION_MS` se le vuelve a preguntar a la base por las últimas velas y se
 * corrige lo que haga falta. La vela en curso termina siendo la unión de las dos fuentes: de la
 * base lo que ya aterrizó en disco, del WebSocket los últimos segundos que todavía no llegaron.
 */

import { useEffect, useRef, useState } from 'react'
import { CandlestickSeries, ColorType, CrosshairMode, LineStyle, createChart } from 'lightweight-charts'
import type { CandlestickData, IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts'

import { ANCHO_SEGUNDOS, obtenerVelas } from '@/lib/api'
import type { Intervalo, VelaJSON } from '@/lib/api'
import { useMercado, useSimbolo } from '@/lib/mercado'

/** Cada cuánto le preguntamos a la base para corregir la vela en curso. */
const RECONCILIACION_MS = 10_000

/** Cuántas velas del final pedimos al reconciliar. Con 3 sobra para cubrir un volcado atrasado. */
const VELAS_A_RECONCILIAR = 3

type Vela = CandlestickData<UTCTimestamp>

/** Lo que el WebSocket alcanzó a ver del tramo que se está formando ahora. */
interface Observado {
  time: UTCTimestamp
  high: number
  low: number
  close: number
}

const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()

/**
 * Pasa una vela de la API al formato del gráfico.
 *
 * Acá es donde los precios dejan de ser texto exacto y se vuelven `number`: es el último momento
 * posible, y es inevitable — el gráfico dibuja píxeles, no decimales.
 */
const aVela = (v: VelaJSON): Vela => ({
  time: (Date.parse(v.inicio) / 1000) as UTCTimestamp,
  open: Number(v.apertura),
  high: Number(v.maximo),
  low: Number(v.minimo),
  close: Number(v.cierre),
})

/** Mezcla las velas nuevas sobre las que ya teníamos: mismo `time` pisa, el resto se agrega. */
const fusionar = (base: Vela[], nuevas: Vela[]): Vela[] => {
  const porTiempo = new Map(base.map((v) => [v.time, v]))
  for (const vela of nuevas) porTiempo.set(vela.time, vela)
  return [...porTiempo.values()].sort((a, b) => (a.time as number) - (b.time as number))
}

interface Props {
  simbolo?: string
  intervalo?: Intervalo
  altura?: number
}

export function CandleChart({ simbolo = 'BTCUSDT', intervalo = '1m', altura = 230 }: Props) {
  const contenedor = useRef<HTMLDivElement>(null)
  const grafico = useRef<IChartApi | null>(null)
  const serie = useRef<ISeriesApi<'Candlestick'> | null>(null)

  /** Todas las velas que estamos mostrando, ordenadas de la más vieja a la más nueva. */
  const velas = useRef<Vela[]>([])
  /** Lo que vimos por WebSocket del tramo en curso; se pisa cuando empieza uno nuevo. */
  const observado = useRef<Observado | null>(null)

  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // Las velas viven en un `ref` (cambian muchas veces por segundo y no queremos un re-render por
  // cada una), pero *si hay o no hay* velas sí decide lo que se muestra: eso va en estado.
  const [hayVelas, setHayVelas] = useState(false)

  const { conectado } = useMercado()
  const estado = useSimbolo(simbolo)

  // -------------------------------------------------------------------------
  // 1) Crear el gráfico (una sola vez) y mantenerlo a tono con el tema
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!contenedor.current) return

    const chart = createChart(contenedor.current, {
      autoSize: true,
      // `handleScale`/`handleScroll` vienen activados: arrastrar y hacer zoom es gratis y es
      // justamente lo que el canvas dibujado a mano no podía dar.
      localization: {
        locale: 'es-CL',
        priceFormatter: (p: number) => p.toLocaleString('es-CL', { maximumFractionDigits: 2 }),
      },
    })

    const candles = chart.addSeries(CandlestickSeries, {
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })

    grafico.current = chart
    serie.current = candles

    // El tema vive en variables CSS, y el gráfico no las entiende: hay que leerlas y
    // pasárselas. Cada vez que el tema cambia, se vuelven a leer.
    const pintar = () => {
      chart.applyOptions({
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: css('--faint'),
          fontFamily: 'JBMono, monospace',
          fontSize: 10,
        },
        grid: {
          vertLines: { color: css('--line-soft') },
          horzLines: { color: css('--line-soft') },
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: {
            color: css('--faint'),
            style: LineStyle.Dashed,
            labelBackgroundColor: css('--surface-2'),
          },
          horzLine: {
            color: css('--faint'),
            style: LineStyle.Dashed,
            labelBackgroundColor: css('--surface-2'),
          },
        },
        rightPriceScale: { borderColor: css('--line') },
        timeScale: {
          borderColor: css('--line'),
          timeVisible: true,
          secondsVisible: false,
        },
      })

      candles.applyOptions({
        upColor: css('--bull'),
        downColor: css('--bear'),
        borderUpColor: css('--bull'),
        borderDownColor: css('--bear'),
        wickUpColor: css('--bull'),
        wickDownColor: css('--bear'),
      })
    }

    pintar()

    // Dos formas de cambiar de tema: el botón (escribe `data-theme`) y el sistema operativo.
    const observadorDeTema = new MutationObserver(pintar)
    observadorDeTema.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })
    const consulta = matchMedia('(prefers-color-scheme: dark)')
    consulta.addEventListener('change', pintar)

    return () => {
      observadorDeTema.disconnect()
      consulta.removeEventListener('change', pintar)
      chart.remove()
      grafico.current = null
      serie.current = null
    }
  }, [])

  // -------------------------------------------------------------------------
  // 2) Traer la historia y volver a preguntar cada tanto para corregir
  // -------------------------------------------------------------------------
  useEffect(() => {
    const control = new AbortController()
    let temporizador: number | undefined

    // Cambió el símbolo o el intervalo: lo que teníamos ya no sirve.
    velas.current = []
    observado.current = null
    setCargando(true)
    setError(null)
    setHayVelas(false)

    const aplicar = (nuevas: Vela[], primeraCarga: boolean) => {
      if (!serie.current || !grafico.current) return

      velas.current = fusionar(velas.current, nuevas)
      setHayVelas(velas.current.length > 0)

      // Guardamos y devolvemos el encuadre: sin esto, cada corrección devolvería la vista al
      // final y le arrebataría el zoom al usuario justo mientras mira algo.
      const encuadre = grafico.current.timeScale().getVisibleLogicalRange()
      serie.current.setData(velas.current)
      if (primeraCarga) grafico.current.timeScale().fitContent()
      else if (encuadre) grafico.current.timeScale().setVisibleLogicalRange(encuadre)
    }

    const pedir = async (primeraCarga: boolean) => {
      try {
        const respuesta = await obtenerVelas(
          simbolo,
          intervalo,
          primeraCarga ? 200 : VELAS_A_RECONCILIAR,
          control.signal,
        )
        aplicar(respuesta.map(aVela), primeraCarga)
        setError(null)
      } catch (e) {
        // Un pedido cancelado no es un error: pasa cada vez que se cambia de símbolo.
        if (control.signal.aborted) return
        // Si falla una reconciliación no borramos lo que ya se está mostrando: el gráfico sigue
        // andando con lo que tiene y la próxima vuelta corrige.
        if (primeraCarga) setError(e instanceof Error ? e.message : 'No se pudo hablar con el backend')
      } finally {
        if (!control.signal.aborted && primeraCarga) setCargando(false)
      }
    }

    void pedir(true)
    temporizador = setInterval(() => void pedir(false), RECONCILIACION_MS)

    return () => {
      control.abort()
      clearInterval(temporizador)
    }
  }, [simbolo, intervalo])

  // -------------------------------------------------------------------------
  // 3) Mover la vela en curso con cada precio que llega por WebSocket
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!estado || !serie.current) return

    const precio = Number(estado.precio)
    const momento = Date.parse(estado.momento) / 1000
    if (!Number.isFinite(precio) || !Number.isFinite(momento)) return

    // A qué tramo pertenece este precio. Es la misma cuenta que hace `time_bucket()` en la
    // base, por eso las velas de las dos fuentes caen siempre en el mismo casillero.
    const ancho = ANCHO_SEGUNDOS[intervalo]
    const inicio = (Math.floor(momento / ancho) * ancho) as UTCTimestamp

    const ultima = velas.current.at(-1)

    // Un precio de un tramo ya cerrado llega tarde (puede pasar tras una reconexión). No se
    // toca nada: la base ya tiene ese tramo y su versión es la buena.
    if (ultima && inicio < ultima.time) return

    let vela: Vela

    if (!ultima || inicio > ultima.time) {
      // Empezó un tramo nuevo: nace una vela que abre, cierra, sube y baja en el mismo precio.
      vela = { time: inicio, open: precio, high: precio, low: precio, close: precio }
      velas.current = [...velas.current, vela]
      observado.current = { time: inicio, high: precio, low: precio, close: precio }
      setHayVelas(true)
    } else {
      // Mismo tramo: se estira la vela que ya estaba.
      const visto = observado.current
      const acumulado: Observado =
        visto && visto.time === inicio
          ? {
              time: inicio,
              high: Math.max(visto.high, precio),
              low: Math.min(visto.low, precio),
              close: precio,
            }
          : { time: inicio, high: precio, low: precio, close: precio }

      observado.current = acumulado

      vela = {
        ...ultima,
        // El máximo y el mínimo son la unión de las dos fuentes: lo que la base ya sabe y lo
        // que el WebSocket vio después. Ninguna de las dos puede achicar a la otra.
        high: Math.max(ultima.high, acumulado.high),
        low: Math.min(ultima.low, acumulado.low),
        close: precio,
      }
      velas.current = [...velas.current.slice(0, -1), vela]
    }

    serie.current.update(vela)
  }, [estado, intervalo])

  const sinDatos = !cargando && !error && !hayVelas

  return (
    <div className="chart-lw" style={{ height: altura }}>
      <div ref={contenedor} style={{ height: '100%' }} />

      {/* Nada de esto inventa datos: si Argos no vio nada, lo dice. */}
      {(cargando || error || sinDatos) && (
        <div className="chart-aviso">
          {error ?? (cargando ? 'Cargando velas…' : `Argos todavía no vio operaciones de ${simbolo}`)}
        </div>
      )}

      {/* Hay velas pero la conexión se cortó: lo que se ve sigue siendo cierto, solo que ya no
          se mueve. Taparlo sería peor que avisarlo. */}
      {!conectado && !cargando && !sinDatos && !error && <span className="chart-frio">en pausa</span>}
    </div>
  )
}
