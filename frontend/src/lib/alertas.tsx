/**
 * Lo que Argos vio, vivo en el panel (paso 3.6).
 *
 * Del otro lado está `GET /alertas`, que devuelve las últimas alertas emitidas por los cuatro
 * detectores, cada una con su evidencia.
 *
 * ## Un solo pedido para toda la app, otra vez
 * Igual que con el mercado y el resumen: dos lugares muestran alertas —el recuadro del Panel y la
 * vista Alertas completa— y el menú muestra cuántas hay sin leer. Con un `fetch` por componente
 * serían tres pollings pidiendo lo mismo y desincronizándose entre sí. Se pide arriba del todo y
 * todos leen de acá.
 *
 * ## Por qué se pregunta y no se empuja
 * El WebSocket ya existe y podría llevar las alertas, pero no se hizo así todavía y la diferencia
 * importa poco: los detectores por vela se evalúan una vez por minuto (o cada cinco), así que un
 * refresco cada diez segundos no atrasa nada que se note. Empujarlas por el socket es el próximo
 * escalón natural y está anotado — cuando llegue la Fase 4 (Telegram), la difusión de alertas ya
 * va a tener que existir de todos modos.
 *
 * ## Lo "no leído" vive solo en el navegador
 * Marcar una alerta como vista es una preferencia de esta pantalla, no un hecho del mercado: no
 * tiene por qué viajar a la base ni ensuciar la tabla de alertas, que guarda **hechos**. Se anota
 * en `localStorage` el id de la última alerta que se miró, y lo nuevo es todo lo que tenga un id
 * más alto. Como el id lo pone la base y solo sube, alcanza con un número.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { obtenerAlertas } from './api'
import type { AlertaJSON } from './api'

/**
 * Cada cuánto se le vuelve a preguntar al backend.
 *
 * Diez segundos, igual que el resumen. Los detectores más rápidos corren por tick, pero el motor
 * agrupa y despacha de a lotes cada dos segundos; pedir más seguido solo agregaría pedidos.
 */
const REFRESCO = 10_000

/** Cuántas alertas se traen. Suficiente para el feed y para la vista completa sin paginar. */
const CUANTAS = 100

const CLAVE_VISTAS = 'argos:alertas:ultima-vista'

interface Estado {
  /** Las alertas, de la más nueva a la más vieja. Vacío = no hay (o todavía no llegaron). */
  alertas: AlertaJSON[]
  /** `true` mientras no haya llegado ninguna respuesta todavía. */
  cargando: boolean
  /** Qué falló, si falló. Se muestra: un feed vacío por un error no debe parecer calma. */
  error: string | null
  /** Cuántas alertas hay más nuevas que la última que el usuario miró. */
  sinLeer: number
  /** Marca todo lo que hay ahora como visto. */
  marcarVistas: () => void
}

const Contexto = createContext<Estado | null>(null)

function leerUltimaVista(): number {
  const guardado = localStorage.getItem(CLAVE_VISTAS)
  const numero = Number(guardado)
  return Number.isFinite(numero) ? numero : 0
}

export function ProveedorAlertas({ children }: { children: ReactNode }) {
  const [alertas, setAlertas] = useState<AlertaJSON[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ultimaVista, setUltimaVista] = useState<number>(leerUltimaVista)

  useEffect(() => {
    const control = new AbortController()
    let vivo = true

    const pedir = async () => {
      try {
        const nuevas = await obtenerAlertas(CUANTAS, control.signal)
        if (!vivo) return
        setAlertas(nuevas)
        setError(null)
      } catch (fallo) {
        // Un pedido cancelado no es un error: pasa al desmontar y no hay que mostrarlo.
        if (!vivo || control.signal.aborted) return
        setError(fallo instanceof Error ? fallo.message : 'No se pudieron traer las alertas')
      } finally {
        if (vivo) setCargando(false)
      }
    }

    pedir()
    const reloj = setInterval(pedir, REFRESCO)

    return () => {
      vivo = false
      clearInterval(reloj)
      control.abort()
    }
  }, [])

  const marcarVistas = useCallback(() => {
    const masNueva = alertas[0]?.id ?? 0
    setUltimaVista(masNueva)
    localStorage.setItem(CLAVE_VISTAS, String(masNueva))
  }, [alertas])

  const sinLeer = useMemo(
    () => alertas.filter((alerta) => alerta.id > ultimaVista).length,
    [alertas, ultimaVista],
  )

  const valor = useMemo(
    () => ({ alertas, cargando, error, sinLeer, marcarVistas }),
    [alertas, cargando, error, sinLeer, marcarVistas],
  )

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>
}

export function useAlertas(): Estado {
  const valor = useContext(Contexto)
  if (valor === null) {
    throw new Error('useAlertas() necesita estar dentro de <ProveedorAlertas>')
  }
  return valor
}

/** Qué tan fuerte se pinta cada severidad. Los nombres son los de `index.css`. */
export const TONO_POR_SEVERIDAD: Record<string, string> = {
  fuerte: 'hi',
  aviso: 'mid',
  info: 'lo',
}
