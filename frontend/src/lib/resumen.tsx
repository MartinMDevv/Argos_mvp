/**
 * La ficha de cada activo, viva: REST para la verdad, WebSocket para el movimiento (paso 2.2b).
 *
 * Del otro lado está `GET /mercado/resumen` (paso 2.2a), que da precio, cambio % a 1h/24h/7d,
 * máximo, mínimo y volumen del día.
 *
 * ## Un solo proveedor, la misma lección que en `mercado.tsx`
 * Cinco componentes necesitan estos datos (menú, watchlist, cabecera, tabla y KPIs). Si cada uno
 * hiciera su propio `fetch` en bucle serían cinco pollings pidiendo lo mismo, y cada cambio de
 * vista los reiniciaría. **Un pedido arriba del todo**, y todos leen de ahí. Es exactamente el
 * argumento por el que el WebSocket vive en un contexto y no en un hook suelto.
 *
 * ## Por qué el porcentaje se recalcula acá
 * El REST se repregunta cada 10 segundos; el WebSocket trae precios cada medio segundo. Si nos
 * quedáramos con el porcentaje que calculó el backend, el precio de la watchlist se movería y el
 * "+1,84%" de al lado quedaría clavado hasta el próximo refresco — dos números contradiciéndose
 * en la misma fila.
 *
 * La solución es no pedirle al backend el resultado sino **el punto de partida**: cada cambio
 * viene con su `referencia` (el precio de hace 24 h) y su momento. Con eso, el porcentaje se
 * rehace acá contra el precio vivo y los dos números se mueven juntos, siempre coherentes.
 *
 * Ojo con lo que esto NO hace: la referencia sigue saliendo de la base, calculada con el ancla y
 * la tolerancia del backend. Acá solo se rehace la división. Si el backend dijo `null` —no había
 * con qué comparar—, acá sigue siendo `null`; no se inventa una referencia para llenar el hueco.
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { PARES, activoDe } from './activos'
import type { Activo } from './activos'
import { obtenerResumen } from './api'
import type { EstadoSimbolo, Plazo, ResumenJSON } from './api'
import { useMercado } from './mercado'

/**
 * Cada cuánto se le vuelve a preguntar al backend.
 *
 * Mismo criterio que la reconciliación del gráfico (paso 2.1): el WebSocket da la inmediatez y
 * el REST corrige. Diez segundos alcanzan de sobra para el máximo, el mínimo y el volumen del
 * día, que no cambian de golpe, y mantiene la carga en un pedido cada diez segundos.
 */
const REFRESCO = 10_000

/** Un minuto de datos por cada minuto del día. Con menos, el volumen es parcial y se advierte. */
export const MINUTOS_DEL_DIA = 1440

/** Todo lo que el panel sabe de un activo, ya en números y listo para mostrar. */
export interface Ficha {
  activo: Activo

  /** El precio a mostrar, o `null` si Argos todavía no sabe nada de este activo. */
  precio: number | null

  /** `true` si el precio salió del WebSocket (segundos). `false` si es el último que dio el REST. */
  vivo: boolean

  /** De cuándo es el precio, en ISO. Sirve para avisar cuando está viejo. */
  momento: string | null

  /** Variación por plazo, recalculada contra el precio vivo. `null` = no había con qué comparar. */
  cambios: Record<Plazo, number | null>

  /** El precio de hace 24 h. Es lo que permite mostrar el cambio también en plata, no solo en %. */
  referencia24h: number | null

  maximo24h: number | null
  minimo24h: number | null
  volumen24h: number | null
  volumenCotizado24h: number | null

  /** Cuántos de los 1.440 minutos del día tienen datos. */
  minutos24h: number

  /** Lo anterior como fracción (0 a 1). Con menos de 1, el volumen del día es parcial. */
  cobertura24h: number

  fuente24h: 'propia' | 'historia' | 'mixta' | null
}

interface EstadoResumen {
  crudo: Record<string, ResumenJSON>
  cargando: boolean
  /** Mensaje del último fallo, o `null`. Se muestra en vez de dejar datos viejos sin explicación. */
  error: string | null
}

const ContextoResumen = createContext<EstadoResumen>({ crudo: {}, cargando: true, error: null })

export function ProveedorResumen({ children }: { children: ReactNode }) {
  const [estado, setEstado] = useState<EstadoResumen>({ crudo: {}, cargando: true, error: null })

  const pedir = useCallback(async (senal: AbortSignal) => {
    try {
      const simbolos = await obtenerResumen(PARES, senal)
      if (senal.aborted) return
      setEstado({ crudo: simbolos, cargando: false, error: null })
    } catch (error) {
      if (senal.aborted) return
      // Los datos viejos se conservan a propósito: un precio de hace diez segundos sigue siendo
      // más útil que una pantalla en blanco. Lo que no se puede hacer es callar el problema, así
      // que el error viaja junto a ellos y el panel lo muestra.
      setEstado((previo) => ({
        ...previo,
        cargando: false,
        error: error instanceof Error ? error.message : 'No se pudo hablar con el backend',
      }))
    }
  }, [])

  useEffect(() => {
    const control = new AbortController()

    void pedir(control.signal)
    const reloj = setInterval(() => void pedir(control.signal), REFRESCO)

    // Al volver a la pestaña se pregunta de una, sin esperar el turno del reloj. El navegador
    // frena los temporizadores en las pestañas de fondo, así que al volver de un rato largo (o
    // de suspender el equipo) lo que hay en pantalla puede tener horas.
    const alVolver = () => {
      if (document.visibilityState === 'visible') void pedir(control.signal)
    }
    document.addEventListener('visibilitychange', alVolver)

    return () => {
      control.abort()
      clearInterval(reloj)
      document.removeEventListener('visibilitychange', alVolver)
    }
  }, [pedir])

  return <ContextoResumen.Provider value={estado}>{children}</ContextoResumen.Provider>
}

/** Si el resumen está cargando o falló. Para estados de carga y avisos de error. */
export function useEstadoResumen(): { cargando: boolean; error: string | null } {
  const { cargando, error } = useContext(ContextoResumen)
  return { cargando, error }
}

/**
 * La ficha de un activo, ya combinada con el precio vivo del WebSocket.
 *
 * Devuelve `null` si Argos no tiene ningún dato del activo. Es distinto de "vale cero": es "no
 * sé", y quien lo reciba tiene que mostrar un hueco, no un número.
 */
export function useFicha(par: string): Ficha | null {
  const { crudo } = useContext(ContextoResumen)
  const { simbolos } = useMercado()
  return construirFicha(par, crudo[par], simbolos[par] ?? null)
}

/**
 * Las fichas de varios activos, en el mismo orden que se pidieron. Para listas y tablas.
 *
 * Existe además de `useFicha` por una razón concreta de React: los hooks no pueden llamarse
 * dentro de un bucle de largo variable, así que una fila de la tabla no puede pedir su propia
 * ficha. Acá se leen los dos contextos una sola vez y el resto es un `map` común.
 */
export function useFichas(pares: string[]): (Ficha | null)[] {
  const { crudo } = useContext(ContextoResumen)
  const { simbolos } = useMercado()
  return pares.map((par) => construirFicha(par, crudo[par], simbolos[par] ?? null))
}

/**
 * Junta las dos fuentes en una ficha: lo que dijo el REST y lo que trae el WebSocket.
 *
 * Es una función normal y no un hook a propósito — así puede llamarse en un `map`.
 */
function construirFicha(
  par: string,
  resumen: ResumenJSON | undefined,
  enVivo: EstadoSimbolo | null,
): Ficha | null {
  const activo = activoDe(par)
  if (!activo || (!resumen && !enVivo)) return null

  // Gana el precio más nuevo, y casi siempre es el del WebSocket: el REST se repregunta cada
  // diez segundos y el socket empuja cada medio. La comparación igual se hace, porque con la
  // ingesta apagada la memoria queda vacía y el bueno pasa a ser el del REST.
  const precioVivo = enVivo ? Number(enVivo.precio) : null
  const precioRest = resumen ? Number(resumen.precio) : null

  // Los momentos se comparan como fechas y no como texto. Los dos vienen en ISO y **hoy**
  // comparar los strings daría bien, pero por casualidad: depende de que ambos tengan el mismo
  // formato exacto de microsegundos y de huso. Es la clase de suposición que aguanta hasta que
  // alguien cambia un `isoformat()` en el backend y rompe algo que nadie va a mirar acá.
  const usarVivo =
    precioVivo !== null &&
    (!resumen || !enVivo || Date.parse(enVivo.momento) >= Date.parse(resumen.momento))

  const precio = usarVivo ? precioVivo : precioRest
  const momento = usarVivo ? (enVivo?.momento ?? null) : (resumen?.momento ?? null)

  const referencia24h = numero(resumen?.cambios['24h']?.referencia)

  return {
    activo,
    precio,
    // "Vivo" significa una sola cosa: este precio llegó por el WebSocket, o sea que tiene
    // segundos. No se mira `origen_precio` del REST — ese dice de dónde lo sacó el backend hace
    // hasta diez segundos, y podría contradecir a un tick que acaba de entrar por el socket.
    vivo: usarVivo,
    momento,
    cambios: {
      '1h': cambioContra(precio, numero(resumen?.cambios['1h']?.referencia)),
      '24h': cambioContra(precio, referencia24h),
      '7d': cambioContra(precio, numero(resumen?.cambios['7d']?.referencia)),
    },
    referencia24h,
    maximo24h: numero(resumen?.maximo_24h),
    minimo24h: numero(resumen?.minimo_24h),
    volumen24h: numero(resumen?.volumen_24h),
    volumenCotizado24h: numero(resumen?.volumen_cotizado_24h),
    minutos24h: resumen?.minutos_24h ?? 0,
    cobertura24h: Math.min(1, (resumen?.minutos_24h ?? 0) / MINUTOS_DEL_DIA),
    fuente24h: resumen?.fuente_24h ?? null,
  }
}

/**
 * Rehace la división: cuánto se movió `precio` respecto de `referencia`, en porcentaje.
 *
 * Devuelve `null` si falta cualquiera de los dos, o si la referencia es cero. No hay valor por
 * defecto: un cero diría "no se movió", que es una afirmación, no una ausencia.
 */
function cambioContra(precio: number | null, referencia: number | null): number | null {
  if (precio === null || referencia === null || referencia === 0) return null
  if (!Number.isFinite(precio) || !Number.isFinite(referencia)) return null
  return ((precio - referencia) / referencia) * 100
}

/** Texto de la API a número, conservando el `null`. Ausencia de dato no es un cero. */
function numero(texto: string | null | undefined): number | null {
  if (texto === null || texto === undefined) return null
  const valor = Number(texto)
  return Number.isFinite(valor) ? valor : null
}
