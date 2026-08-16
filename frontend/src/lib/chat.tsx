/**
 * La conversación con Argos, una sola para toda la app (paso 4.4).
 *
 * ## Por qué vive acá y no dentro de un componente
 * Hay dos lugares donde se puede hablar con Argos: la **isla** de la derecha, para preguntar sin
 * salir del gráfico, y la **sección Chat** a pantalla completa, para leer con calma. Son dos
 * ventanas a la misma conversación, no dos conversaciones.
 *
 * Si cada componente guardara sus mensajes, escribir en la isla y después abrir la sección te
 * mostraría una pantalla en blanco, y volver a la isla haría desaparecer lo que acabas de leer.
 * Peor: al cambiar de vista, React desmonta el componente y el historial se perdería solo. Es la
 * misma razón por la que el WebSocket, el resumen y las alertas viven arriba del árbol.
 *
 * ## Qué hace Argos hoy y qué no
 * **Conversar de verdad llega en la Fase 5**, con el modelo local (Ollama). Hasta entonces esto
 * no finge: arma el estado del mercado con los datos que la app ya tiene cargados —precios,
 * cambios, volatilidad, alertas recientes— y lo dice tal cual, aclarando que lo escribió la app.
 *
 * Fingirlo con plantillas ("parece que BTC está fuerte hoy") sería lo peor de los dos mundos:
 * texto que suena a análisis sin nada detrás. La regla del proyecto vale también para la propia
 * interfaz — sin dato, se dice que no hay dato.
 */

import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { ACTIVOS, simboloDe } from './activos'
import { useAlertas } from './alertas'
import { SIN_DATO, antiguedad, medida, porcentaje, precio as formatearPrecio } from './formato'
import { useFichas } from './resumen'
import { useVolatilidad } from './volatilidad'

export interface Mensaje {
  quien: 'tu' | 'argos'
  /** Texto plano: nunca HTML, ni siquiera el que arma la propia app. */
  texto: string
  momento: string
}

/** Preguntas que Argos sí puede responder hoy, para no dejar la pantalla en blanco. */
export const SUGERENCIAS = [
  '¿Cómo viene el mercado ahora?',
  '¿Qué viste en la última hora?',
  '¿Cuánto se está moviendo BTC?',
] as const

interface Chat {
  mensajes: Mensaje[]
  /** Manda una pregunta. Argos responde con lo que sabe, o dice que todavía no sabe conversar. */
  preguntar: (texto: string) => void
  /** El estado del mercado ahora mismo, sin preguntar nada. */
  contarEstado: () => void
  /** Vacía la conversación. */
  limpiar: () => void
}

const Contexto = createContext<Chat | null>(null)

const ahora = () => new Date().toISOString()

export function ProveedorChat({ children }: { children: ReactNode }) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([])

  const pares = useMemo(() => ACTIVOS.map((activo) => activo.par), [])
  const fichas = useFichas(pares)
  const volatilidades = useVolatilidad(pares)
  const { alertas } = useAlertas()

  /** Arma el estado del mercado con los datos que la app ya tiene cargados. */
  const resumenDeAhora = useCallback((): string => {
    // `useFichas` devuelve `null` para un activo del que Argos todavía no sabe nada: ausencia
    // de dato, no cero. Se dice y se sigue.
    const lineas = fichas.map((ficha, i) => {
      const simbolo = ACTIVOS[i].simbolo
      if (!ficha || ficha.precio === null) return `${simbolo}: sin datos todavía.`

      const cambio = ficha.cambios['24h']
      const vol = volatilidades[ACTIVOS[i].par]

      return (
        `${simbolo}: ${formatearPrecio(ficha.precio)} ` +
        `(${cambio === null ? SIN_DATO : porcentaje(cambio)} en 24 h)` +
        (vol ? `, con un rango típico de ${medida(vol.tipico_pct)} cada 5 min.` : '.')
      )
    })

    const recientes = alertas.filter(
      (alerta) => Date.now() - new Date(alerta.momento).getTime() < 3600_000,
    )

    if (recientes.length === 0) {
      lineas.push('No vi nada fuera de lo normal en la última hora.')
    } else {
      lineas.push(
        `Vi ${recientes.length} ${recientes.length === 1 ? 'cosa' : 'cosas'} en la última hora:`,
      )
      for (const alerta of recientes.slice(0, 4)) {
        lineas.push(
          `· ${alerta.titulo} en ${simboloDe(alerta.simbolo)} (${antiguedad(alerta.momento)}): ${alerta.detalle}`,
        )
      }
    }

    return lineas.join('\n')
  }, [fichas, volatilidades, alertas])

  const contarEstado = useCallback(() => {
    setMensajes((previos) => [
      ...previos,
      { quien: 'tu', texto: '¿Cómo viene el mercado ahora?', momento: ahora() },
      { quien: 'argos', texto: resumenDeAhora(), momento: ahora() },
    ])
  }, [resumenDeAhora])

  const preguntar = useCallback(
    (texto: string) => {
      const pregunta = texto.trim()
      if (!pregunta) return

      // Lo único que Argos sabe responder hoy es el estado del mercado. Si la pregunta va por
      // ahí, se responde con datos; si no, se dice la verdad: todavía no sabe conversar.
      const suenaAEstado = /mercad|precio|c[oó]mo va|c[oó]mo viene|ahora|estado|vist|alert|mov/i.test(
        pregunta,
      )

      setMensajes((previos) => [
        ...previos,
        { quien: 'tu', texto: pregunta, momento: ahora() },
        {
          quien: 'argos',
          texto: suenaAEstado
            ? `${resumenDeAhora()}\n\n(Esto es lo que tengo medido. Entender preguntas de verdad ` +
              'llega con el modelo local, en la Fase 5.)'
            : 'Todavía no sé conversar: el modelo que va a leer los datos y responderte en ' +
              'palabras llega en la Fase 5. Lo que sí puedo hacer ahora es contarte el estado ' +
              'del mercado con los números que tengo — pregúntame cómo viene el mercado.',
          momento: ahora(),
        },
      ])
    },
    [resumenDeAhora],
  )

  const limpiar = useCallback(() => setMensajes([]), [])

  const valor = useMemo(
    () => ({ mensajes, preguntar, contarEstado, limpiar }),
    [mensajes, preguntar, contarEstado, limpiar],
  )

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}

export function useChat(): Chat {
  const valor = useContext(Contexto)
  if (valor === null) {
    throw new Error('useChat() necesita estar dentro de <ProveedorChat>')
  }
  return valor
}

/** La hora de un mensaje, corta: `03:12`. */
export function horaDe(iso: string): string {
  return new Date(iso).toLocaleTimeString('es-CL', { hour: '2-digit', minute: '2-digit' })
}
