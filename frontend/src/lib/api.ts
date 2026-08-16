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

/** Los plazos que compara `GET /mercado/resumen` (`PLAZOS` en `app/resumen.py`). Lista cerrada. */
export const PLAZOS = ['1h', '24h', '7d'] as const

export type Plazo = (typeof PLAZOS)[number]

/**
 * Cuánto se movió el precio en un plazo (ver `Cambio` en `app/modelos.py`).
 *
 * **`referencia` no está de adorno.** Es el precio contra el que se hizo la cuenta, y es lo que
 * le permite al panel rehacerla: el backend calculó el porcentaje contra el precio que tenía en
 * ese momento, pero el WebSocket sigue trayendo precios más nuevos. Con la referencia a mano, el
 * porcentaje se recalcula acá y se mueve junto al precio en vez de quedar congelado hasta el
 * próximo refresco. Ver `cambioContra()` en `lib/resumen.tsx`.
 */
export interface CambioJSON {
  porcentaje: string
  referencia: string
  momento: string
}

/**
 * La ficha de un activo tal cual la manda `GET /mercado/resumen` (paso 2.2a).
 *
 * Tres campos que hay que mirar antes de creerle a los números, y que existen justamente para
 * que el panel no muestre de más:
 *
 * - `momento` — de cuándo es el precio. Si Argos estuvo apagado, es viejo.
 * - `cambios[plazo] === null` — no había con qué comparar. Se muestra "—", **nunca 0%**.
 * - `minutos_24h` — cuántos de los 1.440 minutos del día tienen datos. Con menos de 1.440 el
 *   volumen es el de esos minutos y nada más, y el panel lo advierte.
 */
export interface ResumenJSON {
  precio: string
  momento: string
  /** `vivo` = último tick en memoria; `guardado` = último cierre en la base (ingesta apagada). */
  origen_precio: 'vivo' | 'guardado'
  cambios: Record<Plazo, CambioJSON | null>
  maximo_24h: string | null
  minimo_24h: string | null
  volumen_24h: string | null
  volumen_cotizado_24h: string | null
  minutos_24h: number
  fuente_24h: 'propia' | 'historia' | 'mixta' | null
}

export interface RespuestaResumen {
  plazos: string[]
  /** Un símbolo del que Argos no tiene ningún dato **no aparece** acá. Ausencia ≠ cero. */
  simbolos: Record<string, ResumenJSON>
}

// ---------------------------------------------------------------------------
// Alertas (paso 3.6)
// ---------------------------------------------------------------------------

/** Cuánto pide tu atención una alerta (`SEVERIDADES` en `app/detectores/base.py`). */
export const SEVERIDADES = ['info', 'aviso', 'fuerte'] as const

export type Severidad = (typeof SEVERIDADES)[number]

/**
 * Algo que Argos vio, tal cual lo manda `GET /alertas` (ver `Alerta` en `app/modelos.py`).
 *
 * **`evidencia` no es un extra decorativo.** Son los números crudos con los que el detector
 * llegó a su conclusión —el valor medido, la referencia contra la que lo comparó, el umbral
 * cruzado—, y existen porque la regla del proyecto es que Argos no afirma nada que no se pueda
 * verificar. El panel los muestra para que la alerta se pueda rehacer a mano, no para rellenar.
 *
 * Vienen como texto por el mismo motivo que los precios: son números exactos que no deben pasar
 * por un float. Las claves cambian según el detector que la emitió, así que se muestran como lo
 * que son —pares de nombre y valor— y el panel no supone que exista ninguna en particular.
 */
export interface AlertaJSON {
  id: number
  momento: string
  detector: string
  simbolo: string
  severidad: Severidad
  titulo: string
  detalle: string
  evidencia: Record<string, string>
  /** Identidad de la SITUACIÓN, no del aviso: es con lo que el motor agrupa el antirruido. */
  clave: string
}

export interface RespuestaAlertas {
  cantidad: number
  alertas: AlertaJSON[]
}

/** Una ficha de `GET /detectores`: qué vigila Argos y con qué cadencia. */
export interface DetectorJSON {
  nombre: string
  titulo: string
  descripcion: string
  cadencia: 'por_tick' | 'por_vela_cerrada'
  intervalo: string | null
  velas_necesarias: number
  silencio_segundos: number
}

/**
 * Los mensajes que empuja `WS /ws/mercado` (paso 1.4; `alerta` desde el 4.2).
 *
 * Están tipados como unión discriminada por `tipo`: TypeScript obliga a mirar el `tipo` antes
 * de tocar `simbolos`, así que es imposible leer datos de un `latido` (que no los trae).
 */
export type MensajeMercado =
  | { tipo: 'bienvenida'; momento: string; simbolos: Record<string, EstadoSimbolo> }
  | { tipo: 'estado'; momento: string; simbolos: Record<string, EstadoSimbolo> }
  | { tipo: 'latido'; momento: string }
  /** Una alerta recién emitida (paso 4.2). Llega por el mismo socket que el estado. */
  | { tipo: 'alerta'; momento: string; alerta: AlertaJSON }

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

/**
 * Trae la ficha de cada activo: precio, cambio %, máximo, mínimo y volumen del día.
 *
 * Se piden todos los símbolos de una sola vez —el backend los resuelve en una consulta— en vez
 * de un pedido por moneda. Con dos da igual; con veinte en la watchlist, no.
 */
export async function obtenerResumen(
  pares: string[],
  senal?: AbortSignal,
): Promise<Record<string, ResumenJSON>> {
  const parametros = new URLSearchParams()
  for (const par of pares) parametros.append('simbolos', par)

  const respuesta = await fetch(`${URL_API}/mercado/resumen?${parametros}`, { signal: senal })

  if (!respuesta.ok) {
    throw new Error(`El backend respondió ${respuesta.status} al pedir el resumen de mercado`)
  }

  const datos: RespuestaResumen = await respuesta.json()
  return datos.simbolos
}

/**
 * Trae lo último que Argos vio, de lo más nuevo a lo más viejo (paso 3.6).
 *
 * Sin filtro de símbolo a propósito: el feed del panel es de **todo** lo que Argos vio, no del
 * activo que está mirando el usuario. Que ETH se dispare mientras miras BTC es justamente lo que
 * uno quiere que le avisen.
 */
export async function obtenerAlertas(limite = 50, senal?: AbortSignal): Promise<AlertaJSON[]> {
  const parametros = new URLSearchParams({ limite: String(limite) })

  const respuesta = await fetch(`${URL_API}/alertas?${parametros}`, { signal: senal })

  if (!respuesta.ok) {
    throw new Error(`El backend respondió ${respuesta.status} al pedir las alertas`)
  }

  const datos: RespuestaAlertas = await respuesta.json()
  return datos.alertas
}

/**
 * Un precio que pediste vigilar (`Umbral` en `app/modelos.py`, paso 3.2).
 *
 * **Un umbral vigila una sola dirección.** Si quieres enterarte de la subida y de la bajada son
 * dos umbrales, y así cada aviso dice exactamente qué pasó sin que haya que deducirlo.
 */
export interface UmbralJSON {
  id: number
  simbolo: string
  valor: string
  /** `arriba` = avisa al cruzar subiendo; `abajo`, bajando. La línea pertenece al lado de abajo. */
  direccion: 'arriba' | 'abajo'
  nota: string | null
  creado: string | null
}

export interface RespuestaUmbrales {
  /** Cuántos hay configurados. El backend lo llama así, no `cantidad`. */
  configurados: number
  umbrales: UmbralJSON[]
  /**
   * `false` = Argos todavía no pudo leer la tabla (la base estaba caída al arrancar).
   *
   * Importa mostrarlo: con `false`, una lista vacía **no significa que no haya umbrales**,
   * significa que no sabemos. Decir "no tienes ninguno" en ese caso sería afirmar de más.
   */
  cargado_alguna_vez: boolean
}

/** Los precios que pediste vigilar. */
export async function obtenerUmbrales(senal?: AbortSignal): Promise<RespuestaUmbrales> {
  const respuesta = await fetch(`${URL_API}/umbrales`, { signal: senal })

  if (!respuesta.ok) {
    throw new Error(`El backend respondió ${respuesta.status} al pedir los umbrales`)
  }

  return respuesta.json()
}

/** Agrega un umbral. El backend responde 409 si ya existe uno igual. */
export async function crearUmbral(datos: {
  simbolo: string
  valor: string
  direccion: 'arriba' | 'abajo'
  nota?: string
}): Promise<UmbralJSON> {
  const respuesta = await fetch(`${URL_API}/umbrales`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(datos),
  })

  if (!respuesta.ok) {
    // El backend explica en `detail` qué pasó (duplicado, símbolo no vigilado…). Se muestra
    // su mensaje en vez de uno genérico: sabe más que nosotros sobre lo que salió mal.
    const cuerpo = await respuesta.json().catch(() => null)
    const detalle = cuerpo?.detail?.detalle ?? cuerpo?.detail ?? `error ${respuesta.status}`
    throw new Error(typeof detalle === 'string' ? detalle : `error ${respuesta.status}`)
  }

  return respuesta.json()
}

/** Saca un umbral. Devuelve `true` si estaba y se borró. */
export async function borrarUmbral(id: number): Promise<boolean> {
  const respuesta = await fetch(`${URL_API}/umbrales/${id}`, { method: 'DELETE' })

  if (respuesta.status === 404) return false
  if (!respuesta.ok) {
    throw new Error(`El backend respondió ${respuesta.status} al borrar el umbral`)
  }
  return true
}

/**
 * Lo agitado que está un activo (paso 3.7), tal cual lo manda `GET /mercado/volatilidad`.
 *
 * `tipico_pct` es el rango verdadero **mediano** de un tramo de 5 minutos en las últimas 24 h:
 * la misma medida con la que la alerta #3 decide qué es raro. Que sea la misma no es un detalle
 * — si el panel midiera la volatilidad de otra forma que el detector, las dos pantallas dirían
 * cosas distintas del mismo mercado.
 */
export interface VolatilidadJSON {
  tipico_pct: string
  /** El tramo más movido de las 24 h: dice si el día tuvo un susto aunque la mediana sea baja. */
  maximo_pct: string
  tramos: number
  minutos_por_tramo: number
}

/**
 * La volatilidad típica de cada símbolo.
 *
 * Un símbolo con poca historia **no viene en la respuesta**: es un "no sé", no un cero. El panel
 * muestra "—" en ese caso, igual que con los cambios porcentuales sin referencia.
 */
export async function obtenerVolatilidad(
  pares: string[],
  senal?: AbortSignal,
): Promise<Record<string, VolatilidadJSON>> {
  const parametros = new URLSearchParams()
  for (const par of pares) parametros.append('simbolos', par)

  const respuesta = await fetch(`${URL_API}/mercado/volatilidad?${parametros}`, { signal: senal })

  if (!respuesta.ok) {
    throw new Error(`El backend respondió ${respuesta.status} al pedir la volatilidad`)
  }

  const datos: { simbolos: Record<string, VolatilidadJSON> } = await respuesta.json()
  return datos.simbolos
}

/** Trae el catálogo de detectores: qué vigila Argos ahora mismo. */
export async function obtenerDetectores(senal?: AbortSignal): Promise<DetectorJSON[]> {
  const respuesta = await fetch(`${URL_API}/detectores`, { signal: senal })

  if (!respuesta.ok) {
    throw new Error(`El backend respondió ${respuesta.status} al pedir los detectores`)
  }

  const datos: { detectores: DetectorJSON[] } = await respuesta.json()
  return datos.detectores
}
