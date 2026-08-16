import { useEffect, useState } from 'react'

import { URL_API } from '@/lib/api'
import type { DetectorJSON } from '@/lib/api'
import { useMercado } from '@/lib/mercado'
import { entero } from '@/lib/formato'
import { Icon } from './Icon'

/** Cada cuánto se vuelve a preguntar el estado del backend. */
const REFRESCO = 15_000

interface Salud {
  api: boolean
  base: string | null
  detectores: DetectorJSON[]
  motor: Record<string, number> | null
  /** Lo que informa `GET /mercado/estado` sobre la escritura de ticks. */
  persistencia: { guardados: number; en_espera: number; descartados: number } | null
  /** Cuántas operaciones vio Argos desde que arrancó, sumando todos los símbolos. */
  ticksVistos: number
}

/**
 * Vista Configuración: qué está vigilando Argos y si está sano (paso 3.7).
 *
 * Antes el botón del menú no hacía nada. Y lo que faltaba no era una pantalla de ajustes —hay
 * uno solo, el tema— sino **poder mirar a Argos por dentro sin abrir una terminal**: si la base
 * responde, si la ingesta está guardando, qué detectores corren y con qué cadencia.
 *
 * Es información que ya existía repartida en `/health/db`, `/detectores` y `/mercado/estado`;
 * acá se junta. Nada de esto es configurable todavía a propósito: los umbrales de los detectores
 * se calibraron contra un año de historia (ver `CHECKLIST.md`), y dejar que se toquen a mano sin
 * poder medir el efecto sería deshacer justamente lo que los hizo confiables.
 */
export function ConfiguracionView({
  theme,
  toggleTheme,
}: {
  theme: 'dark' | 'light'
  toggleTheme: () => void
}) {
  const { conectado } = useMercado()
  const [salud, setSalud] = useState<Salud>({
    api: false,
    base: null,
    detectores: [],
    motor: null,
    persistencia: null,
    ticksVistos: 0,
  })

  useEffect(() => {
    const control = new AbortController()
    let vivo = true

    const mirar = async () => {
      const nueva: Salud = {
        api: false,
        base: null,
        detectores: [],
        motor: null,
        persistencia: null,
        ticksVistos: 0,
      }

      try {
        const respuesta = await fetch(`${URL_API}/health/db`, { signal: control.signal })
        const cuerpo = await respuesta.json()
        nueva.api = true
        nueva.base = respuesta.ok ? `PostgreSQL ${cuerpo.versiones?.postgres} · TimescaleDB ${cuerpo.versiones?.timescaledb}` : null
      } catch {
        // Sin API no hay nada más que preguntar: se deja todo en falso y se muestra.
        if (!vivo || control.signal.aborted) return
        setSalud(nueva)
        return
      }

      try {
        const respuesta = await fetch(`${URL_API}/detectores`, { signal: control.signal })
        const cuerpo = await respuesta.json()
        nueva.detectores = cuerpo.detectores ?? []
        nueva.motor = cuerpo.motor ?? null
      } catch {
        /* el bloque de detectores queda vacío y se dice abajo */
      }

      try {
        const respuesta = await fetch(`${URL_API}/mercado/estado`, { signal: control.signal })
        const cuerpo = await respuesta.json()
        nueva.persistencia = cuerpo.persistencia ?? null
        nueva.ticksVistos = Object.values(
          (cuerpo.simbolos ?? {}) as Record<string, { ticks_vistos?: number }>,
        ).reduce((suma, simbolo) => suma + (simbolo.ticks_vistos ?? 0), 0)
      } catch {
        /* idem */
      }

      if (vivo && !control.signal.aborted) setSalud(nueva)
    }

    mirar()
    const reloj = setInterval(mirar, REFRESCO)
    return () => {
      vivo = false
      clearInterval(reloj)
      control.abort()
    }
  }, [])

  return (
    <>
      <div className="panel">
        <div className="pulse-h">
          <h3>Estado de Argos</h3>
          <span className="mono-l stamp">{URL_API.replace(/^https?:\/\//, '')}</span>
        </div>

        <div className="estado-grid">
          <Pieza titulo="API" bien={salud.api} detalle={salud.api ? 'responde' : 'no responde'} />
          <Pieza
            titulo="Base de datos"
            bien={salud.base !== null}
            detalle={salud.base ?? 'sin conexión'}
          />
          <Pieza
            titulo="Precios en vivo"
            bien={conectado}
            detalle={conectado ? 'WebSocket abierto' : 'reconectando'}
          />
          <Pieza
            titulo="Ingesta"
            /* Tener unos pocos ticks en la cola es lo normal: el escritor vuelca por lotes cada
               dos segundos. Lo que sí es un problema es que la cola CREZCA — ahí la ingesta anda
               pero la base no está recibiendo. El colchón es de 20.000, así que 500 ya avisa
               temprano sin marcar en rojo el funcionamiento habitual. */
            bien={salud.ticksVistos > 0 && (salud.persistencia?.en_espera ?? 0) < 500}
            detalle={
              salud.persistencia
                ? `${entero(salud.ticksVistos)} operaciones vistas · ${entero(salud.persistencia.guardados)} guardadas · ${entero(salud.persistencia.en_espera)} en espera`
                : 'sin datos'
            }
          />
        </div>
      </div>

      <div className="panel">
        <div className="pulse-h">
          <h3>Qué vigila Argos</h3>
          {salud.motor && (
            <span className="mono-l stamp">
              {entero(Number(salud.motor.emitidas ?? 0))} emitidas ·{' '}
              {entero(Number(salud.motor.silenciadas ?? 0))} silenciadas
            </span>
          )}
        </div>

        {salud.detectores.length === 0 ? (
          <p className="vacio">No se pudo leer el catálogo de detectores.</p>
        ) : (
          salud.detectores.map((detector) => (
            <div className="detector" key={detector.nombre}>
              <div className="det-t">
                <b>{detector.titulo}</b>
                <span className="mono-l">
                  {detector.cadencia === 'por_tick'
                    ? 'cada operación'
                    : `cada vela de ${detector.intervalo}`}
                </span>
              </div>
              <p>{detector.descripcion}</p>
              <div className="det-m mono-l">
                {detector.velas_necesarias > 0 && `${detector.velas_necesarias} velas de historia · `}
                se calla {Math.round(detector.silencio_segundos / 60)} min tras avisar
              </div>
            </div>
          ))
        )}

        {/* El antirruido no es un detalle de implementación: es media razón de ser del
            proyecto, así que se explica donde se ve. */}
        <p className="vacio">
          Las alertas silenciadas no son alertas perdidas: son la misma noticia contada una sola
          vez. Los umbrales de cada detector se eligieron corriéndolos sobre un año de historia
          real, buscando que hablen unas pocas veces al mes.
        </p>
      </div>

      <div className="panel">
        <div className="pulse-h">
          <h3>Apariencia</h3>
        </div>
        <div className="umbral-form">
          <button type="button" onClick={toggleTheme}>
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            {theme === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro'}
          </button>
          <span className="vacio" style={{ margin: 0 }}>
            Se recuerda en este navegador. Sin elegir, Argos sigue al sistema.
          </span>
        </div>
      </div>
    </>
  )
}

function Pieza({ titulo, bien, detalle }: { titulo: string; bien: boolean; detalle: string }) {
  return (
    <div className="estado-p">
      <div className="l">
        <span className={`punto ${bien ? 'ok' : 'mal'}`} /> {titulo}
      </div>
      <div className="v">{detalle}</div>
    </div>
  )
}
