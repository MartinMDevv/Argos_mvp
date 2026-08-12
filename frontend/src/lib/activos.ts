/**
 * Los activos que Argos vigila, y sus dos nombres (paso 2.2b).
 *
 * ## Por qué esto existe
 * El backend habla de **pares**: `BTCUSDT`, `ETHUSDT`. Es lo correcto, porque un precio no
 * existe en el aire —siempre es "cuánto de esto por aquello"— y así lo llama el exchange.
 *
 * La gente habla de **monedas**: BTC, Bitcoin. Es lo que se muestra en la watchlist, en la
 * cabecera y en el menú.
 *
 * Antes de este paso convivían las dos formas sin traductor: el frontend guardaba `BTC` y el
 * backend recibía `BTCUSDT`, y cada componente resolvía la diferencia como podía. Acá se decide
 * una sola vez.
 *
 * ## La regla: el par manda
 * Todo lo que sea **estado o identidad** —qué activo está seleccionado, cuáles están fijados, la
 * clave de un diccionario, el argumento de una llamada— usa el **par**. El símbolo corto y el
 * nombre son para **mostrar**, nunca para identificar. Un solo idioma adentro evita el clásico
 * "acá era BTC y allá BTCUSDT" que aparece cuando hay que agregar la tercera moneda.
 *
 * ## Fase futura
 * Hoy la lista es fija y espeja `SIMBOLOS_MVP` del backend, porque el MVP vigila dos activos y
 * punto. Cuando se puedan agregar activos (memecoins, v2.0), esta lista la va a servir la API y
 * el catálogo se llenará solo; el resto de la app no se entera, porque ya habla de `Activo`.
 */

export interface Activo {
  /** Como lo llama el backend y el exchange. La identidad de verdad: `BTCUSDT`. */
  par: string
  /** Como lo llama la gente: `BTC`. Solo para mostrar. */
  simbolo: string
  /** Nombre largo: `Bitcoin`. Solo para mostrar. */
  nombre: string
  /** Contra qué se cotiza: `USDT`. Para escribir "BTC/USDT" sin partir el par a mano. */
  cotizacion: string
}

/** Espeja `SIMBOLOS_MVP` de `app/ingesta/binance.py`. El orden es el de la watchlist. */
export const ACTIVOS: Activo[] = [
  { par: 'BTCUSDT', simbolo: 'BTC', nombre: 'Bitcoin', cotizacion: 'USDT' },
  { par: 'ETHUSDT', simbolo: 'ETH', nombre: 'Ethereum', cotizacion: 'USDT' },
]

/** Todos los pares, en el orden del catálogo. Es el orden base de listas y tablas. */
export const PARES: string[] = ACTIVOS.map((a) => a.par)

const POR_PAR = new Map(ACTIVOS.map((a) => [a.par, a]))

/**
 * El activo de un par, o `undefined` si no está en el catálogo.
 *
 * Devuelve `undefined` en vez de inventar un activo genérico: si aparece un par desconocido es
 * que el catálogo quedó desalineado con el backend, y eso conviene que se note.
 */
export function activoDe(par: string): Activo | undefined {
  return POR_PAR.get(par)
}

/** El primer activo del catálogo. Es con el que arranca el panel. */
export const ACTIVO_POR_DEFECTO = ACTIVOS[0]
