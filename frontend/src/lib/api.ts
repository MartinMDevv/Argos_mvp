/**
 * Puente con el backend de Argos (paso 2.1).
 *
 * Acá vive TODO lo que el frontend sabe sobre la forma de la API: rutas, tipos de respuesta y
 * la dirección del servidor. El resto de la app pide datos por estas funciones y nunca arma una
 * URL a mano — el día que cambie una ruta se cambia en un solo lugar.
 *
 * ## Los números vienen como TEXTO, y no es un descuido
 * El backend manda los precios como strings (`"63557.26000000"`). Es a propósito: JSON no tiene
 * decimales exactos, así que un precio mandado como número llegaría a JavaScript convertido en
 * float — exactamente el problema que el backend evita usando `Decimal`. Como texto llega tal
 * cual salió de Binance.
 *
 * Regla que se desprende de eso: **convertir a número lo más tarde posible y solo para dibujar**.
 * El string es la fuente de verdad; el `Number(...)` es una concesión al gráfico, que necesita
 * píxeles y no puede pintar un decimal exacto.
 */

/** Dónde vive el backend. Se puede pisar con `VITE_API_URL` sin tocar el código. */
export const URL_API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** Misma dirección, otro protocolo: `http://` → `ws://`, `https://` → `wss://`. */
export const URL_WS = URL_API.replace(/^http/, 'ws')

// ---------------------------------------------------------------------------
// Intervalos
// ---------------------------------------------------------------------------

/** Los tramos que el backend sabe armar (`INTERVALOS` en `app/velas.py`). Lista cerrada. */
export const INTERVALOS = ['1m', '5m', '15m', '1h', '4h', '1d'] as const

export type Intervalo = (typeof INTERVALOS)[number]

/**
 * Cuánto dura cada tramo, en segundos.
 *
 * Hace falta para una cuenta concreta: cuando llega un precio nuevo por WebSocket hay que saber
 * a qué vela pertenece. `Math.floor(momento / ancho) * ancho` da el inicio de su tramo, que es
 * la misma cuenta que hace `time_bucket()` en la base (ambos alinean contra el epoch).
 */
export const ANCHO_SEGUNDOS: Record<Intervalo, number> = {
  '1m': 60,
  '5m': 300,
  '15m': 900,
  '1h': 3600,
  '4h': 14400,
  '1d': 86400,
}

// ---------------------------------------------------------------------------
// Tipos de la API (espejo de lo que responde el backend)
// ---------------------------------------------------------------------------

/** Una vela tal cual la manda `GET /mercado/velas` (ver `vela_a_json` en `app/velas.py`). */
export interface VelaJSON {
  inicio: string
  apertura: string
  maximo: string
  minimo: string
  cierre: string
  volumen: string
  volumen_cotizado: string
  operaciones: number
  variacion: string
  /**
   * De dónde salieron los números: `propia` (ticks que Argos vio), `historia` (vela oficial de
   * Binance traída por el backfill) o `mixta` (el tramo abarca minutos de las dos clases).
   *
   * Los precios son igual de reales en los tres casos. Lo que cambia es `operaciones`: en las
   * propias son operaciones agrupadas y en las históricas son las reales, siempre más. No se
   * comparan entre sí.
   */
  fuente: 'propia' | 'historia' | 'mixta'
  /** `false` mientras el tramo se sigue formando. La última vela siempre está a medio hacer. */
  completa: boolean
}

export interface RespuestaVelas {
  simbolo: string
  intervalo: string
  cantidad: number
  velas: VelaJSON[]
}

/** Lo último que Argos sabe de un símbolo (ver `instantanea()` en `app/estado.py`). */
export interface EstadoSimbolo {
  precio: string
  cantidad: string
  momento: string
  lado: string
  ticks_vistos: number
}

/**
 * Los tres mensajes que empuja `WS /ws/mercado` (paso 1.4).
 *
 * Están tipados como unión discriminada por `tipo`: TypeScript obliga a mirar el `tipo` antes
 * de tocar `simbolos`, así que es imposible leer datos de un `latido` (que no los trae).
 */
export type MensajeMercado =
  | { tipo: 'bienvenida'; momento: string; simbolos: Record<string, EstadoSimbolo> }
  | { tipo: 'estado'; momento: string; simbolos: Record<string, EstadoSimbolo> }
  | { tipo: 'latido'; momento: string }

// ---------------------------------------------------------------------------
// Llamadas
// ---------------------------------------------------------------------------

/**
 * Trae las últimas velas de un símbolo, de la más vieja a la más nueva.
 *
 * `senal` permite cancelar el pedido: si el usuario cambia de moneda mientras la respuesta
 * viaja, la respuesta vieja se descarta en vez de pisar a la nueva.
 */
export async function obtenerVelas(
  simbolo: string,
  intervalo: Intervalo,
  limite = 200,
  senal?: AbortSignal,
): Promise<VelaJSON[]> {
  const parametros = new URLSearchParams({
    simbolo,
    intervalo,
    limite: String(limite),
  })

  const respuesta = await fetch(`${URL_API}/mercado/velas?${parametros}`, { signal: senal })

  if (!respuesta.ok) {
    throw new Error(`El backend respondió ${respuesta.status} al pedir las velas de ${simbolo}`)
  }

  const datos: RespuestaVelas = await respuesta.json()
  return datos.velas
}
